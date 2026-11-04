#!/usr/bin/env python3
#
# Eden local: loopback-only admin backend. Serves the built webui (webui/dist)
# and a small JSON API wrapping start.sh / eden_ctl.py. No Meshnet exposure -
# this process must never bind anything but 127.0.0.1.

import base64
import binascii
import ipaddress
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

def env(name):
    v = os.environ.get(name)
    if not v:
        sys.exit(f"eden_local: {name} is not set (run through start.sh)")
    return v

EDEN_HOME = env("EDEN_HOME")
EDEN_CONFIG = env("EDEN_CONFIG")
EDEN_CTL = os.path.join(EDEN_HOME, "bin", "eden_ctl", "eden_ctl.py")


def read_version():
    """The one place the version lives: the VERSION file at the root of the Eden folder."""
    try:
        with open(os.path.join(EDEN_HOME, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or "?"
    except OSError:
        return "?"

MESH_IFACE = env("MESH_IFACE")
EDEN_LOGS = env("EDEN_LOGS")
EDEN_SECRETS = env("EDEN_SECRETS")
EDEN_RUN = env("EDEN_RUN")
EDEN_HELPER = env("EDEN_HELPER")      # the root helper: also the source of truth for the allowed ports
EDEN_AVATARS = env("EDEN_AVATARS")    # {service name: data URL}, kept out of eden.json
# Must match eden_remote: the two files that make up "enrolled", and the window file.
SECRET_FILES = ("password.hash", "totp.secret")
ENROLL_WINDOW_FILE = os.path.join(EDEN_RUN, "enroll_window")
ENROLL_WINDOW_SECONDS = 10 * 60
START_SH = os.path.join(EDEN_HOME, "start.sh")
DIST = os.path.join(EDEN_HOME, "webui", "dist")

# E-mail alerts (shared with eden_remote). It reads EDEN_CONFIG / EDEN_SECRETS / EDEN_RUN from the environment.
sys.path.insert(0, os.path.join(EDEN_HOME, "bin", "eden_notify"))
import eden_notify as notify  # noqa: E402

# Traffic history for the Home chart (a sibling module: uvicorn loads this file as backend.eden_local).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eden_i18n  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from eden_policy import flag_untrusted  # noqa: E402  (shared with the Windows edition)
import eden_monitor  # noqa: E402

app = FastAPI(title="Eden local")


def run_start(*args, timeout=60):
    r = subprocess.run([START_SH, *args], capture_output=True, text=True, timeout=timeout)
    return {"ok": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}


@app.get("/api/status")
def status():
    r = run_start("status", timeout=15)
    return r


@app.post("/api/vpn/up")
def vpn_up():
    return lifecycle("vpn-up", timeout=60)


@app.post("/api/vpn/down")
def vpn_down():
    return lifecycle("vpn-down", timeout=60)


# Which edition this is and which optional pages exist: the UI asks once and hides what is not there.
SESSION_FEATURE = False


@app.get("/api/platform")
def get_platform():
    return {"platform": "linux", "session": SESSION_FEATURE, "version": read_version()}




# ---- config/eden.json access -------------------------------------------------
# Endpoints run in FastAPI's threadpool: one lock serializes every
# read-modify-write cycle so concurrent toggles cannot overwrite each other.
_cfg_lock = threading.Lock()


DEFAULT_CONFIG = {"remote_port": 8443, "services": [], "devices": []}   # a fresh install: nothing exposed, nothing known


def read_config():
    try:
        with open(EDEN_CONFIG) as f:
            return json.load(f)
    except FileNotFoundError:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def write_config(cfg):
    """Atomic write: temp file in the same directory, then os.replace, so a crash
    can never leave a truncated eden.json."""
    d = os.path.dirname(EDEN_CONFIG)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".eden.json.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp, EDEN_CONFIG)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ui_language():
    """Language of the UI (and of the messages the API sends back), read without the config lock: the callers that fail
    inside a locked section would deadlock otherwise. A config that cannot be read means the default."""
    try:
        ui = read_config().get("ui")
        lang = ui.get("language") if isinstance(ui, dict) else None
    except (OSError, ValueError):
        lang = None
    return lang if lang in eden_i18n.LANGUAGES else eden_i18n.DEFAULT_LANGUAGE


def say(key, **fields):
    return eden_i18n.message(ui_language(), key, **fields)


def vpn_is_up():
    try:
        r = subprocess.run(["ip", "-br", "addr", "show", MESH_IFACE], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False   # cannot tell: report "down" rather than failing the whole request
    return r.returncode == 0




# ---- allowed ports (root helper) ---------------------------------------------------
# The ports Eden may open are listed in a root-owned file read by the helper. Asking the helper keeps a
# single source of truth (including its fallback when the file is missing); this process can show the
# list but never change it.
ALLOWED_PORTS_FILE = "/etc/eden/allowed_ports"   # must match PORTS_FILE in the root helper (used for messages and "Apri file")
_ports_cache = (0.0, None)


def allowed_ports():
    """Set of ports the helper accepts, or None when they cannot be read. Cached for a few seconds."""
    global _ports_cache
    ts, value = _ports_cache
    if time.monotonic() - ts < 3:
        return value
    try:
        r = subprocess.run(["sudo", "-n", EDEN_HELPER, "ports-list"], capture_output=True, text=True, timeout=10)
        value = {int(x) for x in r.stdout.split()} if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        value = None
    _ports_cache = (time.monotonic(), value)
    return value


# ---- edit the allowed-ports file ------------------------------------------------------
# The file is root-owned on purpose (the helper refuses one that others can write), so opening it with the
# desktop's default app would only give a read-only view. "sudoedit" is the right tool: it copies the file to a
# temp file owned by the user, runs the editor, and installs it back as root when the editor closes, asking for
# the sudo password in the terminal. The command is fixed: nothing from the request reaches it.
EDEN_TERMINAL = os.environ.get("EDEN_TERMINAL", "")            # optional terminal prefix, e.g. "gnome-terminal --"
EDEN_PORTS_EDITOR = os.environ.get("EDEN_PORTS_EDITOR", "")    # optional: becomes SUDO_EDITOR for sudoedit


def terminal_commands(cmd):
    """Terminal invocations to try, in order; each runs `cmd` in a new window."""
    if EDEN_TERMINAL.strip():
        return [[*shlex.split(EDEN_TERMINAL), *cmd]]
    line = shlex.join(cmd)
    candidates = [["ptyxis", "--", *cmd], ["ptyxis", "-x", line], ["gnome-terminal", "--", *cmd],
                  ["kgx", "-e", line], ["konsole", "-e", *cmd], ["xfce4-terminal", "-x", *cmd], ["xterm", "-e", *cmd]]
    return [c for c in candidates if shutil.which(c[0])]


@app.post("/api/allowed-ports/open")
def open_allowed_ports():
    """Open /etc/eden/allowed_ports in a terminal with sudoedit, so the user edits it with an editor of their choice."""
    cmd = ["sudoedit", ALLOWED_PORTS_FILE]
    child_env = dict(os.environ)
    if EDEN_PORTS_EDITOR:
        child_env["SUDO_EDITOR"] = EDEN_PORTS_EDITOR
    for argv in terminal_commands(cmd):
        try:
            proc = subprocess.Popen(argv, env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            continue
        try:
            rc = proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            return {"ok": True, "terminal": argv[0]}       # still running: the terminal window is open
        if rc == 0:
            return {"ok": True, "terminal": argv[0]}       # some terminals hand over to a server process and exit
        # non-zero right away: wrong syntax for this terminal, or no display; try the next one
    raise HTTPException(502, say("terminal_open_failed", file=ALLOWED_PORTS_FILE))


# ---- service avatars -----------------------------------------------------------------
# A small {service name: data URL} map in its own file, so eden.json stays hand-editable. The browser already
# crops and shrinks the picture; it is validated here anyway (type, size, magic bytes).
AVATAR_MAX_CHARS = 64 * 1024
AVATAR_RE = re.compile(r"data:image/(webp|png|jpeg|gif);base64,([A-Za-z0-9+/]+={0,2})")
AVATAR_MAGIC = {"webp": b"RIFF", "png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff", "gif": b"GIF8"}
_avatar_lock = threading.Lock()


def valid_avatar(data_url):
    """True for a small base64 data URL of a real PNG/JPEG/WebP/GIF (checked by magic bytes)."""
    if not isinstance(data_url, str) or len(data_url) > AVATAR_MAX_CHARS:
        return False
    m = AVATAR_RE.fullmatch(data_url)
    if not m:
        return False
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        return False
    if not raw.startswith(AVATAR_MAGIC[m.group(1)]):
        return False
    return m.group(1) != "webp" or raw[8:12] == b"WEBP"


def read_avatars():
    try:
        with open(EDEN_AVATARS) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def update_avatars(mutate):
    """Read-modify-write of the avatar map under its own lock, atomic like write_config."""
    with _avatar_lock:
        data = read_avatars()
        mutate(data)
        d = os.path.dirname(EDEN_AVATARS)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".avatars.json.")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp, EDEN_AVATARS)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


DEVICE_KEY = "device:"   # device pictures share avatars.json with the services' ones; ":" cannot occur in a service name
FORWARD_MIN_PORT = 1024  # the forwarder runs as the normal user: unprivileged ports only
EDEN_PID_FILE = os.path.join(EDEN_RUN, "eden.pid")
FORWARD_STATUS_FILE = os.path.join(EDEN_RUN, "forward.status.json")


def avatar_of(avatars, key):
    value = avatars.get(key)
    return value if valid_avatar(value) else None


def pid_running(pid_file, needle):
    """PID from `pid_file` if /proc confirms it is a process whose command line contains `needle`
    (a stale pid file must never make us trust, or signal, an unrelated process); otherwise None."""
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return pid if needle in f.read() else None
    except (OSError, ValueError):
        return None


def foreground_pid():
    """The foreground start.sh that holds Eden up (foreground mode), or None."""
    return pid_running(EDEN_PID_FILE, b"start.sh")


def read_forward_status():
    try:
        with open(FORWARD_STATUS_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cfg_untrusted(dev):
    """The device's untrusted flag in the config, with the same fail-closed rule as eden_ctl.is_untrusted: anything
    but false (true, null, garbage) means untrusted; a missing flag is a trusted device from before the feature.
    A peer that Nord lists as external is untrusted whatever this says; that part needs the live peer list."""
    return flag_untrusted(dev)


def services_state(cfg):
    avatars, allowed = read_avatars(), allowed_ports()
    fwd_alive = pid_running(os.path.join(EDEN_RUN, "eden_forward.pid"), b"eden_forward.py") is not None
    fwd_routes = read_forward_status().get("routes", {}) if fwd_alive else {}

    def forward_status(s):
        # None: not a forwarded service, or the forwarder is not running (VPN down). "idle": no route right now
        # (service off, or no enabled device granted). Otherwise what the forwarder reports: listening / error.
        if not s.get("forward") or not fwd_alive:
            return None
        return fwd_routes.get(str(s["port"])) or {"state": "idle"}

    up = vpn_is_up()
    return {
        "vpn_up": up,
        # This computer's own Meshnet address, read from the interface: it is assigned by Nord, never typed in. None while the VPN is down.
        "mesh_ip": mesh_ip() if up else None,
        "services": [{"name": s["name"], "port": s["port"], "enabled": bool(s.get("enabled")),
                      "note": s.get("note", ""), "avatar": avatar_of(avatars, s["name"]),
                      "forward": bool(s.get("forward")), "forward_status": forward_status(s),
                      # None = could not ask the helper; the helper enforces the list anyway
                      "port_allowed": None if allowed is None else s["port"] in allowed}
                     for s in cfg.get("services", [])],
        "devices": [{"name": d["name"], "enabled": bool(d.get("enabled", True)),
                     "services": list(d.get("services", [])), "avatar": avatar_of(avatars, DEVICE_KEY + d["name"]),
                     "untrusted": cfg_untrusted(d)}
                    for d in cfg.get("devices", [])],
    }


def find(items, name, what):
    for i in items:
        if i["name"] == name:
            return i
    raise HTTPException(404, f"unknown {what}: {name}")


def apply_change(mutate):
    if not _ops_lock.acquire(blocking=False):
        raise HTTPException(409, say("busy"))
    try:
        return _apply_change(mutate)
    finally:
        _ops_lock.release()


def _apply_change(mutate):
    """Load config, apply `mutate`, save, then vpn-reload. If the reload fails the
    previous config is restored, so the UI never shows a state the rules don't have."""
    with _cfg_lock:
        old = read_config()
        new = json.loads(json.dumps(old))
        mutate(new)
        write_config(new)
        r = run_start("vpn-reload", timeout=60)
        if not r["ok"]:
            write_config(old)
            run_start("vpn-reload", timeout=60)   # best effort: bring live rules back in line with the restored config
            raise HTTPException(502, f"vpn-reload failed, change reverted: {(r['stderr'] or r['stdout']).strip()}")
        return {**services_state(new), "applied": "RELOAD: applied" in r["stdout"]}


class EnabledBody(BaseModel):
    enabled: bool


class GrantBody(BaseModel):
    granted: bool


@app.get("/api/services")
def get_services():
    with _cfg_lock:
        return services_state(read_config())


SERVICE_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
NOTE_MAX = 120


class NewServiceBody(BaseModel):
    name: str
    port: int
    note: str = ""
    avatar: str | None = None
    forward: bool = False     # the service listens only on 127.0.0.1: Eden forwards the Meshnet address to it


class EditServiceBody(BaseModel):
    # Partial update: every field is optional (the card's "Inoltro" switch sends just "forward").
    name: str | None = None
    port: int | None = None
    note: str | None = None
    forward: bool | None = None
    avatar: str | None = None      # a new picture (data URL)
    clear_avatar: bool = False     # remove the picture; with neither, the picture is kept


class ServiceOrderBody(BaseModel):
    names: list[str]


@app.post("/api/services-order")
def order_services(body: ServiceOrderBody):
    """Save the order of the service cards: the order of the `services` array in eden.json. It changes nothing
    on the firewall, so there is no vpn-reload and no ops lock (like /api/settings). 409 when the list does not
    match the services that exist now (one was added or removed meanwhile): the page reloads and retries."""
    with _cfg_lock:
        cfg = read_config()
        by_name = {s["name"]: s for s in cfg.get("services", [])}
        if len(body.names) != len(set(body.names)) or set(body.names) != set(by_name):
            raise HTTPException(409, say("services_changed"))
        cfg["services"] = [by_name[n] for n in body.names]
        write_config(cfg)
        return services_state(cfg)


@app.post("/api/services")
def add_service(body: NewServiceBody):
    """Create a service, always off. Its port only opens if the root helper allows it (ports file)."""
    name, note = body.name, body.note.strip()
    if not SERVICE_NAME_RE.fullmatch(name):
        raise HTTPException(400, say("service_name_invalid"))
    if not 1 <= body.port <= 65535:
        raise HTTPException(400, say("port_range"))
    if len(note) > NOTE_MAX:
        raise HTTPException(400, say("note_too_long", max=NOTE_MAX))
    if body.avatar is not None and not valid_avatar(body.avatar):
        raise HTTPException(400, say("avatar_invalid"))
    if body.forward and body.port < FORWARD_MIN_PORT:
        raise HTTPException(400, say("forward_min_port", min=FORWARD_MIN_PORT))

    def mutate(cfg):
        services = cfg.setdefault("services", [])
        if any(s["name"] == name for s in services):
            raise HTTPException(409, say("service_exists", name=name))
        if body.port == cfg.get("remote_port"):
            raise HTTPException(409, say("port_is_remote", port=body.port))
        clash = next((s["name"] for s in services if s["port"] == body.port), None)
        if clash:
            raise HTTPException(409, say("port_in_use", port=body.port, service=clash))
        services.append({"name": name, "port": body.port, "enabled": False, "note": note,
                         **({"forward": True} if body.forward else {})})

    result = apply_change(mutate)
    # The picture is saved only once the service exists, so a rejected request leaves no orphan entry.
    update_avatars(lambda data: data.__setitem__(name, body.avatar) if body.avatar else data.pop(name, None))
    with _cfg_lock:
        return {**services_state(read_config()), "applied": result["applied"]}


@app.post("/api/services/{name}/edit")
def edit_service(name: str, body: EditServiceBody):
    """Partial update of a service. Changing the port turns the service off: a new port is a new exposure and
    must be switched on again on purpose. Renaming carries the device grants and the picture along."""
    new_name = name if body.name is None else body.name
    note = None if body.note is None else body.note.strip()
    if not SERVICE_NAME_RE.fullmatch(new_name):
        raise HTTPException(400, say("service_name_invalid"))
    if body.port is not None and not 1 <= body.port <= 65535:
        raise HTTPException(400, say("port_range"))
    if note is not None and len(note) > NOTE_MAX:
        raise HTTPException(400, say("note_too_long", max=NOTE_MAX))
    if body.avatar is not None and not valid_avatar(body.avatar):
        raise HTTPException(400, say("avatar_invalid"))

    def mutate(cfg):
        services = cfg.get("services", [])
        svc = find(services, name, "service")
        if new_name != name and any(s["name"] == new_name for s in services):
            raise HTTPException(409, say("service_exists", name=new_name))
        if body.port is not None and body.port != svc["port"]:
            if body.port == cfg.get("remote_port"):
                raise HTTPException(409, say("port_is_remote", port=body.port))
            clash = next((s["name"] for s in services if s is not svc and s["port"] == body.port), None)
            if clash:
                raise HTTPException(409, say("port_in_use", port=body.port, service=clash))
            svc["port"] = body.port
            svc["enabled"] = False
        if note is not None:
            svc["note"] = note
        if body.forward is True:
            svc["forward"] = True
        elif body.forward is False:
            svc.pop("forward", None)
        if svc.get("forward") and svc["port"] < FORWARD_MIN_PORT:
            raise HTTPException(400, say("forward_min_port_hint", min=FORWARD_MIN_PORT))
        if new_name != name:
            svc["name"] = new_name
            for dev in cfg.get("devices", []):
                dev["services"] = [new_name if x == name else x for x in dev.get("services", [])]

    result = apply_change(mutate)

    def update_avatar(data):
        if new_name != name:
            moved = data.pop(name, None)
            data.pop(new_name, None)           # never inherit a stale picture of an old service with that name
            if moved:
                data[new_name] = moved
        if body.avatar:
            data[new_name] = body.avatar
        elif body.clear_avatar:
            data.pop(new_name, None)
    update_avatars(update_avatar)
    with _cfg_lock:
        return {**services_state(read_config()), "applied": result["applied"]}


@app.delete("/api/services/{name}")
def delete_service(name: str):
    """Remove a service, its card picture and every device grant on it; the reload closes its port."""
    def mutate(cfg):
        find(cfg.get("services", []), name, "service")
        cfg["services"] = [s for s in cfg["services"] if s["name"] != name]
        for d in cfg.get("devices", []):
            d["services"] = [x for x in d.get("services", []) if x != name]
    result = apply_change(mutate)
    update_avatars(lambda data: data.pop(name, None))
    return result


@app.post("/api/services/{name}")
def set_service(name: str, body: EnabledBody):
    def mutate(cfg):
        svc = find(cfg.get("services", []), name, "service")
        if body.enabled:
            allowed = allowed_ports()
            if allowed is not None and svc["port"] not in allowed:
                raise HTTPException(409, say("port_not_allowed", port=svc['port'], file=ALLOWED_PORTS_FILE))
        svc["enabled"] = body.enabled
    result = apply_change(mutate)
    if body.enabled:
        notify.event("access_widened", detail=say("ev_service_on", name=name))
    return result


@app.post("/api/devices/{device}/services/{service}")
def set_grant(device: str, service: str, body: GrantBody):
    def mutate(cfg):
        svc = find(cfg.get("services", []), service, "service")   # validates the name
        dev = find(cfg.get("devices", []), device, "device")
        granted = [x for x in dev.get("services", []) if x != service]
        if body.granted:
            if cfg_untrusted(dev) and svc["port"] == cfg.get("remote_port"):
                # Never, by design: the remote-login port is not for an untrusted device (eden_ctl refuses it too).
                raise HTTPException(409, say("untrusted_remote_port", port=svc['port']))
            granted.append(service)
        dev["services"] = granted
    result = apply_change(mutate)
    if body.granted:
        notify.event("access_widened", detail=say("ev_device_service", device=device, service=service))
    return result


# ---- lifecycle / status ---------------------------------------------------------
# One lock serializes every start.sh action that changes state (vpn/session up/down,
# vpn-reload from config changes): they must never interleave.
_ops_lock = threading.Lock()
STATUS_RE = re.compile(r"^([A-Za-z0-9_]+): (running|stopped|up|down)\b")


def lifecycle(*args, timeout):
    if not _ops_lock.acquire(blocking=False):
        raise HTTPException(409, say("busy"))
    try:
        return run_start(*args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": say("lifecycle_timeout", action=args[0], seconds=timeout)}
    finally:
        _ops_lock.release()


def parse_status():
    """{name: bool} from the 'name: running|stopped|up|down' lines of `start.sh status`."""
    try:
        out = run_start("status", timeout=15)["stdout"]
    except subprocess.TimeoutExpired:
        return {}
    return {m.group(1): m.group(2) in ("running", "up")
            for m in map(STATUS_RE.match, out.splitlines()) if m}


def mesh_ip():
    try:
        r = subprocess.run(["ip", "-4", "-br", "addr", "show", MESH_IFACE], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = r.stdout.split()
    return parts[2].split("/")[0] if r.returncode == 0 and len(parts) >= 3 else None


@app.get("/api/vpn")
def get_vpn():
    st = parse_status()
    ip = mesh_ip() if st.get(MESH_IFACE) else None
    port = read_config().get("remote_port")
    return {"daemon": st.get("nordvpnd", False), "iface": st.get(MESH_IFACE, False),
            "remote": st.get("eden_remote", False), "remote_url": f"http://{ip}:{port}" if ip else None}


@app.get("/api/vpn/settings")
def get_vpn_settings():
    """Read-only view of the Nord settings Eden controls; null when the daemon is not running."""
    if not parse_status().get("nordvpnd"):
        return {"settings": None}
    try:
        r = subprocess.run([sys.executable, EDEN_CTL, "nord-settings"], capture_output=True, text=True, timeout=30)
        return {"settings": json.loads(r.stdout) if r.returncode == 0 else None}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"settings": None}




# ---- restart Eden ---------------------------------------------------------------------
# Eden is held up by the foreground start.sh (foreground mode). A restart is done by that process, because
# it is the one that owns every child: it gets SIGUSR1 and runs down + up itself. Restarting from any other
# process would make the foreground one see its children vanish and tear the new ones down.
@app.post("/api/restart")
def restart_eden():
    pid = foreground_pid()
    if pid is None:
        raise HTTPException(409, say("restart_unavailable"))
    # After the answer has gone out: this very process is one of the things the restart stops.
    threading.Timer(0.5, os.kill, (pid, signal.SIGUSR1)).start()
    return {"ok": True}


# ---- settings and enrollment window ---------------------------------------------
# session timeout / lockout live in eden.json and are re-read by eden_remote on every
# use, so saving them needs no restart. Re-enrollment deletes the two secrets, opens a
# timed window (a file with an expiry timestamp) and restarts eden_remote, which drops
# every remote session; eden_remote then serves the enrollment page only while the
# window is open.
class SettingsBody(BaseModel):
    session_timeout_minutes: int
    lockout_attempts: int
    lockout_minutes: int


def enroll_remaining():
    try:
        with open(ENROLL_WINDOW_FILE) as f:
            return max(0, int(float(f.read().strip()) - time.time() + 0.999))
    except (OSError, ValueError):
        return 0


def enrolled():
    return all(os.path.exists(os.path.join(EDEN_SECRETS, f)) for f in SECRET_FILES)


def settings_state():
    with _cfg_lock:
        cfg = read_config()
    st = parse_status()
    ip = mesh_ip() if st.get(MESH_IFACE) else None
    return {
        "session_timeout_minutes": cfg.get("session_timeout_minutes", 15),
        "lockout_attempts": cfg.get("lockout_attempts", 5),
        "lockout_minutes": cfg.get("lockout_minutes", 5),
        "remote_port": cfg.get("remote_port"),
        "restart_available": foreground_pid() is not None,
        "enroll": {"enrolled": enrolled(), "window_remaining": enroll_remaining(),
                   "window_minutes": ENROLL_WINDOW_SECONDS // 60,
                   "remote_running": st.get("eden_remote", False),
                   "url": f"http://{ip}:{cfg.get('remote_port')}" if ip else None},
    }


@app.get("/api/settings")
def get_settings():
    return settings_state()


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    if not 0 <= body.session_timeout_minutes <= 1440:
        raise HTTPException(400, say("session_timeout_range"))
    if not 1 <= body.lockout_attempts <= 20:
        raise HTTPException(400, say("lockout_attempts_range"))
    if not 1 <= body.lockout_minutes <= 120:
        raise HTTPException(400, say("lockout_minutes_range"))
    with _cfg_lock:
        cfg = read_config()
        cfg.update(body.model_dump())
        write_config(cfg)
    return settings_state()


def write_enroll_window():
    fd, tmp = tempfile.mkstemp(dir=EDEN_RUN, prefix=".enroll_window.")
    with os.fdopen(fd, "w") as f:
        f.write(f"{time.time() + ENROLL_WINDOW_SECONDS}\n")
    os.replace(tmp, ENROLL_WINDOW_FILE)


def remove_quietly(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@app.post("/api/enroll/open")
def enroll_open():
    """Delete password+TOTP, open the timed window, restart eden_remote (drops all sessions)."""
    if not _ops_lock.acquire(blocking=False):
        raise HTTPException(409, say("busy"))
    try:
        if not parse_status().get("eden_remote"):
            raise HTTPException(409, say("remote_not_running"))
        write_enroll_window()
        for name in SECRET_FILES:
            remove_quietly(os.path.join(EDEN_SECRETS, name))
        try:
            r = run_start("remote-restart", timeout=30)
        except subprocess.TimeoutExpired:
            r = {"ok": False, "stdout": "", "stderr": "timeout"}
        if not r["ok"]:
            raise HTTPException(502, say("remote_restart_failed", detail=(r['stderr'] or r['stdout']).strip()))
    finally:
        _ops_lock.release()
    notify.event("enroll_opened", detail=say("ev_enroll_opened", minutes=ENROLL_WINDOW_SECONDS // 60))
    return settings_state()


@app.post("/api/enroll/cancel")
def enroll_cancel():
    """Close the window early. Secrets stay deleted: remote login is unavailable until a new window is opened."""
    remove_quietly(ENROLL_WINDOW_FILE)
    return settings_state()


# ---- appearance (for the login page) ---------------------------------------------
# The login page is served by eden_remote to other devices, which cannot read this browser's localStorage. Settings
# saves theme and field style here too ("ui" in eden.json) and the login page reads them from eden_remote.
# The language ("ui.language", en or it) is stored here as well: it also decides the language of the API's error messages.
class AppearanceBody(BaseModel):
    theme: str | None = None
    field_style: str | None = None
    language: str | None = None


def appearance_state():
    with _cfg_lock:
        ui = read_config().get("ui")
    ui = ui if isinstance(ui, dict) else {}
    return {"theme": ui.get("theme") if ui.get("theme") in ("light", "dark") else None,
            "field_style": ui.get("field_style") if ui.get("field_style") in ("fill", "outline") else None,
            "language": ui.get("language") if ui.get("language") in eden_i18n.LANGUAGES else eden_i18n.DEFAULT_LANGUAGE}


@app.get("/api/appearance")
def get_appearance():
    return appearance_state()


@app.post("/api/appearance")
def set_appearance(body: AppearanceBody):
    if body.theme is not None and body.theme not in ("light", "dark"):
        raise HTTPException(400, say("theme_invalid"))
    if body.field_style is not None and body.field_style not in ("fill", "outline"):
        raise HTTPException(400, say("field_style_invalid"))
    if body.language is not None and body.language not in eden_i18n.LANGUAGES:
        raise HTTPException(400, say("language_invalid"))
    with _cfg_lock:
        cfg = read_config()
        ui = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
        if body.language is not None:
            ui["language"] = body.language
        if body.theme is not None:
            ui["theme"] = body.theme
        if body.field_style is not None:
            ui["field_style"] = body.field_style
        cfg["ui"] = ui
        write_config(cfg)
    return appearance_state()


# ---- notifications (e-mail) ---------------------------------------------------------
# Settings are in eden.json under "notifications" (nothing secret); the SMTP password is the file secrets/smtp.password,
# written here and never sent back: the API only says whether one is set. The sending itself is eden_notify.
SMTP_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
EMAIL_RE = re.compile(r"[^@\s<>\"',;()\[\]\\]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class SmtpBody(BaseModel):
    host: str
    port: int
    security: str
    verify_tls: bool = True
    username: str = ""
    sender: str
    recipient: str
    password: str | None = None   # None: keep the stored one; "": remove it; anything else: replace it


class NotifySettingsBody(BaseModel):
    enabled: bool
    cooldown_minutes: int


def notifications_state():
    with _cfg_lock:
        cfg = notify.settings(read_config().get("notifications") or {})
    smtp = cfg["smtp"]
    return {
        "enabled": cfg["enabled"],
        "cooldown_minutes": cfg["cooldown_minutes"],
        "configured": notify.configured(smtp),
        "smtp": {"host": smtp["host"], "port": smtp["port"], "security": smtp["security"], "verify_tls": smtp["verify_tls"],
                 "username": smtp["username"], "sender": smtp["sender"], "recipient": smtp["recipient"],
                 "password_set": notify.password_set()},   # never the password itself
        "events": [{"id": e["id"], "label": notify.label(e["id"]), "description": notify.description(e["id"]), "source": e["source"],
                    "enabled": cfg["events"][e["id"]]} for e in notify.CATALOG],
        "status": notify.read_status(),
    }


def save_notifications(mutate):
    with _cfg_lock:
        cfg = read_config()
        section = cfg.get("notifications") if isinstance(cfg.get("notifications"), dict) else {}
        mutate(section)
        cfg["notifications"] = section
        write_config(cfg)


def write_smtp_password(value):
    """Atomic write of secrets/smtp.password (mode 0600 where the filesystem honours it); "" removes the file."""
    path = notify.password_file()
    if value == "":
        remove_quietly(path)
        return
    fd, tmp = tempfile.mkstemp(dir=EDEN_SECRETS, prefix=".smtp.password.")   # mkstemp creates it 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
        os.replace(tmp, path)
    except BaseException:
        remove_quietly(tmp)
        raise


@app.get("/api/notifications")
def get_notifications():
    return notifications_state()


@app.post("/api/notifications/smtp")
def set_notifications_smtp(body: SmtpBody):
    host, sender, recipient, username = body.host.strip(), body.sender.strip(), body.recipient.strip(), body.username.strip()
    if not SMTP_HOST_RE.fullmatch(host):
        raise HTTPException(400, say("smtp_host_invalid"))
    if not 1 <= body.port <= 65535:
        raise HTTPException(400, say("port_range"))
    if body.security not in notify.SECURITY_MODES:
        raise HTTPException(400, say("smtp_security_invalid"))
    if len(username) > 256 or CONTROL_RE.search(username):
        raise HTTPException(400, say("smtp_username_invalid"))
    for label, address in (("label_sender", sender), ("label_recipient", recipient)):
        if not EMAIL_RE.fullmatch(address) or len(address) > 254:
            raise HTTPException(400, say("email_invalid", label=say(label)))
    if body.password is not None and (len(body.password) > 256 or CONTROL_RE.search(body.password)):
        raise HTTPException(400, say("smtp_password_invalid"))
    save_notifications(lambda n: n.__setitem__("smtp", {"host": host, "port": body.port, "security": body.security,
                                                         "verify_tls": body.verify_tls, "username": username,
                                                         "sender": sender, "recipient": recipient}))
    if body.password is not None:
        write_smtp_password(body.password)
    return notifications_state()


@app.post("/api/notifications/settings")
def set_notifications_settings(body: NotifySettingsBody):
    if not 1 <= body.cooldown_minutes <= 1440:
        raise HTTPException(400, say("cooldown_range"))
    save_notifications(lambda n: n.update(enabled=body.enabled, cooldown_minutes=body.cooldown_minutes))
    return notifications_state()


@app.post("/api/notifications/events/{event_id}")
def set_notification_event(event_id: str, body: EnabledBody):
    if event_id not in notify.CATALOG_BY_ID:
        raise HTTPException(404, say("event_unknown", id=event_id))
    save_notifications(lambda n: n.setdefault("events", {}).__setitem__(event_id, body.enabled))
    return notifications_state()


@app.post("/api/notifications/test")
def test_notification():
    """Send the test message with the saved settings (whatever the switches say). The error text is shown as is."""
    ok, text = notify.send_test()
    if not ok:
        raise HTTPException(502, text)
    return {**notifications_state(), "message": text}


# ---- devices ------------------------------------------------------------------
def live_peers():
    """Live Meshnet peers through eden_ctl, or None when unavailable (VPN down, CLI error)."""
    if not vpn_is_up():
        return None
    try:
        r = subprocess.run([sys.executable, EDEN_CTL, "live-peers"], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def devices_state(cfg, peers):
    avatars = read_avatars()
    by_key = {p["public_key"]: p for p in peers or []}
    known = {d["public_key"] for d in cfg.get("devices", [])}
    return {
        "vpn_up": vpn_is_up(),
        "peers_ok": peers is not None,
        # external: Nord lists the peer under "External Peers" (another account); it is untrusted for good and the
        # switch cannot be turned off. Unknown (VPN down) reads as not external here; turning untrusted OFF asks again.
        "devices": [{"name": d["name"], "public_key": d["public_key"], "enabled": bool(d.get("enabled", True)),
                     "services": list(d.get("services", [])), "peer": by_key.get(d["public_key"]),
                     "avatar": avatar_of(avatars, DEVICE_KEY + d["name"]),
                     "external": bool((by_key.get(d["public_key"]) or {}).get("external")),
                     "meshnet": d.get("meshnet") if d.get("meshnet") in ("mine", "theirs", "both") else None,
                     "untrusted": cfg_untrusted(d) or bool((by_key.get(d["public_key"]) or {}).get("external"))}
                    for d in cfg.get("devices", [])],
        "available": [p for p in peers or [] if p["public_key"] not in known],
    }


def device_name(peer, taken):
    """Config name derived from the peer's nickname: lowercase [a-z0-9_-], unique."""
    raw = peer.get("nickname") or peer.get("hostname", "").split(".")[0] or "device"
    base = re.sub(r"[^a-z0-9_-]+", "-", raw.lower()).strip("-_")[:32] or "device"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}-{n}", n + 1
    return name


# ---- remote services -------------------------------------------------------------
# A remote service is a port that ANOTHER device offers to this computer (a web app on a friend's PC, say). It is only a
# bookmark in eden.json ("remote_services": name, device public key, port, note): Eden filters what comes INTO this
# machine, never what leaves it, so nothing here touches the firewall and a change needs no reload. The device is
# picked from the live Meshnet peers and kept by public key, like everywhere else.
def peer_label(peer, cfg_devices):
    """Name to show for a peer: the Eden device name when it is configured, else its nickname or host name."""
    for d in cfg_devices:
        if d["public_key"] == peer.get("public_key"):
            return d["name"]
    return peer.get("nickname") or (peer.get("hostname") or "").split(".")[0] or "device"


def remote_services_state(cfg, peers):
    by_key = {p["public_key"]: p for p in peers or []}
    devices = cfg.get("devices", [])
    rows = []
    for s in cfg.get("remote_services", []):
        peer = by_key.get(s["public_key"])
        rows.append({"name": s["name"], "public_key": s["public_key"], "port": s["port"], "note": s.get("note", ""),
                     "device": peer_label(peer, devices) if peer else next(
                         (d["name"] for d in devices if d["public_key"] == s["public_key"]), s.get("device_name", "?")),
                     "ip": peer["ip"] if peer else None,
                     "address": f"{peer['ip']}:{s['port']}" if peer else None,
                     "found": peer is not None,
                     "online": bool(peer) and (peer.get("status") or "").lower() == "connected",
                     "offered": bool(peer and peer.get("allows_in"))})
    return {"vpn_up": vpn_is_up(), "peers_ok": peers is not None, "services": rows,
            "peers": [{"public_key": p["public_key"], "label": peer_label(p, devices), "ip": p["ip"],
                       "offered": bool(p.get("allows_in")), "external": bool(p.get("external"))} for p in peers or []]}


class RemoteServiceBody(BaseModel):
    name: str | None = None
    public_key: str | None = None
    port: int | None = None
    note: str | None = None


def remote_service_fields(body, cfg, peers, current=None):
    """Validate a new or edited remote service against the config and the live peers; returns the stored entry."""
    name = body.name if body.name is not None else current["name"]
    key = body.public_key if body.public_key is not None else (current or {}).get("public_key")
    port = body.port if body.port is not None else (current or {}).get("port")
    note = (body.note if body.note is not None else (current or {}).get("note", "")).strip()
    if not SERVICE_NAME_RE.fullmatch(name or ""):
        raise HTTPException(400, say("service_name_invalid"))
    if not key:
        raise HTTPException(400, say("remote_device_required"))
    if port is None or not 1 <= port <= 65535:
        raise HTTPException(400, say("port_range"))
    if len(note) > NOTE_MAX:
        raise HTTPException(400, say("note_too_long", max=NOTE_MAX))
    if any(s["name"] == name and s is not current for s in cfg.get("remote_services", [])):
        raise HTTPException(409, say("remote_service_exists", name=name))
    # The device name is stored as a hint, for when the peer list cannot be read (VPN off).
    peer = next((p for p in peers or [] if p["public_key"] == key), None)
    hint = peer_label(peer, cfg.get("devices", [])) if peer else (current or {}).get("device_name", "")
    return {"name": name, "public_key": key, "port": port, "note": note, "device_name": hint}


@app.get("/api/remote-services")
def get_remote_services():
    peers = live_peers()
    with _cfg_lock:
        return remote_services_state(read_config(), peers)


@app.post("/api/remote-services")
def add_remote_service(body: RemoteServiceBody):
    peers = live_peers()
    with _cfg_lock:
        cfg = read_config()
        cfg.setdefault("remote_services", []).append(remote_service_fields(body, cfg, peers))
        write_config(cfg)
        return remote_services_state(cfg, peers)


@app.post("/api/remote-services/{name}/edit")
def edit_remote_service(name: str, body: RemoteServiceBody):
    peers = live_peers()
    with _cfg_lock:
        cfg = read_config()
        current = find(cfg.get("remote_services", []), name, "remote service")
        current.update(remote_service_fields(body, cfg, peers, current))
        write_config(cfg)
        return remote_services_state(cfg, peers)


@app.delete("/api/remote-services/{name}")
def delete_remote_service(name: str):
    peers = live_peers()
    with _cfg_lock:
        cfg = read_config()
        find(cfg.get("remote_services", []), name, "remote service")
        cfg["remote_services"] = [s for s in cfg["remote_services"] if s["name"] != name]
        write_config(cfg)
        return remote_services_state(cfg, peers)


class AddDeviceBody(BaseModel):
    public_key: str


@app.get("/api/devices")
def get_devices():
    peers = live_peers()
    with _cfg_lock:
        return devices_state(read_config(), peers)


@app.post("/api/devices")
def add_device(body: AddDeviceBody):
    """Add a device chosen from the live peer list. Created disabled, UNTRUSTED and with no service grants: it must
    be made trusted on purpose (never possible for an external peer)."""
    peers = live_peers()
    if peers is None:
        raise HTTPException(409, say("vpn_off_add_device"))
    peer = next((p for p in peers if p["public_key"] == body.public_key), None)
    if peer is None:
        raise HTTPException(404, say("peer_not_found"))

    def mutate(cfg):
        if any(d["public_key"] == peer["public_key"] for d in cfg["devices"]):
            raise HTTPException(409, say("device_exists_cfg"))
        cfg["devices"].append({"name": device_name(peer, {d["name"] for d in cfg["devices"]}),
                               "public_key": peer["public_key"], "enabled": False, "services": [], "untrusted": True})
    return apply_change(mutate)


class UntrustedBody(BaseModel):
    untrusted: bool


@app.post("/api/devices/{device}/untrusted")
def set_device_untrusted(device: str, body: UntrustedBody):
    """Switch a device between untrusted and trusted. ON removes every service grant of the device at once (the
    services stay on for the other devices) and the reload closes those ports. OFF widens access: refused for a peer
    Nord lists as external, and refused when that cannot be checked (VPN down, peer not listed): fail closed."""
    if not body.untrusted:
        with _cfg_lock:
            key = find(read_config().get("devices", []), device, "device")["public_key"]
        peers = live_peers()
        if peers is None:
            raise HTTPException(409, say("vpn_off_check_external"))
        peer = next((p for p in peers if p["public_key"] == key), None)
        if peer is None:
            raise HTTPException(409, say("peer_missing_check_external"))
        if peer.get("external"):
            raise HTTPException(409, say("device_is_external"))

    def mutate(cfg):
        dev = find(cfg["devices"], device, "device")
        if body.untrusted:
            if not cfg_untrusted(dev):
                dev["untrusted"] = True
                dev["services"] = []
        else:
            dev.pop("untrusted", None)
    result = apply_change(mutate)
    if not body.untrusted:
        notify.event("access_widened", detail=say("ev_untrusted_cleared", device=device))
    return result


@app.post("/api/devices/{device}/enabled")
def set_device_enabled(device: str, body: EnabledBody):
    def mutate(cfg):
        find(cfg["devices"], device, "device")["enabled"] = body.enabled
    result = apply_change(mutate)
    if body.enabled:
        notify.event("access_widened", detail=say("ev_device_enabled", device=device))
    return result


class EditDeviceBody(BaseModel):
    name: str | None = None
    avatar: str | None = None
    clear_avatar: bool = False     # with neither avatar nor this, the picture is kept
    # Whose Meshnet the link belongs to, as the user says it (Nord does not tell who invited whom; for the devices of
    # another account both permission sets read the same): "mine", "theirs", "both"; "" clears it; None keeps it.
    meshnet: str | None = None


@app.post("/api/devices/{device}/edit")
def edit_device(device: str, body: EditDeviceBody):
    """Rename a device and/or change its picture. The device stays what it is: it is identified by its public key."""
    new_name = device if body.name is None else body.name
    if not SERVICE_NAME_RE.fullmatch(new_name):   # same shape as service names: it appears in URLs
        raise HTTPException(400, say("device_name_invalid"))
    if body.avatar is not None and not valid_avatar(body.avatar):
        raise HTTPException(400, say("avatar_invalid"))
    if body.meshnet not in (None, "", "mine", "theirs", "both"):
        raise HTTPException(400, "meshnet: mine, theirs, both or empty")

    def mutate(cfg):
        dev = find(cfg["devices"], device, "device")
        if new_name != device and any(d["name"] == new_name for d in cfg["devices"]):
            raise HTTPException(409, say("device_name_taken", name=new_name))
        dev["name"] = new_name
        if body.meshnet == "":
            dev.pop("meshnet", None)
        elif body.meshnet is not None:
            dev["meshnet"] = body.meshnet

    result = apply_change(mutate)

    def update_avatar(data):
        old_key, new_key = DEVICE_KEY + device, DEVICE_KEY + new_name
        if new_name != device:
            moved = data.pop(old_key, None)
            data.pop(new_key, None)
            if moved:
                data[new_key] = moved
        if body.avatar:
            data[new_key] = body.avatar
        elif body.clear_avatar:
            data.pop(new_key, None)
    update_avatars(update_avatar)
    return result


@app.delete("/api/devices/{device}")
def delete_device(device: str):
    def mutate(cfg):
        find(cfg["devices"], device, "device")   # 404 if unknown
        cfg["devices"] = [d for d in cfg["devices"] if d["name"] != device]
    result = apply_change(mutate)
    update_avatars(lambda data: data.pop(DEVICE_KEY + device, None))
    return result


# ---- live monitor (Home page) ---------------------------------------------------
# The numbers of the Home page are computed inside the request that asks for them (the page asks only while it is open
# and the tab is visible). The traffic history is the exception: see "live traffic" below. Two endpoints keep the
# frequent request cheap:
#   /api/monitor          two sysfs reads and one `ss` (no root, a few ms); asked every refresh_seconds
#   /api/monitor/devices  the Nord peer list through eden_ctl (slow); asked every presence_seconds and cached
# Standard library only, imported lazily inside the functions that need it.
MESH_NET = "100.64.0.0/10"            # Nord Meshnet range: only connections to peers inside it are reported
MONITOR_CACHE_SECONDS = 0.5           # two open tabs share one sample instead of running `ss` twice
MONITOR_DEVICES_CACHE_SECONDS = 4.0
MONITOR_MAX_CONNECTIONS = 200
SS_TIMEOUT = 3
_monitor_lock = threading.Lock()
_monitor_cache = (0.0, None)
_monitor_devices_lock = threading.Lock()
_monitor_devices_cache = (0.0, None)
# The only TCP details taken from `ss -i` (rtt is "avg/dev", the first number is wanted). Anything else on the line,
# such as the congestion algorithm's own block (cubic or bbr:(...)), is ignored on purpose.
SS_FIELD_RE = re.compile(r"\b(bytes_sent|bytes_received|rtt|lastsnd|lastrcv):(\d+(?:\.\d+)?)")
IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def iface_address(iface):
    """IPv4 address of an interface through the SIOCGIFADDR ioctl (no process is started), or None."""
    import fcntl
    import socket
    import struct
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            packed = fcntl.ioctl(sock.fileno(), 0x8915, struct.pack("256s", iface.encode()[:15]))
        return socket.inet_ntoa(packed[20:24])
    except OSError:
        return None


def iface_counters(iface):
    """(rx_bytes, tx_bytes) since the interface came up, read from sysfs, or None. Totals: the rate is the client's
    difference between two samples."""
    if not iface or "/" in iface or iface.startswith("."):
        return None
    base = f"/sys/class/net/{iface}/statistics"
    try:
        with open(f"{base}/rx_bytes") as f:
            rx = int(f.read())
        with open(f"{base}/tx_bytes") as f:
            tx = int(f.read())
        return rx, tx
    except (OSError, ValueError):
        return None


def split_addr(text):
    ip, _, port = text.rpartition(":")
    return (ip, int(port)) if IPV4_RE.fullmatch(ip) and port.isdigit() else (None, None)


def parse_ss(text):
    """Sockets from `ss -Htni state established ...`: a line with the addresses, then an indented line with the TCP
    details. A socket with no traffic has no bytes_sent/bytes_received at all (they count as 0). IPv6 is skipped."""
    out, cur = [], None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t":
            if cur is not None:
                for key, value in SS_FIELD_RE.findall(line):
                    cur.setdefault(key, float(value))
            continue
        parts = line.split()
        cur = None
        if len(parts) < 4:
            continue
        l_ip, l_port = split_addr(parts[-2])
        r_ip, r_port = split_addr(parts[-1])
        if l_ip is None or r_ip is None:
            continue
        cur = {"local_ip": l_ip, "local_port": l_port, "remote_ip": r_ip, "remote_port": r_port}
        out.append(cur)
    return out


def build_connections(sockets, mesh, cfg):
    """Connections to Meshnet peers, shaped for the UI. `in`: the local port is one Eden knows (a service or the
    remote-access port); `out`: this computer called a peer. A socket that talks to this computer itself shows up at both ends:
    only the listening side is kept."""
    import ipaddress
    net = ipaddress.ip_network(MESH_NET)
    names = {s["port"]: s["name"] for s in cfg.get("services", [])}
    remote_port = cfg.get("remote_port")
    rows = []
    for c in sockets:
        try:
            if ipaddress.ip_address(c["remote_ip"]) not in net:
                continue
        except ValueError:
            continue
        known = c["local_port"] in names or c["local_port"] == remote_port
        if c["remote_ip"] == mesh and not known:
            continue
        rows.append({
            "id": f'{c["remote_ip"]}:{c["remote_port"]}>{c["local_port"]}',
            "remote_ip": c["remote_ip"], "remote_port": c["remote_port"], "local_port": c["local_port"],
            "direction": "in" if known else "out",
            "kind": "service" if c["local_port"] in names else ("remote" if c["local_port"] == remote_port else "other"),
            "service": names.get(c["local_port"]),
            "bytes_sent": int(c.get("bytes_sent", 0)), "bytes_received": int(c.get("bytes_received", 0)),
            "rtt_ms": c.get("rtt"),
            "idle_ms": int(min(c["lastsnd"], c["lastrcv"])) if "lastsnd" in c and "lastrcv" in c else None,
        })
    rows.sort(key=lambda r: r["bytes_sent"] + r["bytes_received"], reverse=True)
    return rows[:MONITOR_MAX_CONNECTIONS], len(rows) > MONITOR_MAX_CONNECTIONS


def build_monitor():
    import ipaddress
    now = time.time()
    ip, counters = iface_address(MESH_IFACE), iface_counters(MESH_IFACE)
    if ip is None or counters is None:
        return {"vpn_up": False, "t": now}
    snap = {"vpn_up": True, "t": now, "mesh_ip": ip, "rx_bytes": counters[0], "tx_bytes": counters[1],
            "connections": None, "truncated": False}
    try:
        # The address went through ipaddress first: it can never be taken for an option by ss.
        if ipaddress.ip_address(ip) not in ipaddress.ip_network(MESH_NET):
            return snap
        r = subprocess.run(["ss", "-Htni", "state", "established", "src", ip], capture_output=True, text=True, timeout=SS_TIMEOUT)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return snap          # counters still useful; connections: null means "could not read them"
    if r.returncode == 0:
        snap["connections"], snap["truncated"] = build_connections(parse_ss(r.stdout), ip, read_config())
    return snap


@app.get("/api/monitor")
def get_monitor():
    global _monitor_cache
    touch_ui()
    with _monitor_lock:
        stamp, data = _monitor_cache
        if data is not None and time.monotonic() - stamp < MONITOR_CACHE_SECONDS:
            return data
        data = build_monitor()
        _monitor_cache = (time.monotonic(), data)
        return data


def peer_online(peer):
    return str(peer.get("status", "")).strip().lower() in ("connected", "online")


def build_monitor_devices():
    peers = live_peers()
    cfg = read_config()
    by_key = {p["public_key"]: p for p in peers or []}
    known = {d["public_key"] for d in cfg.get("devices", [])}
    devices = []
    for d in cfg.get("devices", []):
        p = by_key.get(d["public_key"])
        devices.append({"name": d["name"], "enabled": bool(d.get("enabled", True)), "ip": p.get("ip") if p else None,
                        "online": bool(p) and peer_online(p), "status": p.get("status") if p else None,
                        "untrusted": cfg_untrusted(d) or bool(p and p.get("external"))})
    unknown = [{"name": p.get("nickname") or p.get("hostname", "").split(".")[0] or "peer", "ip": p.get("ip"),
                "online": peer_online(p), "status": p.get("status"), "untrusted": bool(p.get("external"))}
               for p in peers or [] if p["public_key"] not in known]
    return {"peers_ok": peers is not None, "devices": devices, "unknown": unknown}


@app.get("/api/remote/home")
def remote_home(ip: str):
    """Read-only, for eden_remote (loopback): what the dashboard of a logged-in remote device shows. `ip` is the Meshnet
    address eden_remote saw on the connection, never something the browser sends. A device is "trusted" only when it is in
    the config, not marked untrusted and not external; anything else (unknown peer, external peer) is untrusted. The services
    are the ones that are really open to it: service on, port allowed, forwarding not broken, device enabled and granted."""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(400, "bad address")
    mon = monitor_devices_data()
    if not mon["peers_ok"]:
        raise HTTPException(503, say("peers_unavailable"))
    cfg = read_config()
    peer = next((d for d in mon["devices"] if d.get("ip") == ip), None)
    other = next((d for d in mon["unknown"] if d.get("ip") == ip), None)
    out = {"host_name": host_name(), "device": None, "trusted": False, "services": []}
    if peer is None:
        if other is not None:
            out["device"] = {"name": other["name"], "known": False, "enabled": False}
        return out
    dev = next((d for d in cfg.get("devices", []) if d["name"] == peer["name"]), None)
    out["device"] = {"name": peer["name"], "known": True, "enabled": bool(peer["enabled"])}
    out["trusted"] = bool(dev) and not peer["untrusted"]
    if not dev or not peer["enabled"]:
        return out
    granted = set(dev.get("services", []))
    state = services_state(cfg)
    for svc in state["services"]:
        if svc["name"] not in granted or not svc["enabled"] or svc["port_allowed"] is False:
            continue
        if svc["forward"] and (svc["forward_status"] or {}).get("state") == "error":
            continue
        if peer["untrusted"] and svc["port"] == cfg.get("remote_port"):
            continue   # never for an untrusted device, by design
        out["services"].append({"name": svc["name"], "port": svc["port"], "note": svc["note"], "avatar": svc["avatar"]})
    return out


@app.get("/api/monitor/devices")
def get_monitor_devices():
    touch_ui()
    return monitor_devices_data()


def monitor_devices_data():
    """Names and presence of the Meshnet peers. Never waits behind another caller: while one request is asking Nord,
    the others get the last answer (or an empty one) at once."""
    global _monitor_devices_cache
    stamp, data = _monitor_devices_cache
    if data is not None and time.monotonic() - stamp < MONITOR_DEVICES_CACHE_SECONDS:
        return data
    if not _monitor_devices_lock.acquire(blocking=False):
        return data or {"peers_ok": None, "devices": [], "unknown": []}
    try:
        data = build_monitor_devices()
        _monitor_devices_cache = (time.monotonic(), data)
        return data
    finally:
        _monitor_devices_lock.release()


# ---- live traffic: history and presence events ----------------------------------------
# "monitor" in eden.json: live (default on), refresh_seconds (2), presence_seconds (15), retention_days (7) and
# record_when_closed (true). While live is on a sampler records the Meshnet interface rate every refresh_seconds and every
# device that comes online or goes offline. With record_when_closed off it records only while a browser tab with Eden
# is open and visible (the page asks /api/monitor/live every few seconds, and that counts as "open"). Switched off,
# nothing is read or stored. Entries older than retention_days are dropped at startup and then once an hour.
# This replaces "the monitor costs nothing when Home is closed": the user decides here.
MONITOR_HISTORY_FILE = os.path.join(os.path.dirname(EDEN_AVATARS), "monitor_history.json")
MONITOR_DEFAULTS = {"live": True, "refresh_seconds": 2, "presence_seconds": 15, "retention_days": 7, "record_when_closed": True}
MONITOR_LIMITS = {"refresh_seconds": (1, 60), "presence_seconds": (5, 300), "retention_days": (1, 35)}
UI_OPEN_SECONDS = 45          # a page that has not asked for this long counts as closed
monitor_history = eden_monitor.History()
_ui_seen = 0.0


def touch_ui():
    global _ui_seen
    _ui_seen = time.monotonic()


def ui_open():
    return time.monotonic() - _ui_seen < UI_OPEN_SECONDS


def monitor_settings():
    with _cfg_lock:
        m = read_config().get("monitor")
    m = m if isinstance(m, dict) else {}
    out = dict(MONITOR_DEFAULTS)
    for key, default in MONITOR_DEFAULTS.items():
        v = m.get(key)
        if isinstance(default, bool):
            out[key] = v if isinstance(v, bool) else default
        elif isinstance(v, int) and not isinstance(v, bool) and MONITOR_LIMITS[key][0] <= v <= MONITOR_LIMITS[key][1]:
            out[key] = v
    return out


def monitor_live():
    return monitor_settings()["live"]


def monitor_gate():
    return monitor_settings()["record_when_closed"] or ui_open()


def monitor_presence():
    """{name: {name, ip, online, untrusted}} of every Meshnet peer, or None when Nord cannot say."""
    data = monitor_devices_data()
    if data.get("peers_ok") is not True:
        return None
    return {p["name"]: p for p in [*data["devices"], *data["unknown"]]}


_s0 = monitor_settings()
monitor_sampler = eden_monitor.Sampler(monitor_history, lambda: iface_counters(MESH_IFACE), monitor_presence,
                                       path=MONITOR_HISTORY_FILE, step=_s0["refresh_seconds"],
                                       presence_every=_s0["presence_seconds"], retention_s=_s0["retention_days"] * 86400,
                                       gate=monitor_gate)


def apply_monitor_settings():
    s = monitor_settings()
    monitor_sampler.configure(step=s["refresh_seconds"], presence_every=s["presence_seconds"],
                              retention_s=s["retention_days"] * 86400)
    if s["live"]:
        monitor_sampler.start()
    else:
        monitor_sampler.stop()
    return s


@app.on_event("startup")
def monitor_startup():
    monitor_history.load(MONITOR_HISTORY_FILE)
    monitor_history.prune(time.time() - monitor_settings()["retention_days"] * 86400)
    apply_monitor_settings()


@app.on_event("shutdown")
def monitor_shutdown():
    monitor_sampler.stop()


class LiveBody(BaseModel):
    live: bool


class MonitorSettingsBody(BaseModel):
    refresh_seconds: int
    presence_seconds: int
    retention_days: int
    record_when_closed: bool


def live_state():
    s = monitor_settings()
    return {**s, "running": monitor_sampler.running, **monitor_history.info()}


@app.get("/api/monitor/live")
def get_monitor_live():
    touch_ui()   # the page polls this every few seconds: it is also how Eden knows a UI is open
    return live_state()


def save_monitor(patch):
    with _cfg_lock:
        cfg = read_config()
        m = cfg.get("monitor") if isinstance(cfg.get("monitor"), dict) else {}
        m.update(patch)
        cfg["monitor"] = m
        write_config(cfg)


@app.post("/api/monitor/live")
def set_monitor_live(body: LiveBody):
    save_monitor({"live": body.live})
    apply_monitor_settings()
    return live_state()


@app.post("/api/monitor/settings")
def set_monitor_settings(body: MonitorSettingsBody):
    for key, (lo, hi) in MONITOR_LIMITS.items():
        if not lo <= getattr(body, key) <= hi:
            label = say({"refresh_seconds": "label_refresh", "presence_seconds": "label_presence",
                         "retention_days": "label_retention"}[key])
            raise HTTPException(400, say("monitor_range_invalid", label=label, lo=lo, hi=hi))
    save_monitor(body.model_dump())
    s = apply_monitor_settings()
    monitor_history.prune(time.time() - s["retention_days"] * 86400)   # a shorter retention takes effect now
    return live_state()


@app.get("/api/monitor/history")
def get_monitor_history(range: str = "30m", max_points: int = 600):
    if range not in eden_monitor.RANGES:
        raise HTTPException(400, say("history_range_unknown", range=range))
    touch_ui()
    now = time.time()
    span = eden_monitor.RANGES[range]
    since = monitor_history.info()["since"]
    start = now - span if span is not None else (since if since is not None else now - 60)
    out = monitor_history.query(start, now, max(50, min(max_points, 2000)))
    return {**live_state(), "range": range, "from": start, "to": now, **out}


# ---- name of this computer ----------------------------------------------------------------
# Shown everywhere the UI says where Eden runs ("host_name" in eden.json; default: this machine's hostname). The UI reads
# it once when a page loads, so a change shows up in the other pages after a reload; no restart of Eden is needed.
# The remote login page is a separate app and says "the computer where Eden runs" without naming it.
HOST_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}")


def host_name():
    import socket
    with _cfg_lock:
        v = read_config().get("host_name")
    if isinstance(v, str) and HOST_NAME_RE.fullmatch(v.strip()):
        return v.strip()
    return socket.gethostname().split(".")[0].upper() or "EDEN"


class HostBody(BaseModel):
    host_name: str


@app.get("/api/host")
def get_host():
    return {"host_name": host_name()}


@app.post("/api/host")
def set_host(body: HostBody):
    name = body.host_name.strip()
    if not HOST_NAME_RE.fullmatch(name):
        raise HTTPException(400, say("host_name_invalid"))
    with _cfg_lock:
        cfg = read_config()
        cfg["host_name"] = name
        write_config(cfg)
    return {"host_name": name}


# ---- audit (read-only) ----------------------------------------------------------
# Two kinds of source: the root helper's journal entries, and the *.log files in
# EDEN_LOGS. Only names found in that directory listing are ever opened.
LOG_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+\.log")
MAX_LINES = 1000
TAIL_BYTES = 512 * 1024


def log_ids():
    try:
        return sorted(n[:-4] for n in os.listdir(EDEN_LOGS) if LOG_NAME_RE.fullmatch(n))
    except OSError:
        return []


def is_action(line):
    """uvicorn access-log lines for requests that change something (not the polling GETs)."""
    return '"POST ' in line or '"DELETE ' in line or '"PUT ' in line


def tail_file(path, n, keep=None):
    """Last `n` lines (after the optional `keep` filter) of the final TAIL_BYTES of a file."""
    with open(path, "rb") as f:
        size = f.seek(0, os.SEEK_END)
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > TAIL_BYTES:
        lines = lines[1:]   # first line is probably cut in the middle
    return [l for l in lines if keep is None or keep(l)][-n:]


def helper_journal(n):
    try:
        r = subprocess.run(["journalctl", "-t", "eden-helper", "-n", str(n), "--no-pager", "-o", "short-iso"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HTTPException(502, say("journalctl_unavailable", error=e))
    if r.returncode:
        raise HTTPException(502, say("journalctl_failed", detail=(r.stderr or r.stdout).strip()))
    return r.stdout.splitlines()


@app.get("/api/audit/sources")
def audit_sources():
    return {"sources": [{"id": "helper", "label": "Helper (azioni root)"}] +
                       [{"id": i, "label": f"{i}.log"} for i in log_ids()]}


@app.get("/api/audit")
def get_audit(source: str = "helper", lines: int = 200, actions_only: bool = False):
    n = max(1, min(lines, MAX_LINES))
    if source == "helper":
        return {"source": source, "lines": helper_journal(n)}
    if source not in log_ids():
        raise HTTPException(404, f"unknown log source: {source}")
    path = os.path.join(EDEN_LOGS, source + ".log")
    return {"source": source, "lines": tail_file(path, n, is_action if actions_only else None)}


class SPAStaticFiles(StaticFiles):
    """The built webui is a single-page app: /vpn, /services, ... exist only inside its client-side router, so a
    page refresh or a bookmark on one of them must get index.html and let the app route it. Everything that is
    not a page keeps a real 404: API paths (a wrong URL must not answer with HTML) and anything that looks like
    a file (a missing asset must not be masked by index.html)."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                return response
            not_found = None
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            not_found = exc
        if path == "api" or path.startswith("api/") or "." in os.path.basename(path):
            if not_found is not None:
                raise not_found
            return response
        return await super().get_response("index.html", scope)


# Static webui build, mounted last so /api/* above takes priority.
if os.path.isdir(DIST):
    app.mount("/", SPAStaticFiles(directory=DIST, html=True), name="webui")
else:
    @app.get("/")
    def not_built():
        return {"error": f"{DIST} not found - run 'pnpm build' in webui/ first"}


# Windows edition: the functions above that are tied to Linux are replaced by windows/eden_platform_windows.py. Nothing
# changes on Linux: this block does not run there.
if sys.platform == "win32" or os.environ.get("EDEN_PLATFORM") == "windows":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "windows"))
    import eden_platform_windows  # noqa: E402
    eden_platform_windows.apply(globals(), app)
