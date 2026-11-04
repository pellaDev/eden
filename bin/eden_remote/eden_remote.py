#!/usr/bin/env python3
#
# Eden remote: the only process listening on the Meshnet address. Does two
# things and nothing else - login (password + TOTP) and, once logged in,
# a raw byte pipe to an optional upstream web service on loopback (EDEN_UPSTREAM_PORT; none by default: a logged-in
# user is then sent to Eden's own dashboard). The upstream owns the root path, so Eden's own pages live under
# /eden/. No admin functions live here; those belong to Eden local (loopback only).
#
# UI: the login, enrollment and "closed" screens are one small React app (PDS components) built from
# webui/login.html into webui/dist-login/ (see vite.login.config.ts). This process serves only that folder's
# index and its assets/ plus logo.svg, all under /eden/, never anything else from disk. The app talks to
# /eden/api/state, /eden/api/login and /eden/api/enroll (JSON), and takes theme and field style from eden.json
# ("ui"), so it looks like Eden local does.
#
# Notifications: failed logins, lockouts, successful logins and enrollment go to eden_notify (e-mail).
#
# Enrollment: password + TOTP are set up through a page that is only served while
# an enrollment window is open. Eden local opens the window (it deletes the two
# files in secrets/, writes an expiry timestamp to EDEN_RUN/enroll_window and
# restarts this process, which drops every session). Without an open window and
# without the two files, nothing is offered here: no QR, no form. The window closes
# when enrollment succeeds or when it expires; the page shows a countdown.
#
# Session: a random token kept in memory only (no database), expiring after
# session_timeout_minutes of inactivity (0 = never expire). Failed logins: after
# lockout_attempts, an IP is locked out for lockout_minutes. Both settings, like
# the timeout, are read from config/eden.json on every use.

import base64
import hashlib
import hmac
import math
import json
import mimetypes
import os
import re
import secrets
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import pyotp
import qrcode
import io

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "eden_notify"))
import eden_notify as notify   # noqa: E402  (e-mail alerts: event() never raises and never blocks)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import eden_i18n   # noqa: E402  (texts of the mail details, in the language set in Eden local's Settings)

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_MINUTES = 5
COOKIE_NAME = "eden_session"
SCRYPT_PARAMS = dict(n=2**14, r=8, p=1, dklen=32)  # ~tens of ms per attempt on this hardware
GATE_MESSAGE = "no eden_session session. Open /eden/login first."


def env(name, default=None):
    v = os.environ.get(name, default)
    if v is None:
        sys.exit(f"eden_remote: {name} is not set (run through start.sh)")
    return v


SECRETS_DIR = env("EDEN_SECRETS")
PASS_FILE = os.path.join(SECRETS_DIR, "password.hash")
TOTP_FILE = os.path.join(SECRETS_DIR, "totp.secret")
UPSTREAM_PORT = int(os.environ.get("EDEN_UPSTREAM_PORT") or 0)   # loopback only; the single forwarding target, 0 = none
ENROLL_WINDOW_FILE = os.path.join(env("EDEN_RUN"), "enroll_window")
EDEN_LOCAL_PORT = int(os.environ.get("EDEN_LOCAL_PORT") or 0)   # loopback: the read-only dashboard data comes from Eden local
# The built login app. EDEN_LOGIN_DIST may override the default location under EDEN_HOME.
LOGIN_DIST = os.path.realpath(os.environ.get("EDEN_LOGIN_DIST") or os.path.join(env("EDEN_HOME"), "webui", "dist-login"))
MAX_BODY = 4096   # bytes: a login or enrollment JSON body is a few dozen
ASSET_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")
# The login page loads only its own files; frames are refused. 'unsafe-inline' is for style attributes only.
APP_CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; "
           "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


def load_config():
    with open(env("EDEN_CONFIG")) as f:
        return json.load(f)


def ui_language():
    """Language set in Eden local's Settings (ui.language); the default when the config cannot be read."""
    try:
        ui = load_config().get("ui")
        lang = ui.get("language") if isinstance(ui, dict) else None
    except (OSError, ValueError):
        lang = None
    return lang if lang in eden_i18n.LANGUAGES else eden_i18n.DEFAULT_LANGUAGE


