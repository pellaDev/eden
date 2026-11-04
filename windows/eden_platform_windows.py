# Eden, Windows edition: adapts the Eden local backend (backend/eden_local.py) to Windows WITHOUT editing its Linux code.
# eden_local calls a small, fixed set of functions that are tied to Linux (`ip`, /proc, sysfs, `ss`, sudoedit,
# journalctl, SIGUSR1, the Nord CLI). On Windows, eden_local ends with one hook that calls apply(): the functions below
# replace them by name in eden_local's namespace, and a few routes are replaced in place. Every other line of
# eden_local runs unchanged on both systems. Nothing here is imported by the Linux edition.
# windows/test_eden_platform.py checks, against the real eden_local, that every name replaced here still exists with the
# same parameters, so a rename on the Linux side cannot silently break Windows.
#
# What differs on Windows (all of it is in this file):
#   - the control script is windows/eden.py (not start.sh) and prints the same status lines;
#   - the Meshnet adapter is found by its 100.64.0.0/10 address, not by a fixed interface name;
#   - there is no peer list from Nord: the "peers" are the devices of eden.json, which carry the Meshnet "address"
#     typed by the user; a peer reads "connected" while it has an established connection to this machine;
#   - connections come from psutil: no per-connection byte counters (the table shows them as 0);
#   - the allowed ports are asked from the elevated helper; the file is opened in an elevated Notepad (UAC prompt);
#   - "Restart Eden" writes a request file that the foreground eden.py polls (Windows has no SIGUSR1).

import ipaddress
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eden_winclient as client  # noqa: E402
import eden_winhelper as helper  # noqa: E402

MESH_NET = ipaddress.ip_network("100.64.0.0/10")
HERE = os.path.dirname(os.path.abspath(__file__))
RESTART_FILE = "restart.request"


def _psutil():
    import psutil
    return psutil


def mesh_adapter():
    """(adapter name, address) of the Meshnet adapter, or None while Meshnet is off."""
    try:
        for name, addrs in _psutil().net_if_addrs().items():
            for a in addrs:
                if a.family.name == "AF_INET" and ipaddress.ip_address(a.address) in MESH_NET:
                    return name, a.address
    except Exception:
        pass
    return None


def established_remotes(local_ip):
    """{remote ip: [(remote port, local port)]} of the established TCP connections to this machine's Meshnet address."""
    out = {}
    try:
        for c in _psutil().net_connections(kind="tcp"):
            if c.status == "ESTABLISHED" and c.raddr and c.laddr and c.laddr.ip == local_ip:
                out.setdefault(c.raddr.ip, []).append((c.raddr.port, c.laddr.port))
    except Exception:
        pass
    return out


