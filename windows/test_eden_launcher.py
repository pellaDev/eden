# Tests of the Windows launcher (eden.py) with a fake operating-system layer. Run: python3 test_eden_launcher.py
import os
import sys
import tempfile

import eden as e


class FakeSystem:
    def __init__(self):
        self.procs, self.next, self.mesh, self.nord_up, self.fail_spawn = {}, 100, ("NordLynx", "100.64.0.5"), True, set()

    def spawn(self, argv, log_path, env, cwd):
        self.next += 1
        name = os.path.basename(log_path)[:-4]
        if name in self.fail_spawn:
            return self.next     # a pid that is never alive
        self.procs[self.next] = " ".join(argv) + " " + env.get("EDEN_REMOTE_BIND", env.get("EDEN_FORWARD_BIND", ""))
        return self.next

    def cmdline(self, pid):
        return self.procs.get(pid)

    def stop(self, pid):
        self.procs.pop(pid, None)

    def mesh_address(self):
        return self.mesh

    def nord_running(self):
        return self.nord_up


def launcher(**kw):
    d = tempfile.mkdtemp()
    env = e.build_env({"EDEN_DATA": d})
    os.makedirs(os.path.dirname(env["EDEN_CONFIG"]), exist_ok=True)
    open(env["EDEN_CONFIG"], "w").write('{"remote_port": 8443}')
    out, calls = [], []
    sysx = FakeSystem()
    for k, v in kw.items():
        setattr(sysx, k, v)
    lt = e.Launcher(env=env, system=sysx, python="py", out=out.append, sleep=lambda s: None)
    lt.winctl = lambda cmd: (calls.append(cmd), True)[1]
    return lt, sysx, out, calls


def test_build_env_defaults_and_overrides():
    env = e.build_env({"LOCALAPPDATA": "L"})
    assert env["EDEN_CONFIG"] == os.path.join("L", "Eden", "config", "eden.json") and env["EDEN_LOCAL_PORT"] == "8780"
    assert env["EDEN_RUN"].startswith(os.path.join("L", "Eden")) and env["EDEN_HOME"] == e.HOME
    env = e.build_env({"LOCALAPPDATA": "L", "EDEN_LOCAL_PORT": "9000", "EDEN_DATA": "D"})
    assert env["EDEN_LOCAL_PORT"] == "9000" and env["EDEN_CONFIG"] == os.path.join("D", "config", "eden.json")


def test_vpn_up_order_and_listeners():
    lt, s, out, calls = launcher()
    assert lt.vpn_up()
    assert calls == ["guard", "final"]                              # guard first, ports opened last
    assert lt.alive("eden_remote") and lt.alive("eden_forward")
    assert any("100.64.0.5" in p for p in s.procs.values())         # bound to the Meshnet address
    assert "VPN up." in out and any("eden_remote up on 100.64.0.5:8443" in x for x in out)


def test_vpn_up_without_meshnet_fails_closed():
    lt, s, out, calls = launcher(mesh=None)
    lt.mesh_wait = lambda seconds=30: None
    assert not lt.vpn_up()
    assert calls == ["guard", "deny-all"] and not s.procs          # nothing listening, guard rules in place
    assert "FAILED: vpn-up" in out


def test_vpn_up_stops_when_a_listener_fails():
    lt, s, out, calls = launcher(fail_spawn={"eden_remote"})
    assert not lt.vpn_up()
    assert "final" not in calls and calls[-1] == "deny-all"


def test_vpn_down_blocks_first_then_stops():
    lt, s, out, calls = launcher()
    lt.vpn_up()
    calls.clear()
    lt.vpn_down()
    assert calls == ["deny-all"] and not lt.alive("eden_remote") and not lt.alive("eden_forward") and not s.procs


def test_vpn_down_reports_a_failed_guard():
    # The guard state is what the user relies on after a failure: when the rules could not be applied, down()
    # must say so and fail, not answer True.
    lt, s, out, calls = launcher()
    lt.vpn_up()
    calls.clear()
    out.clear()
    lt.winctl = lambda cmd: (calls.append(cmd), False)[1]      # the helper is unreachable
    assert not lt.vpn_down()
    assert calls == ["deny-all"] and not s.procs
    assert any("guard rules were not applied" in x for x in out)


def test_stale_pid_is_not_trusted():
    lt, s, _, _ = launcher()
    open(lt.pid_file("eden_remote"), "w").write("999")             # no such process
    assert not lt.alive("eden_remote")
    s.procs[999] = "notepad.exe"                                    # a pid reused by something else
    assert not lt.alive("eden_remote")
    lt.kill("eden_remote")
    assert 999 in s.procs                                           # never stopped an unrelated process


def test_local_up_down_and_loopback_only():
    lt, s, out, _ = launcher()
    assert lt.local_up() and lt.alive("eden_local", "uvicorn")
    line = next(v for v in s.procs.values() if "uvicorn" in v)
    assert "--host 127.0.0.1" in line and "backend.eden_local:app" in line
    assert lt.local_up() and "eden_local already running" in out
    lt.local_down()
    assert not lt.alive("eden_local", "uvicorn")


def test_status_lines_match_what_the_ui_reads():
    import re
    lt, s, out, _ = launcher()
    lt.vpn_up()
    out.clear()
    lt.status()
    names = {m.group(1): m.group(2) for m in (re.match(r"^([A-Za-z0-9_]+): (running|stopped|up|down)\b", x) for x in out) if m}
    assert names == {"eden_local": "stopped", "nordvpnd": "running", "NordLynx": "up", "eden_remote": "running", "eden_forward": "running"}


def test_vpn_reload():
    lt, s, out, calls = launcher(mesh=None)
    assert lt.vpn_reload() and out[0] == "RELOAD: deferred" and not calls
    lt, s, out, calls = launcher()
    lt.vpn_up()
    calls.clear()
    out.clear()
    assert lt.vpn_reload() and calls == ["reload"] and "RELOAD: applied" in out


def test_foreground_restart_request_and_teardown():
    lt, s, out, calls = launcher()
    open(os.path.join(lt.run_dir, e.RESTART_FILE), "w").close()
    assert lt.foreground(once=True)
    assert "== restarting Eden ==" in out and "Eden restarted." in out
    assert not os.path.exists(os.path.join(lt.run_dir, e.RESTART_FILE))
    assert not s.procs and not os.path.exists(lt.pid_file("eden"))   # everything stopped at the end


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print("ok", name)
        except Exception as e:
            failed.append(name)
            print(f"FAIL {name}: {e!r}")
    if failed:
        # Stopping at the first failure hid every test after it and left the exit code at 0, so a runner could not
        # tell a pass from a broken suite.
        sys.exit(f"{len(failed)} of {len(tests)} failed: {', '.join(failed)}")
    print("ALL WINDOWS LAUNCHER TESTS PASSED")