def say(key, **fields):
    return eden_i18n.message(ui_language(), key, **fields)


def lockout_params():
    """(max failed attempts, lockout seconds) from the config, defaults if absent/unreadable."""
    try:
        cfg = load_config()
    except (OSError, ValueError):
        cfg = {}
    return (max(1, int(cfg.get("lockout_attempts", DEFAULT_MAX_ATTEMPTS))),
            max(1, int(cfg.get("lockout_minutes", DEFAULT_LOCKOUT_MINUTES))) * 60)


# ---------- password hashing (scrypt, salted) ----------

def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, **SCRYPT_PARAMS)


def set_password(password: str):
    salt = secrets.token_bytes(16)
    digest = hash_password(password, salt)
    with open(PASS_FILE, "wb") as f:
        f.write(salt + digest)
    os.chmod(PASS_FILE, 0o600)


def check_password(password: str) -> bool:
    with open(PASS_FILE, "rb") as f:
        blob = f.read()
    salt, digest = blob[:16], blob[16:]
    return hmac.compare_digest(hash_password(password, salt), digest)


# ---------- TOTP enrollment ----------

def enrolled() -> bool:
    return os.path.exists(PASS_FILE) and os.path.exists(TOTP_FILE)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_qr_png(secret: str, label: str, issuer: str) -> bytes:
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=label, issuer_name=issuer)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def enroll_remaining() -> int:
    """Seconds left in the enrollment window opened by Eden local (0 = closed)."""
    try:
        with open(ENROLL_WINDOW_FILE) as f:
            expiry = float(f.read().strip())
    except (OSError, ValueError):
        return 0
    return max(0, math.ceil(expiry - time.time()))


def close_enroll_window():
    try:
        os.unlink(ENROLL_WINDOW_FILE)
    except FileNotFoundError:
        pass


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------- sessions and lockout (in memory only) ----------

_lock = threading.Lock()
_sessions = {}      # token -> last_activity (monotonic)
_attempts = {}       # client ip -> (count, locked_until monotonic)
_pending_enroll = {}  # holds the TOTP secret between "show QR" and "confirm" (memory only)


def session_timeout_seconds():
    minutes = load_config().get("session_timeout_minutes", 15)
    return None if minutes in (0, None) else minutes * 60


def new_session() -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = time.monotonic()
    return token


def session_valid(token) -> bool:
    if not token:
        return False
    timeout = session_timeout_seconds()
    with _lock:
        last = _sessions.get(token)
        if last is None:
            return False
        if timeout is not None and time.monotonic() - last > timeout:
            del _sessions[token]
            return False
        _sessions[token] = time.monotonic()   # sliding window
        return True


def lock_remaining(ip) -> int:
    """Seconds left on this source's lockout (0 = not locked)."""
    with _lock:
        count, until = _attempts.get(ip, (0, 0))
        return max(0, math.ceil(until - time.monotonic()))


def locked_out(ip) -> bool:
    return lock_remaining(ip) > 0


def record_attempt(ip, ok: bool):
    """Count a login attempt. Returns (failed attempts so far, True if this failure started a lockout)."""
    max_attempts, lockout_seconds = lockout_params()
    with _lock:
        count, until = _attempts.get(ip, (0, 0))
        if ok:
            _attempts.pop(ip, None)
            return 0, False
        count += 1
        locked_now = count >= max_attempts
        until = time.monotonic() + lockout_seconds if locked_now else until
        _attempts[ip] = (count, until)
        return count, locked_now


# ---------- raw byte pipe ----------

# One pipe serves HTTP and WebSocket alike: after the 101 the bytes are just bytes,
# and an HTTP client that reads the whole response before writing anything cannot
# carry an event stream. Nothing here buffers.