def apply(ns, app):
    """Replace the Linux-bound functions of eden_local (`ns` = its globals) and routes (`app`) for Windows."""
    from fastapi import HTTPException
    from fastapi.routing import APIRoute

    python = sys.executable

    def run_start(*args, timeout=60):
        r = subprocess.run([python, os.path.join(HERE, "eden.py"), *args], capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ))
        return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}

    def vpn_is_up():
        return mesh_adapter() is not None

    ports_cache = {"t": 0.0, "value": None}

    def allowed_ports():
        if time.monotonic() - ports_cache["t"] < 3:
            return ports_cache["value"]
        try:
            answer = client.call("ports-list")
            value = set(answer["ports"]) if answer.get("ok") else None
        except SystemExit:                 # the helper is not running: report "unknown", like Linux does
            value = None
        ports_cache.update(t=time.monotonic(), value=value)
        return value

    def pid_running(pid_file, needle):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            line = " ".join(_psutil().Process(pid).cmdline())
        except Exception:
            return None
        return pid if needle.decode("utf-8", "replace") in line else None

    def foreground_pid():
        return pid_running(ns["EDEN_PID_FILE"], b"eden.py")

    def mesh_ip():
        adapter = mesh_adapter()
        return adapter[1] if adapter else None

    def iface_address(iface):
        return mesh_ip()

    def iface_counters(iface):
        adapter = mesh_adapter()
        if adapter is None:
            return None
        try:
            c = _psutil().net_io_counters(pernic=True)[adapter[0]]
            return c.bytes_recv, c.bytes_sent
        except Exception:
            return None

    def helper_journal(n):
        path = os.path.join(helper.data_dir(), "helper.log")
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[-n:]
        except OSError:
            return []

    def live_peers():
        """The configured devices as peers (there is no peer list on Windows). None while Meshnet is off."""
        adapter = mesh_adapter()
        if adapter is None:
            return None
        remotes = established_remotes(adapter[1])
        peers = []
        for d in ns["read_config"]().get("devices", []):
            addr = d.get("address")
            peers.append({"nickname": d["name"], "hostname": "", "ip": addr or "", "public_key": d.get("public_key") or f"addr:{addr}",
                          "status": "connected" if addr in remotes else "disconnected", "external": False,
                          "allow_in": False, "allows_in": False})
        return peers

    def build_monitor():
        now = time.time()
        adapter = mesh_adapter()
        counters = iface_counters(None)
        if adapter is None or counters is None:
            return {"vpn_up": False, "t": now}
        ip = adapter[1]
        snap = {"vpn_up": True, "t": now, "mesh_ip": ip, "rx_bytes": counters[0], "tx_bytes": counters[1],
                "connections": None, "truncated": False}
        sockets = [{"local_ip": ip, "local_port": lp, "remote_ip": rip, "remote_port": rp}
                   for rip, pairs in established_remotes(ip).items() for rp, lp in pairs]
        snap["connections"], snap["truncated"] = ns["build_connections"](sockets, ip, ns["read_config"]())
        return snap

    for fn in (run_start, vpn_is_up, allowed_ports, pid_running, foreground_pid, mesh_ip, iface_address, iface_counters,
               helper_journal, live_peers, build_monitor):
        ns[fn.__name__] = fn
    ns["ALLOWED_PORTS_FILE"] = os.path.join(helper.data_dir(), "allowed_ports")

    # -- routes replaced in place (the handler is bound when the route is declared, so the name cannot be swapped)
    def open_allowed_ports():
        """Open the allowed-ports file in Notepad with administrator rights (the user answers the UAC prompt)."""
        path = ns["ALLOWED_PORTS_FILE"]
        try:
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Process", "notepad.exe", "-ArgumentList",
                              f"'{path}'", "-Verb", "RunAs"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError:
            raise HTTPException(502, ns["say"]("terminal_open_failed", file=path))
        return {"ok": True, "terminal": "notepad"}

    def restart_eden():
        if foreground_pid() is None:
            raise HTTPException(409, ns["say"]("restart_unavailable"))
        path = os.path.join(ns["EDEN_RUN"], RESTART_FILE)
        # After the answer has gone out: this very process is one of the things the restart stops.
        threading.Timer(0.5, lambda: open(path, "w").close()).start()
        return {"ok": True}

    def get_vpn_settings():
        """There are no Nord settings to read on Windows: the user manages them in the Nord app."""
        return {"settings": None}

    def get_platform():
        """Which edition this is: the UI hides the pages that exist on Linux only and words the file texts for Windows."""
        return {"platform": "windows", "session": False, "version": ns["read_version"]()}

    for path, method, fn in (("/api/allowed-ports/open", "POST", open_allowed_ports), ("/api/restart", "POST", restart_eden),
                             ("/api/vpn/settings", "GET", get_vpn_settings), ("/api/platform", "GET", get_platform)):
        for i, route in enumerate(app.router.routes):
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                app.router.routes[i] = APIRoute(path, fn, methods=[method])
                break
        else:
            raise RuntimeError(f"eden_platform_windows: route {method} {path} not found in eden_local")

    # -- add a device by its Meshnet address (Windows has no peer list to pick from)
    class AddByAddressBody(ns["BaseModel"]):
        address: str
        name: str | None = None

    def add_device_by_address(body: AddByAddressBody):
        """Add a device typed by address. Created disabled, UNTRUSTED and with no grants, like on Linux."""
        try:
            ip = ipaddress.IPv4Address(body.address.strip())
        except ValueError:
            raise HTTPException(400, ns["say"]("address_invalid"))
        if ip not in MESH_NET:
            raise HTTPException(400, ns["say"]("address_invalid"))
        name = (body.name or "").strip().lower() or "device-" + "-".join(str(ip).split(".")[2:])
        if not ns["SERVICE_NAME_RE"].fullmatch(name):
            raise HTTPException(400, ns["say"]("device_name_invalid"))

        def mutate(cfg):
            for d in cfg["devices"]:
                if d.get("address") == str(ip):
                    raise HTTPException(409, ns["say"]("address_exists"))
                if d["name"] == name:
                    raise HTTPException(409, ns["say"]("device_name_taken", name=name))
            cfg["devices"].append({"name": name, "public_key": f"addr:{ip}", "address": str(ip), "enabled": False,
                                   "services": [], "untrusted": True})
        return ns["apply_change"](mutate)

    app.router.routes.append(APIRoute("/api/devices/by-address", add_device_by_address, methods=["POST"]))

    # The UI shows an address form instead of the peer list when this flag is set.
    real_devices_state = ns["devices_state"]

    def devices_state(cfg, peers):
        return {**real_devices_state(cfg, peers), "by_address": True}
    ns["devices_state"] = devices_state

    # The Dev tree may still carry the remote browser session routes (stripped from the release): they cannot work here.
    app.router.routes[:] = [r for r in app.router.routes if not str(getattr(r, "path", "")).startswith("/api/session")]

    # Eden cannot tell a device of another account from your own here: the user decides, so nothing is external.


# Names this module replaces in eden_local: the test compares them with the real module.
REPLACED_FUNCTIONS = ("run_start", "vpn_is_up", "allowed_ports", "pid_running", "foreground_pid", "mesh_ip", "iface_address",
                      "iface_counters", "helper_journal", "live_peers", "build_monitor", "devices_state")
REPLACED_ROUTES = (("/api/allowed-ports/open", "POST"), ("/api/restart", "POST"), ("/api/vpn/settings", "GET"),
                   ("/api/platform", "GET"))
