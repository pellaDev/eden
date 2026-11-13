# Tests of the elevated helper and its client with a fake PowerShell and a real local transport: the named pipe on
# Windows, a Unix socket elsewhere. Nothing here needs administrator rights or a real firewall.
# Run: python3 test_eden_winhelper.py
import os
import sys
import tempfile
import threading
import time

import eden_winclient as client
import eden_winhelper as hp

KEY = b"k" * 40
SAFE = ("C:\\ProgramData\\Eden\\allowed_ports NT AUTHORITY\\SYSTEM:(I)(F)\n"
        "                                    BUILTIN\\Administrators:(I)(F)\n"
        "                                    BUILTIN\\Users:(I)(RX)\n\nSuccessfully processed 1 files; Failed processing 0 files\n")
UNSAFE = SAFE.replace("BUILTIN\\Users:(I)(RX)", "BUILTIN\\Users:(I)(M)")
PATH = "C:\\ProgramData\\Eden\\allowed_ports"
FAMILY = "AF_PIPE" if os.name == "nt" else "AF_UNIX"


def pipe_path(d):
    """The transport this system can actually build: a named pipe on Windows, a socket file elsewhere."""
    return r"\\.\pipe\eden-test-" + os.path.basename(d) if os.name == "nt" else os.path.join(d, "pipe")


def serve_on(h, address, key=KEY):
    """serve() in a thread, and wait for the listener. Returns the stop event."""
    stop, ready = threading.Event(), threading.Event()
    threading.Thread(target=hp.serve, kwargs={"address": address, "family": FAMILY, "key": key, "helper": h,
                                              "stop": stop, "ready": ready}, daemon=True).start()
    assert ready.wait(5), "the listener did not start"
    return stop


class FakePs:
    def __init__(self, adapter="NordLynx|100.64.0.5"):
        self.adapter, self.scripts, self.fail = adapter, [], False

    def __call__(self, script):
        self.scripts.append(script)
        if "Get-NetIPAddress" in script:
            return 0, self.adapter or ""
        if self.fail:
            return 1, "boom"
        if "Get-NetFirewallRule -Group" in script:
            return 0, "Eden a rest\nEden a set1 allow"
        return 0, ""


def helper(ports_text=None, adapter="NordLynx|100.64.0.5", icacls=SAFE):
    d = tempfile.mkdtemp()
    env = {"EDEN_WIN_DATA": d}
    if ports_text is not None:
        open(os.path.join(d, "allowed_ports"), "w").write(ports_text)
    ps = FakePs(adapter)
    return hp.Helper(ps=ps, icacls=lambda p: icacls.replace(PATH, p), env=env), ps, d


def test_acl():
    assert hp.acl_problem(SAFE, PATH) is None
    assert "Users has the right M" in hp.acl_problem(UNSAFE, PATH)
    assert hp.acl_problem("", PATH) == "the ACL is empty"
    assert "Everyone" in hp.acl_problem(SAFE + "                                    Everyone:(W)\n", PATH)
    # A line that is not an ACE is skipped, never read as unsafe. icacls writes its summary in the language of the
    # system, so a parser that trusted the English wording refused a perfectly safe file on a localized Windows.
    assert hp.acl_problem("garbage line\n", PATH) == "the ACL is empty"
    assert hp.acl_problem(SAFE + "\nElaborati 1 files; Elaborazione fallita di 0 file\n", PATH) is None
    assert hp.acl_problem(SAFE + "\nSuccessfully processed 1 files\n", PATH) is None
    assert hp.acl_problem("C:\\x NT AUTHORITY\\SYSTEM:(F)\n   BUILTIN\\Administrators:(F)\n", "C:\\x") is None


def test_helper_key_is_checked_the_same_way():
    # A shared secret is only a secret while nobody else can read the file, so helper.key follows the same rule as
    # allowed_ports. Without the check the helper would serve a key any user could read.
    d = tempfile.mkdtemp()
    open(os.path.join(d, "helper.key"), "wb").write(KEY)
    good = hp.Helper(ps=FakePs(), icacls=lambda p: SAFE.replace(PATH, p), env={"EDEN_WIN_DATA": d})
    assert good.key() == KEY
    bad = hp.Helper(ps=FakePs(), icacls=lambda p: UNSAFE.replace(PATH, p), env={"EDEN_WIN_DATA": d})
    try:
        bad.key()
        raise AssertionError("an unsafe key file must be refused")
    except hp.HelperError as e:
        assert "helper.key" in str(e) and "Users has the right M" in str(e), e
    empty = hp.Helper(ps=FakePs(), icacls=lambda p: "", env={"EDEN_WIN_DATA": d})
    assert empty.key() == KEY            # nothing to read: no invented ACL, the file is what it is


