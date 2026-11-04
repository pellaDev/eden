# Eden launcher, Windows edition: the counterpart of start.sh. Same commands, same output lines the UI reads
# ("name: running|stopped|up|down", "RELOAD: applied|deferred"), no remote browser session (not part of the Windows
# edition). Started on demand by the user, never at boot; Eden's lifetime is tied to this process in foreground mode.
# Nothing of this file is imported by the Linux edition. Needs Python 3.11+ and psutil (see requirements-windows.txt).
#
#   eden.py                    foreground: start everything; Ctrl+C or closing the window stops everything
#   eden.py up | down          VPN group + Eden local together / stop everything
#   eden.py vpn-up | vpn-down  Meshnet group: guard rules, eden_remote and eden_forward on the Meshnet address, rules
#   eden.py vpn-reload         re-apply the rules from eden.json while the VPN is up
#   eden.py remote-restart     restart eden_remote only (drops every remote session)
#   eden.py local-up | local-down   Eden local, the loopback-only admin UI and API
#   eden.py status
#
# On Windows the user turns Meshnet on in the Nord app: "vpn-up" waits for the Meshnet adapter (an address in
# 100.64.0.0/10) instead of starting it, and "vpn-down" leaves the firewall in the guard state (everything blocked)
# and does not touch Nord. Paths come from the environment or from %LOCALAPPDATA%\Eden; nothing is absolute here.

import ipaddress
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.dirname(HERE)
MESH_NET = ipaddress.ip_network("100.64.0.0/10")
NORD_SERVICE = "nordvpn-service"
RESTART_FILE = "restart.request"


def build_env(base, home=HOME):
    """The EDEN_* variables every Eden process reads (the same names as on Linux), with Windows defaults."""
    data = base.get("EDEN_DATA") or os.path.join(base.get("LOCALAPPDATA") or os.path.expanduser("~"), "Eden")
    env = dict(base)
    defaults = {
        "EDEN_HOME": home,
        "EDEN_DATA": data,
        "EDEN_CONFIG": os.path.join(data, "config", "eden.json"),
        "EDEN_RUN": os.path.join(data, "run"),
        "EDEN_LOGS": os.path.join(data, "logs"),
        "EDEN_SECRETS": os.path.join(data, "secrets"),
        "EDEN_AVATARS": os.path.join(data, "avatars.json"),
        "EDEN_HELPER": r"\\.\pipe\eden-helper",   # informational on Windows: the helper is reached through the pipe
        "MESH_IFACE": "NordLynx",                  # the real adapter is found by its 100.64.0.0/10 address
        "EDEN_LOCAL_PORT": "8780",
        "EDEN_UPSTREAM_PORT": "0",                  # no upstream behind the remote login unless configured
    }
    for key, value in defaults.items():
        if not env.get(key):
            env[key] = value
    return env


class System:
    """Everything that touches the operating system, in one place so the launcher logic is testable anywhere."""

    def __init__(self):
        try:
            import psutil
        except ImportError:
            sys.exit("eden: psutil is missing (install\\install-user.ps1)")
        self.psutil = psutil

    def spawn(self, argv, log_path, env, cwd):
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open(log_path, "wb") as log:
            return subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, cwd=cwd,
                                    creationflags=flags).pid

    def cmdline(self, pid):
        try:
            return " ".join(self.psutil.Process(pid).cmdline())
        except (self.psutil.Error, OSError):
            return None

    def stop(self, pid):
        try:
            proc = self.psutil.Process(pid)
            for child in proc.children(recursive=True):
                child.kill()
            proc.terminate()
            proc.wait(5)
        except self.psutil.TimeoutExpired:
            proc.kill()
        except (self.psutil.Error, OSError):
            pass

    def mesh_address(self):
        """(adapter name, address) of the Meshnet adapter, or None while Meshnet is off."""
        for name, addrs in self.psutil.net_if_addrs().items():
            for a in addrs:
                if a.family.name == "AF_INET":
                    try:
                        if ipaddress.ip_address(a.address) in MESH_NET:
                            return name, a.address
                    except ValueError:
                        continue
        return None

    def nord_running(self):
        try:
            return self.psutil.win_service_get(NORD_SERVICE).status() == "running"
        except Exception:
            return False