def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def rfile_leftover(rfile, sock):
    """Bytes rfile already read past the headers. The raw pipe reads the socket directly, so
    anything still sitting in rfile's buffer would be lost: take it and forward it first.
    BufferedReader.peek() is the only way to see them, but peek fills the buffer from the raw
    stream and blocks when the buffer is empty. The raw is a SocketIO with no setblocking(), so
    the socket itself is flipped to non-blocking for the check alone: peek then raises
    BlockingIOError instead of waiting for data that is not there yet. peek() leaves the bytes in
    the buffer, so they are consumed here or the pipe would send them a second time."""
    if not hasattr(rfile, "peek"):
        return b""
    was_blocking = sock.getblocking()
    try:
        sock.setblocking(False)
        try:
            buffered = rfile.peek(65536)
        except BlockingIOError:
            buffered = b""
    finally:
        try:
            sock.setblocking(was_blocking)
        except OSError:
            pass
    if not buffered:
        return b""
    try:
        return rfile.read(len(buffered))
    except OSError:
        return b""


def eden_path(raw):
    """Path, normalized (no query, no trailing slash). The upstream owns '/', so every Eden
    route lives under /eden/ and can never collide with it. '/' itself is NOT an Eden route:
    it belongs to the upstream, and an empty path must not collapse into /eden."""
    return urlsplit(raw).path.rstrip("/") or "/"


def is_eden_route(route):
    """True only for Eden's own paths. startswith("/eden") alone would also match /edenx."""
    return route == "/eden" or route.startswith("/eden/")


# ---------- login app (static files) and its state ----------

def static_file(route):
    """Path of a file the login app may load, or None. Only dist-login/assets/<name> and dist-login/logo.svg are
    ever served; the name must match a strict pattern, so no path can climb out of the folder."""
    if route == "/eden/logo.svg":
        rel = "logo.svg"
    elif route.startswith("/eden/assets/"):
        name = route[len("/eden/assets/"):]
        if not ASSET_NAME_RE.fullmatch(name) or name.startswith("."):
            return None
        rel = os.path.join("assets", name)
    else:
        return None
    path = os.path.join(LOGIN_DIST, rel)
    return path if os.path.isfile(path) else None


def app_state(token=None):
    """What the login app needs before it can draw anything: which screen, the enrollment time left, the look.
    A browser that already has a valid session gets the dashboard ("home") instead of the login form."""
    if enrolled():
        mode, remaining = ("home" if session_valid(token) else "login"), 0
    else:
        remaining = enroll_remaining()
        mode = "enroll" if remaining > 0 else "closed"
        if mode == "closed":
            _pending_enroll.clear()
    try:
        ui = load_config().get("ui") or {}
    except (OSError, ValueError):
        ui = {}
    theme, field_style = ui.get("theme"), ui.get("field_style")
    return {"mode": mode, "remaining": remaining, "language": ui_language(),
            "appearance": {"theme": theme if theme in ("light", "dark") else None,
                           "field_style": field_style if field_style in ("fill", "outline") else None}}