def test_ports_file():
    h, _, _ = helper(None)
    assert h.handle({"cmd": "ports-list"}) == {"ok": True, "ports": [8443]}          # file missing: the default only
    h, _, _ = helper("# eden\n8443\n8096  # media\n\n")
    assert h.handle({"cmd": "ports-list"})["ports"] == [8096, 8443]
    h, _, _ = helper("8443\nabc\n")
    assert "not a port" in h.handle({"cmd": "ports-list"})["error"]
    h, _, _ = helper("8443\n", icacls=UNSAFE)                                          # writable by users: refuse
    assert "not safe" in h.handle({"cmd": "ports-list"})["error"]
    h, _, _ = helper("")                                                              # empty file: nothing may be opened
    assert h.handle({"cmd": "ports-list"})["ports"] == []


def test_apply_validates_and_applies():
    h, ps, _ = helper("8443\n8096\n")
    r = h.handle({"cmd": "apply", "pairs": [[8096, "100.64.0.10"], [8443, "100.64.0.10"]]})
    assert r == {"ok": True, "applied": 2}, r
    script = ps.scripts[-1]
    assert "Set-EdenRules" in script and "-Alias 'NordLynx'" in script and "'8096'" in script and "100.64.0.10" in script
    for bad, text in (([[22, "100.64.0.10"]], "not in the allowed"), ([[8096, "192.0.2.1"]], "outside the Meshnet"),
                      ([[8096, "x'; Remove-Item"]], "not an IPv4"), ([[True, "100.64.0.10"]], "not in the allowed"),
                      ([[8096]], "[port, address]"), ("nope", "list"), ([[8096, "100.64.0.1"]] * 300, "at most")):
        before = len(ps.scripts)
        r = h.handle({"cmd": "apply", "pairs": bad})
        assert not r["ok"] and text in r["error"], (bad, r)


def test_refused_requests_run_nothing_dangerous():
    h, ps, _ = helper("8443\n")
    h.handle({"cmd": "apply", "pairs": [[22, "100.64.0.10"]]})
    assert not any("Set-EdenRules" in s and "New-NetFirewallRule" in s and "Eden " in s and "'22'" in s for s in ps.scripts)
    assert not h.handle({"cmd": "format-c"})["ok"] and not h.handle("x")["ok"] and not h.handle({"cmd": 3})["ok"]


def test_apply_needs_meshnet():
    h, ps, _ = helper("8443\n", adapter="")
    r = h.handle({"cmd": "apply", "pairs": [[8443, "100.64.0.10"]]})
    assert not r["ok"] and "Meshnet is off" in r["error"]
    r = h.handle({"cmd": "guard"})
    # Rules put on a guessed adapter name are not the guard: they could sit on another interface while the real
    # Meshnet one stays open. The helper must refuse, not guess.
    assert not r["ok"] and "refusing to guess" in r["error"], r
    assert not any("Set-EdenRules" in s for s in ps.scripts)
    h, ps, _ = helper("8443\n")                    # with an adapter, the guard works as before
    r = h.handle({"cmd": "guard"})
    assert r["ok"] and "-Alias 'NordLynx'" in ps.scripts[-1] and "'Block'" in ps.scripts[-1] and "Protocol='Any'" in ps.scripts[-1]


def test_powershell_failure_is_reported():
    h, ps, _ = helper("8443\n")
    ps.fail = True
    r = h.handle({"cmd": "apply", "pairs": [[8443, "100.64.0.10"]]})
    assert not r["ok"] and "PowerShell failed" in r["error"]


def test_ping_list_remove():
    h, ps, _ = helper("8443\n")
    assert h.handle({"cmd": "ping"}) == {"ok": True, "adapter": "NordLynx", "address": "100.64.0.5"}
    assert h.handle({"cmd": "list"})["rules"] == ["Eden a rest", "Eden a set1 allow"]
    assert h.handle({"cmd": "remove"})["ok"] and "Remove-EdenRules" in ps.scripts[-1]
    h, _, _ = helper("8443\n", adapter="")
    assert h.handle({"cmd": "ping"})["adapter"] is None


def test_log_is_written():
    h, _, d = helper("8443\n")
    h.handle({"cmd": "guard"})
    h.handle({"cmd": "bogus"})
    text = open(os.path.join(d, "helper.log")).read()
    assert "guard" in text and "REFUSED" in text


