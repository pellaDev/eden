# Eden, Windows edition: the elevated helper. The only Eden process that runs with administrator rights. It has a
# FIXED command set, receives only validated parameters (ports and Meshnet addresses), never rule text or shell text,
# builds every PowerShell command itself from eden_winfw, and stores nothing. The rest of Eden runs as the normal user
# and asks it through a named pipe (eden_winclient.py). Standard library only; nothing of it is imported by the Linux
# edition. It is the counterpart of the Linux root helper (eden_helper.py), kept separate on purpose.
#
# Started on demand (never at boot) by a scheduled task that runs with the highest privileges, created once by the
# install script (W5); the task runs:  python eden_winhelper.py serve
# Files (created by the install script, the folder is writable by administrators only):
#   %ProgramData%\Eden\allowed_ports   ports Eden may open, one per line ("#" starts a comment); the helper refuses to
#                                      work if anyone but administrators can write to it (fail closed)
#   %ProgramData%\Eden\helper.key      shared secret of the pipe, readable by the installing user and administrators
#   %ProgramData%\Eden\helper.log      what the helper did (appended)
#
# Commands (one dict per request: {"cmd": ..., ...}; the answer is {"ok": true, ...} or {"ok": false, "error": text}):
#   ping                               alive; returns the Meshnet adapter name and address (or null when Meshnet is off)
#   ports-list                         the ports Eden may open
#   apply  pairs=[[port, "ip"], ...]   make exactly these (port, address) pairs reachable: the "up" rule set
#   guard                              block everything from the Meshnet adapter (Eden down, or any failure)
#   remove                             remove every Eden rule (uninstall)
#   list                               names of the Eden rules that exist

import ipaddress
import json
import os
import re
import subprocess
import sys
import threading
import time
from multiprocessing import connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eden_winfw as fw  # noqa: E402

PIPE = r"\\.\pipe\eden-helper"
DEFAULT_ALLOWED_PORTS = (8443,)   # Eden remote (login + TOTP); everything else must be listed in the file
MAX_ALLOWED_PORTS = 64
MAX_PAIRS = 256
MESH_NET = ipaddress.ip_network("100.64.0.0/10")
DEFAULT_ALIAS = "NordLynx"        # used by the guard when Meshnet is off and no adapter can be found
SAFE_PRINCIPALS = ("NT AUTHORITY\\SYSTEM", "BUILTIN\\ADMINISTRATORS", "NT SERVICE\\TRUSTEDINSTALLER")
READ_ONLY_RIGHTS = {"R", "RX", "GR", "GE", "RC", "S", "REA", "RA", "X", "RD"}
INHERIT_FLAGS = {"I", "OI", "CI", "IO", "NP"}


class HelperError(Exception):
    """A request that must be refused; the text goes back to the caller."""


def data_dir(env=None):
    env = env if env is not None else os.environ
    base = env.get("EDEN_WIN_DATA") or os.path.join(env.get("ProgramData", r"C:\ProgramData"), "Eden")
    return base