def clean_text(value, limit=120):
    """Text from a request, made safe to put in a log line or a mail body."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


class Handler(BaseHTTPRequestHandler):
    server_version = "eden_remote/0"

    def log_message(self, fmt, *args):
        sys.stderr.write("eden_remote: " + (fmt % args) + "\n")

    def client_ip(self):
        return self.client_address[0]

    def send_html(self, body, status=HTTPStatus.OK):
        b = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def send_plain(self, status, text):
        b = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":   # a HEAD response has headers only
            self.wfile.write(b)

    def send_app(self, status=HTTPStatus.OK):
        """The login app's index. It decides what to show from /eden/api/state, not from the URL."""
        try:
            with open(os.path.join(LOGIN_DIST, "login.html"), "rb") as f:
                data = f.read()
        except OSError:
            self.send_plain(HTTPStatus.SERVICE_UNAVAILABLE, "Eden: the login page is not built (run pnpm build in webui/).")
            return
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", APP_CSP)
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path):
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        # assets/ names carry a content hash, so they never change; the logo may
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if "/assets/" in path else "public, max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, obj, extra_headers=()):
        b = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra_headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def read_json(self):
        """The JSON object in the body, or None (wrong type, too big, not JSON). Sends the error itself in that case."""
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "bad_request"})
            return None
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY:
                raise ValueError
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError
            return body
        except (ValueError, UnicodeDecodeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return None

    def cookie_token(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE_NAME:
                return v
        return None

    # ---- GET ----
    def do_GET(self):
        route = eden_path(self.path)
        asset = static_file(route)
        if asset:
            self.send_file(asset)
            return
        if route == "/eden/api/state":
            self.send_json(HTTPStatus.OK, app_state(self.cookie_token()))
            return
        if route == "/eden/api/home":
            self.api_home()
            return

        if not enrolled():
            remaining = enroll_remaining()
            if remaining <= 0:
                _pending_enroll.clear()
                self.send_app(HTTPStatus.FORBIDDEN)   # the app shows "configuration not available"
                return
            if route == "/eden/enroll.png":
                secret = _pending_enroll.setdefault("secret", new_totp_secret())
                png = totp_qr_png(secret, label="eden", issuer="Eden")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.send_header("Cache-Control", "no-store")   # a cached QR from an earlier window would enroll the wrong secret
                self.end_headers()
                self.wfile.write(png)
                return
            self.send_app()
            return

        if is_eden_route(route):
            # Eden's own pages, never forwarded: the upstream owns '/'.
            if route in ("/eden", "/eden/login", "/eden/home"):
                self.send_app()
                return
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        if session_valid(self.cookie_token()):
            self.proxy()
            return

        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", "/eden/login")
        self.end_headers()

    # ---- POST ----
    def do_POST(self):
        # Route first, body only for Eden's own two routes: reading the body here would consume
        # bytes the proxy still has to forward.
        route = eden_path(self.path)
        if route == "/eden/api/enroll":
            self.api_enroll()
            return
        if route == "/eden/api/login":
            self.api_login()
            return

        if is_eden_route(route):
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        # Not Eden's own: the upstream may POST to /api/... constantly, so POST must fall through to the
        # proxy. 401 rather than a redirect here - an API caller should see an error, not login HTML.
        if not session_valid(self.cookie_token()):
            self.send_plain(HTTPStatus.UNAUTHORIZED, GATE_MESSAGE)
            return
        self.proxy()

    def api_enroll(self):
        if enrolled():
            self.send_json(HTTPStatus.CONFLICT, {"error": "already_enrolled"})
            return
        remaining = enroll_remaining()
        if remaining <= 0:
            _pending_enroll.clear()
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "closed"})
            return
        body = self.read_json()
        if body is None:
            return
        ip = self.client_ip()
        key = "enroll:" + ip   # the TOTP check during enrollment is rate-limited like login, per source
        left = lock_remaining(key)
        if left > 0:
            self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "locked", "retry_after": left})
            return
        password, code = body.get("password"), body.get("totp")
        if not isinstance(password, str) or not isinstance(code, str) or len(password) > 256 or len(code) > 12:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        if not password:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "empty_password"})
            return
        secret = _pending_enroll.get("secret")
        if not secret or not verify_totp(secret, code):
            record_attempt(key, False)
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "bad_code"})
            return
        record_attempt(key, True)
        set_password(password)
        with open(TOTP_FILE, "w") as f:
            f.write(secret)
        os.chmod(TOTP_FILE, 0o600)
        _pending_enroll.clear()
        close_enroll_window()
        notify.event("enroll_completed", source=ip, detail="browser: " + clean_text(self.headers.get("User-Agent")))
        self.send_json(HTTPStatus.OK, {"ok": True})

    def api_home(self):
        """The dashboard's data: asked to Eden local (loopback, read-only) about the address this connection comes from."""
        if not enrolled() or not session_valid(self.cookie_token()):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid"})
            return
        if not EDEN_LOCAL_PORT:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
            return
        url = f"http://127.0.0.1:{EDEN_LOCAL_PORT}/api/remote/home?ip={self.client_ip()}"
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError):
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
            return
        self.send_json(HTTPStatus.OK, data)

    def api_login(self):
        if not enrolled():
            self.send_json(HTTPStatus.CONFLICT, {"error": "not_enrolled"})
            return
        body = self.read_json()
        if body is None:
            return
        ip = self.client_ip()
        left = lock_remaining(ip)
        if left > 0:
            self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "locked", "retry_after": left})
            return
        password, code = body.get("password"), body.get("totp")
        if not isinstance(password, str) or not isinstance(code, str) or len(password) > 256 or len(code) > 12:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "bad_request"})
            return
        try:
            with open(TOTP_FILE) as f:
                secret = f.read().strip()
            ok = check_password(password) and verify_totp(secret, code)
        except OSError:   # the credentials were deleted between the check above and now (re-enrollment)
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
            return
        count, locked_now = record_attempt(ip, ok)
        browser = "browser: " + clean_text(self.headers.get("User-Agent"))
        if not ok:
            notify.event("login_failed", source=ip, detail=say("ev_login_failed", count=count, browser=browser))
            if locked_now:
                _, lockout_seconds = lockout_params()
                notify.event("login_lockout", source=ip, detail=say("ev_login_lockout", count=count, minutes=lockout_seconds // 60))
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid"})
            return
        notify.event("login_success", source=ip, detail=browser)
        token = new_session()
        self.send_json(HTTPStatus.OK, {"ok": True, "next": "/eden/home"},   # the dashboard; '/' belongs to the upstream
                       [("Set-Cookie", f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/")])

    # ---- proxy (raw byte pipe; HTTP and WebSocket share it, one function for both) ----
    def proxy(self):
        """Forward to the upstream with the path verbatim: it owns its own routing, so rewriting it here would
        break it. Without an upstream a logged-in user is sent to Eden's own dashboard."""
        if not UPSTREAM_PORT:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/eden/home")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            upstream = socket.create_connection(("127.0.0.1", UPSTREAM_PORT), timeout=10)
        except OSError as e:
            self.send_plain(HTTPStatus.BAD_GATEWAY, f"upstream unreachable: {e}")
            return
        client = self.connection
        # The connect timeout must be dropped: a pipe that blocks on recv for more than 10 s would
        # otherwise raise and tear down a long generation or an idle WebSocket.
        client.setblocking(True)
        upstream.setblocking(True)
        try:
            request_line = f"{self.command} {self.path} {self.request_version}\r\n".encode()
            # The proxied response carries no Content-Length, so a client can only know the body
            # ended by seeing EOF. A keep-alive upstream never sends EOF, so the pipe would sit
            # forever: ask the upstream to close after the response. An upgrade must keep its own
            # Connection value, so it is the one case that is not rewritten.
            is_upgrade = "upgrade" in (self.headers.get("Connection") or "").lower()
            headers = b"".join(f"{k}: {v}\r\n".encode("latin-1", "replace")
                               for k, v in self.headers.items() if k.lower() != "connection")
            upstream.sendall(request_line + headers +
                             f"Connection: {'Upgrade' if is_upgrade else 'close'}\r\n\r\n".encode())
            length = int(self.headers.get("Content-Length", 0))
            if length:
                upstream.sendall(self.rfile.read(length))
            leftover = rfile_leftover(self.rfile, client)
            if leftover:
                upstream.sendall(leftover)
            self.wfile.flush()
            t1 = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
            t2 = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
            t1.start(); t2.start()
            t1.join(); t2.join()
        finally:
            try:
                upstream.close()
            except OSError:
                pass
            # The pipe consumed this connection: the server loop must not read another request here.
            self.close_connection = True

    # ---- every other method is a proxy method too ----
    def proxy_or_refuse(self):
        if is_eden_route(eden_path(self.path)):
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        if not session_valid(self.cookie_token()):
            self.send_plain(HTTPStatus.UNAUTHORIZED, GATE_MESSAGE)
            return
        self.proxy()

    def do_HEAD(self):
        self.proxy_or_refuse()

    def do_PUT(self):
        self.proxy_or_refuse()

    def do_PATCH(self):
        self.proxy_or_refuse()

    def do_DELETE(self):
        self.proxy_or_refuse()

    def do_OPTIONS(self):
        self.proxy_or_refuse()


def main():
    port = load_config()["remote_port"]
    bind = os.environ.get("EDEN_REMOTE_BIND", "0.0.0.0")  # start.sh sets this to the Meshnet IP
    httpd = ThreadingHTTPServer((bind, port), Handler)
    if not os.path.isfile(os.path.join(LOGIN_DIST, "login.html")):
        print(f"eden_remote: WARNING {LOGIN_DIST}/login.html is missing: build it with 'pnpm build' in webui/", file=sys.stderr)
    print(f"eden_remote listening on {bind}:{port} (enrolled={enrolled()})")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