def test_a_broken_request_does_not_kill_the_listener():
    # A listener thread that dies leaves the scheduled task as a zombie process with no listener and no error
    # reported: the helper would look alive in Task Scheduler while answering nobody.
    class Boom(FakePs):
        def __call__(self, script):
            raise RuntimeError("powershell exploded")

    d = tempfile.mkdtemp()
    h = hp.Helper(ps=Boom(), icacls=lambda p: SAFE.replace(PATH, p), env={"EDEN_WIN_DATA": d})
    stop = serve_on(h, pipe_path(d))
    r = client.call("ping", address=pipe_path(d), family=FAMILY, key=KEY)
    assert not r["ok"] and "helper error" in r["error"], r
    assert client.call("ports-list", address=pipe_path(d), family=FAMILY, key=KEY)["ok"], "the listener must survive"
    stop.set()

    # A key that is not bytes, or a key file that cannot be read, must be refused before the listener: an exception
    # here used to end the thread silently, leaving the task running with no listener.
    d2 = tempfile.mkdtemp()
    open(os.path.join(d2, "helper.key"), "wb").write(KEY)
    h2 = hp.Helper(ps=FakePs(), icacls=lambda p: SAFE.replace(PATH, p), env={"EDEN_WIN_DATA": d2})
    try:
        hp.serve(address=pipe_path(d2), family=FAMILY, key="not-bytes", helper=h2)
        raise AssertionError("a non-bytes key must be refused")
    except SystemExit as e:
        assert "listener cannot start" in str(e), e
    assert "listener cannot start" in open(os.path.join(d2, "helper.log")).read()
    # An unsafe key file is refused the same way, before anything answers a request.
    h3 = hp.Helper(ps=FakePs(), icacls=lambda p: UNSAFE.replace(PATH, p), env={"EDEN_WIN_DATA": d2})
    try:
        hp.serve(address=pipe_path(d2), family=FAMILY, helper=h3)
        raise AssertionError("an unsafe key file must be refused")
    except SystemExit as e:
        assert "not safe" in str(e), e


def test_client_and_server_over_the_platform_transport():
    h, ps, d = helper("8443\n8096\n")
    sock = pipe_path(d)
    stop = serve_on(h, sock)
    r = client.call("apply", address=sock, family=FAMILY, key=KEY, pairs=[[8096, "100.64.0.10"]])
    assert r == {"ok": True, "applied": 1}, r
    assert client.call("ping", address=sock, family=FAMILY, key=KEY)["adapter"] == "NordLynx"
    # a client with the wrong key gets nothing and does not stop the server
    refused = False
    try:
        client.call("guard", address=sock, family=FAMILY, key=b"w" * 40)
    except SystemExit as e:
        refused = "not reachable" in str(e)
    assert refused, "a wrong key must be refused"
    assert client.call("ports-list", address=sock, family=FAMILY, key=KEY)["ports"] == [8096, 8443]
    stop.set()
    try:
        client.call("ping", address=sock, family=FAMILY, key=KEY)
    except SystemExit:
        pass


def test_client_reports_an_absent_helper():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "helper.key"), "wb").write(KEY)
    try:
        client.call("ping", address=pipe_path(d), family=FAMILY, env={"EDEN_WIN_DATA": d})
        raise SystemExit("no error")
    except SystemExit as e:
        assert "not reachable" in str(e)


def test_client_starts_the_helper_on_demand():
    h, ps, d = helper("8443\n")
    sock = pipe_path(d)
    stop, calls = threading.Event(), []

    def starter():
        calls.append(1)
        threading.Thread(target=hp.serve, kwargs={"address": sock, "family": FAMILY, "key": KEY, "helper": h,
                                                  "stop": stop, "ready": threading.Event()}, daemon=True).start()
        return True

    client._last_start[0] = 0.0
    r = client.call("ping", address=sock, family=FAMILY, key=KEY, starter=starter, wait=5)
    assert r["ok"] and calls == [1], (r, calls)
    stop.set()


def test_client_does_not_wait_when_there_is_no_task():
    client._last_start[0] = 0.0
    d = tempfile.mkdtemp()
    t0 = __import__("time").monotonic()
    try:
        client.call("ping", address=pipe_path(d), family=FAMILY, key=KEY, starter=lambda: False, wait=5)
        raise AssertionError("no error")
    except SystemExit as e:
        assert "not reachable" in str(e)
    assert __import__("time").monotonic() - t0 < 2


def test_wrong_key_never_starts_the_helper():
    h, ps, d = helper("8443\n")
    sock = pipe_path(d)
    stop = serve_on(h, sock)
    calls = []
    client._last_start[0] = 0.0
    try:
        client.call("ping", address=sock, family=FAMILY, key=b"w" * 40, starter=lambda: calls.append(1) or True, wait=2)
    except SystemExit:
        pass
    assert calls == [], "a wrong key must not trigger a start"
    stop.set()


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
    print("ALL HELPER TESTS PASSED")