class Launcher:
    def __init__(self, env=None, system=None, python=None, out=print, sleep=time.sleep):
        self.env = env or build_env(os.environ)
        self.sys = system or System()
        self.python = python or sys.executable
        self.out, self.sleep = out, sleep
        self.run_dir, self.logs = self.env["EDEN_RUN"], self.env["EDEN_LOGS"]
        for d in (self.run_dir, self.logs, self.env["EDEN_SECRETS"], os.path.dirname(self.env["EDEN_CONFIG"])):
            os.makedirs(d, exist_ok=True)

    # -- processes
    SCRIPTS = {"eden_remote": ("bin", "eden_remote", "eden_remote.py"), "eden_forward": ("bin", "eden_forward", "eden_forward.py")}

    def pid_file(self, name):
        return os.path.join(self.run_dir, name + ".pid")

    def alive(self, name, needle=None):
        """True if the pid file names a running process whose command line contains `needle` (a stale pid file must
        never make us trust, or stop, an unrelated process)."""
        try:
            pid = int(open(self.pid_file(name)).read().strip())
        except (OSError, ValueError):
            return False
        line = self.sys.cmdline(pid)
        return line is not None and (needle or name) in line

    def spawn(self, name, argv, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        pid = self.sys.spawn(argv, os.path.join(self.logs, name + ".log"), env, HOME)
        with open(self.pid_file(name), "w") as f:
            f.write(str(pid))

    def kill(self, name):
        try:
            pid = int(open(self.pid_file(name)).read().strip())
        except (OSError, ValueError):
            return
        if self.alive(name):
            self.sys.stop(pid)
        try:
            os.remove(self.pid_file(name))
        except OSError:
            pass

    def port(self):
        return json.load(open(self.env["EDEN_CONFIG"]))["remote_port"]

    # -- helper commands run as separate processes, like eden_ctl on Linux
    def winctl(self, cmd):
        r = subprocess.run([self.python, os.path.join(HERE, "eden_winctl.py"), cmd], env=self.env, capture_output=True, text=True)
        text = (r.stdout + r.stderr).strip()
        if text:
            self.out(text)
        return r.returncode == 0

    # -- groups
    def local_up(self):
        if self.alive("eden_local", "uvicorn"):
            self.out("eden_local already running")
            return True
        # Hardcoded to loopback: this admin backend must never be reachable from anywhere but 127.0.0.1.
        self.spawn("eden_local", [self.python, "-m", "uvicorn", "backend.eden_local:app", "--host", "127.0.0.1",
                                  "--port", self.env["EDEN_LOCAL_PORT"]])
        self.sleep(2)
        if not self.alive("eden_local", "uvicorn"):
            self.out(f"eden_local failed to start, see {self.logs}\\eden_local.log")
            return False
        self.out(f"eden_local up on http://127.0.0.1:{self.env['EDEN_LOCAL_PORT']}/")
        return True

    def local_down(self):
        self.kill("eden_local")

    def mesh_wait(self, seconds=30):
        """Meshnet is started by the user in the Nord app: wait for its adapter instead of starting it."""
        for _ in range(seconds):
            adapter = self.sys.mesh_address()
            if adapter:
                return adapter
            self.sleep(1)
        return None

    def remote_up(self):
        if self.alive("eden_remote"):
            self.out("eden_remote already running")
            return True
        adapter = self.mesh_wait(1)
        if not adapter:
            self.out("eden_remote: no Meshnet address, is Meshnet on in the Nord app?")
            return False
        self.spawn("eden_remote", [self.python, os.path.join(HOME, *self.SCRIPTS["eden_remote"])], {"EDEN_REMOTE_BIND": adapter[1]})
        self.sleep(1)
        if not self.alive("eden_remote"):
            self.out(f"eden_remote failed to start, see {self.logs}\\eden_remote.log")
            return False
        self.out(f"eden_remote up on {adapter[1]}:{self.port()}")
        return True

    def remote_down(self):
        self.kill("eden_remote")

    def forward_up(self):
        if self.alive("eden_forward"):
            self.out("eden_forward already running")
            return True
        adapter = self.mesh_wait(1)
        if not adapter:
            self.out("eden_forward: no Meshnet address, is Meshnet on in the Nord app?")
            return False
        for f in ("forward.json", "forward.status.json"):    # never start from a previous run's routes
            try:
                os.remove(os.path.join(self.run_dir, f))
            except OSError:
                pass
        self.spawn("eden_forward", [self.python, os.path.join(HOME, *self.SCRIPTS["eden_forward"])], {"EDEN_FORWARD_BIND": adapter[1]})
        self.sleep(1)
        if not self.alive("eden_forward"):
            self.out(f"eden_forward failed to start, see {self.logs}\\eden_forward.log")
            return False
        self.out(f"eden_forward up on {adapter[1]}")
        return True

    def forward_down(self):
        self.kill("eden_forward")
        for f in ("forward.json", "forward.status.json"):
            try:
                os.remove(os.path.join(self.run_dir, f))
            except OSError:
                pass

    def vpn_up(self):
        # Order matters: guard rules before anything listens, listeners after Meshnet has an address, the rules that
        # open ports last (a port is only reachable once whatever is behind it is up).
        for step in (lambda: self.winctl("guard"), lambda: self.mesh_wait() is not None, self.remote_up, self.forward_up,
                     lambda: self.winctl("final")):
            if not step():
                self.out("FAILED: vpn-up")
                self.vpn_down()
                return False
        self.out("VPN up.")
        return True

    def vpn_down(self):
        self.winctl("deny-all")        # first: nothing may be reachable while the listeners go away
        self.remote_down()
        self.forward_down()
        self.out("== leftovers (VPN) ==")
        self.out("(Meshnet itself is switched off in the Nord app; the Eden rules stay in the guard state)")
        return True

    def vpn_reload(self):
        if not self.sys.mesh_address():
            self.out("RELOAD: deferred")
            self.out("VPN not up: config saved, rules will be loaded at the next vpn-up.")
            return True
        if not self.alive("eden_forward") and not self.forward_up():
            self.out("RELOAD: failed (eden_forward)")
            return False
        if not self.winctl("reload"):
            self.out("RELOAD: failed")
            return False
        self.out("RELOAD: applied")
        return True

    def remote_restart(self):
        if not self.alive("eden_remote"):
            self.out("eden_remote is not running (is the VPN up?)")
            return False
        self.remote_down()
        self.sleep(1)
        return self.remote_up()

    def status(self):
        self.out("-- Eden locale --")
        self.out(f"eden_local: running (http://127.0.0.1:{self.env['EDEN_LOCAL_PORT']}/)" if self.alive("eden_local", "uvicorn") else "eden_local: stopped")
        self.out("-- VPN --")
        self.out("nordvpnd: running" if self.sys.nord_running() else "nordvpnd: stopped")
        self.out(f"{self.env['MESH_IFACE']}: " + ("up" if self.sys.mesh_address() else "down"))
        self.out("eden_remote: running" if self.alive("eden_remote") else "eden_remote: stopped")
        self.out("eden_forward: running" if self.alive("eden_forward") else "eden_forward: stopped")
        return True

    def up(self):
        if not self.vpn_up():
            return False
        if not self.local_up():
            return False
        self.out("Eden up (VPN + local UI).")
        return True

    def down(self):
        self.local_down()
        self.vpn_down()
        return True

    # -- foreground: Eden lives as long as this process; Ctrl+C, Ctrl+Break or closing the window stop everything
    def foreground(self, once=False):
        stop = {"flag": False}
        pid_file = self.pid_file("eden")
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))

        def handler(signum, frame):
            stop["flag"] = True

        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), handler)
        try:
            if not self.up():
                self.out("start failed")
                return False
            self.out("Eden is running. Close this window (or press Ctrl+C) to stop everything.")
            while not stop["flag"]:
                request = os.path.join(self.run_dir, RESTART_FILE)
                if os.path.exists(request):
                    os.remove(request)
                    self.out("== restarting Eden ==")
                    self.down()
                    if not self.up():
                        self.out("restart failed")
                        return False
                    self.out("Eden restarted.")
                if once:
                    break
                self.sleep(1)
        finally:
            self.down()
            try:
                os.remove(pid_file)
            except OSError:
                pass
        return True


def main(argv):
    launcher = Launcher()
    commands = {"up": launcher.up, "down": launcher.down, "vpn-up": launcher.vpn_up, "vpn-down": launcher.vpn_down,
                "vpn-reload": launcher.vpn_reload, "remote-restart": launcher.remote_restart,
                "local-up": launcher.local_up, "local-down": lambda: launcher.local_down() or True, "status": launcher.status}
    if not argv:
        return 0 if launcher.foreground() else 1
    if argv[0] not in commands:
        print("usage: eden.py [up|down|vpn-up|vpn-down|vpn-reload|remote-restart|local-up|local-down|status]\n"
              "       eden.py (no argument)  - foreground: start everything, stop it all when this window closes")
        return 2
    return 0 if commands[argv[0]]() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