def log(text, env=None):
    try:
        with open(os.path.join(data_dir(env), "helper.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")
    except OSError:
        pass   # a log that cannot be written must not stop a protective action


# ---- allowed ports file ----------------------------------------------------------------------------------------
def acl_problem(icacls_output, path=None):
    """Why the file is unsafe, or None. `icacls_output` is the text of `icacls <file>`: one line per ACE, like
    "NT AUTHORITY\\SYSTEM:(F)" or "BUILTIN\\Users:(I)(R)". Anyone but SYSTEM, Administrators and TrustedInstaller may
    only have read rights; anything else (write, modify, full, delete, ownership) or a line that cannot be read is
    unsafe: fail closed."""
    found = False
    for raw in icacls_output.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("successfully processed"):
            continue
        if path and line.startswith(path):
            line = line[len(path):].strip()   # the first line starts with the file's own path
        # What is left is "<principal>:(<rights>)(<rights>)..."
        m = re.fullmatch(r"(.+?):((?:\([A-Za-z,]+\))+)", line)
        if not m:
            return f"cannot read the ACL line: {line}"
        principal = m.group(1).strip()
        found = True
        if principal.upper() in SAFE_PRINCIPALS:
            continue
        for group in re.findall(r"\(([A-Za-z,]+)\)", m.group(2)):
            for right in group.split(","):
                if right in INHERIT_FLAGS:
                    continue
                if right not in READ_ONLY_RIGHTS:
                    return f"{principal} has the right {right}"
    return None if found else "the ACL is empty"


def read_allowed_ports(path, icacls_output):
    """The set of ports from the file. File missing = the default only; present but unsafe or malformed = error."""
    if not os.path.exists(path):
        return frozenset(DEFAULT_ALLOWED_PORTS)
    problem = acl_problem(icacls_output, path)
    if problem:
        raise HelperError(f"{path} is not safe: {problem}")
    ports = set()
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not re.fullmatch(r"\d{1,5}", line) or not 1 <= int(line) <= 65535:
            raise HelperError(f"{path}:{n}: not a port: {line!r}")
        ports.add(int(line))
    if len(ports) > MAX_ALLOWED_PORTS:
        raise HelperError(f"{path}: more than {MAX_ALLOWED_PORTS} ports")
    return frozenset(ports)


# ---- the system side (replaceable in tests) -------------------------------------------------------------------
def run_powershell(script):
    """Runs a PowerShell script (text given on stdin, so nothing is quoted); returns (returncode, output)."""
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", "-"],
                       input=script, capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def run_icacls(path):
    r = subprocess.run(["icacls.exe", path], capture_output=True, text=True, timeout=30)
    return r.stdout


class Helper:
    def __init__(self, ps=run_powershell, icacls=run_icacls, env=None, clock=time.time):
        self.ps, self.icacls, self.env, self.clock = ps, icacls, env, clock
        self.lock = threading.Lock()   # one change at a time

    # -- helpers
    def ports_file(self):
        return os.path.join(data_dir(self.env), "allowed_ports")

    def allowed(self):
        path = self.ports_file()
        return read_allowed_ports(path, self.icacls(path) if os.path.exists(path) else "")

    def mesh_adapter(self):
        """(alias, address) of the Meshnet adapter, or None while Meshnet is off. Found by its 100.64.0.0/10 address."""
        rc, out = self.ps("Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '100.*' } | "
                          "ForEach-Object { \"$($_.InterfaceAlias)|$($_.IPAddress)\" }")
        for line in out.splitlines():
            alias, _, addr = line.strip().partition("|")
            try:
                if rc == 0 and alias and ipaddress.ip_address(addr) in MESH_NET:
                    return alias, addr
            except ValueError:
                continue
        return None

    def powershell_set(self, rules, alias):
        gen = time.strftime("%H%M%S", time.localtime(self.clock())) + f"{int(self.clock() * 1000) % 1000:03d}"
        script = (fw.APPLY_FUNCTION + "\n$ErrorActionPreference = 'Stop'\n$rules = " + fw.render_rules(rules) +
                  f"\nSet-EdenRules -Generation '{gen}' -Rules $rules -Alias '{alias}'\n")
        rc, out = self.ps(script)
        if rc:
            raise HelperError(f"PowerShell failed: {out[-400:]}")

    def validate_pairs(self, pairs):
        if not isinstance(pairs, list) or len(pairs) > MAX_PAIRS:
            raise HelperError(f"pairs: a list of at most {MAX_PAIRS} items")
        allowed, clean = self.allowed(), set()
        for item in pairs:
            if not (isinstance(item, (list, tuple)) and len(item) == 2):
                raise HelperError("pairs: each item is [port, address]")
            port, ip = item
            if isinstance(port, bool) or not isinstance(port, int) or port not in allowed:
                raise HelperError(f"port {port!r} is not in the allowed ports")
            try:
                addr = ipaddress.IPv4Address(ip)
            except (ValueError, TypeError):
                raise HelperError(f"address {ip!r} is not an IPv4 address") from None
            if addr not in MESH_NET:
                raise HelperError(f"address {ip} is outside the Meshnet range {MESH_NET}")
            clean.add((port, str(addr)))
        return clean

    # -- commands
    def handle(self, request):
        with self.lock:
            try:
                return self._handle(request)
            except HelperError as e:
                log(f"REFUSED {request.get('cmd') if isinstance(request, dict) else '?'}: {e}", self.env)
                return {"ok": False, "error": str(e)}
            except Exception as e:   # anything unexpected: say so, and do not leave the machine less protected
                log(f"ERROR {e!r}", self.env)
                return {"ok": False, "error": f"helper error: {e}"}

    def _handle(self, request):
        if not isinstance(request, dict) or not isinstance(request.get("cmd"), str):
            raise HelperError("a request is {\"cmd\": ...}")
        cmd = request["cmd"]
        if cmd == "ping":
            adapter = self.mesh_adapter()
            return {"ok": True, "adapter": adapter[0] if adapter else None, "address": adapter[1] if adapter else None}
        if cmd == "ports-list":
            return {"ok": True, "ports": sorted(self.allowed())}
        if cmd == "list":
            rc, out = self.ps("Get-NetFirewallRule -Group 'Eden' -ErrorAction SilentlyContinue | "
                              "Select-Object -ExpandProperty DisplayName")
            return {"ok": True, "rules": [x for x in out.splitlines() if x.strip()]}
        if cmd == "apply":
            pairs = self.validate_pairs(request.get("pairs"))
            adapter = self.mesh_adapter()
            if adapter is None:
                raise HelperError("Meshnet is off: no adapter with a 100.64.0.0/10 address")
            self.powershell_set(fw.up_rules(pairs), adapter[0])
            log(f"apply {sorted(pairs)} on {adapter[0]}", self.env)
            return {"ok": True, "applied": len(pairs)}
        if cmd == "guard":
            adapter = self.mesh_adapter()
            self.powershell_set(fw.guard_rules(), adapter[0] if adapter else DEFAULT_ALIAS)
            log("guard", self.env)
            return {"ok": True}
        if cmd == "remove":
            rc, out = self.ps(fw.APPLY_FUNCTION + "\nRemove-EdenRules\n")
            if rc:
                raise HelperError(f"PowerShell failed: {out[-400:]}")
            log("remove", self.env)
            return {"ok": True}
        raise HelperError(f"unknown command {cmd!r}")


def read_key(env=None):
    with open(os.path.join(data_dir(env), "helper.key"), "rb") as f:
        key = f.read().strip()
    if len(key) < 32:
        raise HelperError("helper.key is too short")
    return key


def serve(address=PIPE, family=None, key=None, helper=None, stop=None):
    """Answer requests until `stop` (a threading.Event) is set, or forever. One request per connection."""
    helper = helper or Helper()
    key = key or read_key(helper.env)
    family = family or ("AF_PIPE" if os.name == "nt" else "AF_UNIX")
    with connection.Listener(address, family, authkey=key) as listener:
        while not (stop and stop.is_set()):
            try:
                with listener.accept() as conn:
                    request = conn.recv()
                    conn.send(helper.handle(request))
            except (connection.AuthenticationError, EOFError, OSError):
                continue   # a wrong key or a dropped client: next one


if __name__ == "__main__":
    if sys.argv[1:] == ["serve"]:
        serve()
    else:
        sys.exit("usage: eden_winhelper.py serve")
