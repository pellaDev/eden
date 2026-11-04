#!/usr/bin/env python3
#
# Eden forwarder: for services that listen only on 127.0.0.1 (e.g. llama.cpp). It accepts connections on the
# Meshnet address, on the same port as the service, and relays them to 127.0.0.1:port. It is a second security
# layer next to the nft table, and the service itself stays closed to everything but loopback:
#   - binds ONLY the Meshnet address: it refuses to start on anything outside 100.64.0.0/10 (never 0.0.0.0)
#   - relays ONLY to 127.0.0.1: fixed in this file, not configurable
#   - accepts ONLY the source IPs listed for that port (the same (port, ip) pairs eden_ctl gives to nft) and
#     closes any other connection right at accept
#   - when an IP is removed from a route (device disabled, grant revoked) its live connections are closed at once
# Routes come from $EDEN_RUN/forward.json, written atomically by eden_ctl; the file is re-read on SIGHUP and
# whenever it changes. A missing or corrupt file means no routes (fail closed). The state of each route for the
# UI goes to $EDEN_RUN/forward.status.json. Standard library only; runs as the normal user (ports >= 1024).
#
# Environment (exported by start.sh): EDEN_FORWARD_BIND (the Meshnet address), EDEN_RUN.

import asyncio
import errno
import ipaddress
import json
import os
import signal
import socket
import sys
import tempfile
import time

TARGET_HOST = "127.0.0.1"          # fixed on purpose: this process never relays anywhere else
MESH_NET = ipaddress.ip_network("100.64.0.0/10")
MIN_PORT = 1024                    # unprivileged ports only
MAX_CONN_PER_ROUTE = 128
CONNECT_TIMEOUT = 3.0
POLL_SECONDS = 1.0                 # how often the routes file is checked for changes
RETRY_SECONDS = 10.0               # how often a route that could not listen is retried
BUF_SIZE = 64 * 1024
LOG_QUIET_SECONDS = 60.0           # a denied/failed source is logged at most once per this time

BIND = ""
ROUTES_FILE = ""
STATUS_FILE = ""
RUN_DIR = ""

routes = {}    # port -> Route (listening)
failed = {}    # port -> (detail, retry_at) for routes that could not listen
_quiet = {}    # log key -> last time logged


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} eden_forward: {msg}", flush=True)


def log_once(key, msg):
    """Log at most once per LOG_QUIET_SECONDS for the same key (a scanner must not flood the log)."""
    now = time.monotonic()
    if now - _quiet.get(key, -LOG_QUIET_SECONDS) >= LOG_QUIET_SECONDS:
        if len(_quiet) > 1000:
            _quiet.clear()
        _quiet[key] = now
        log(msg)


class Route:
    def __init__(self, port, allow):
        self.port = port
        self.allow = set(allow)
        self.server = None
        self.conns = {}      # source ip -> set of live Conn
        self.session = {}    # source ip -> [bytes to service, bytes from service, started]: one "session" = first to last connection


class Conn:
    def __init__(self, ip, writers):
        self.ip = ip
        self.writers = writers

    def abort(self):
        for w in self.writers:
            try:
                w.transport.abort()
            except (OSError, AttributeError):
                pass


def keepalive(writer):
    """Detect dead peers on long-lived connections (llama.cpp streams can last minutes)."""
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for opt, val in (("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 15), ("TCP_KEEPCNT", 4)):
            if hasattr(socket, opt):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
    except OSError:
        pass


async def relay(src, dst, stats, index):
    """Copy src -> dst until EOF (True) or error (False). EOF is passed on as a half-close."""
    try:
        while True:
            data = await src.read(BUF_SIZE)
            if not data:
                break
            dst.write(data)
            await dst.drain()
            stats[index] += len(data)
    except (OSError, asyncio.IncompleteReadError):
        return False
    try:
        if dst.can_write_eof():
            dst.write_eof()
    except OSError:
        return False
    return True


def task_failed(task):
    return task.cancelled() or task.exception() is not None or task.result() is False


async def handle(route, client_r, client_w):
    peer = client_w.get_extra_info("peername")
    ip = peer[0] if peer else "?"
    up_w = None
    conn = None
    try:
        if routes.get(route.port) is not route or ip not in route.allow:
            log_once(("deny", route.port, ip), f"denied port={route.port} from={ip}")
            return
        if sum(len(c) for c in route.conns.values()) >= MAX_CONN_PER_ROUTE:
            log_once(("full", route.port), f"too many connections on port={route.port}, refusing {ip}")
            return
        try:
            up_r, up_w = await asyncio.wait_for(asyncio.open_connection(TARGET_HOST, route.port), CONNECT_TIMEOUT)
        except (OSError, asyncio.TimeoutError) as e:
            log_once(("up", route.port), f"cannot reach {TARGET_HOST}:{route.port}: {e!r}")
            return
        if routes.get(route.port) is not route or ip not in route.allow:   # revoked while connecting
            return
        keepalive(client_w)
        keepalive(up_w)
        conn = Conn(ip, (client_w, up_w))
        if not route.conns.get(ip):
            route.session[ip] = [0, 0, time.monotonic()]
            log(f"open port={route.port} from={ip}")
        route.conns.setdefault(ip, set()).add(conn)
        stats = route.session[ip]
        tasks = [asyncio.ensure_future(relay(client_r, up_w, stats, 0)), asyncio.ensure_future(relay(up_r, client_w, stats, 1))]
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            if any(task_failed(t) for t in done):    # one side broke: do not leave the other waiting forever
                for t in pending:
                    t.cancel()
                break
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if conn is not None:
            live = route.conns.get(ip)
            if live is not None:
                live.discard(conn)
                if not live:
                    route.conns.pop(ip, None)
                    up, down, started = route.session.pop(ip, [0, 0, time.monotonic()])
                    log(f"closed port={route.port} from={ip} to_service={up}B from_service={down}B after {time.monotonic() - started:.0f}s")
        for w in (client_w, up_w):
            if w is not None:
                try:
                    w.close()
                except OSError:
                    pass


def read_desired():
    """{port: set of allowed source IPs} from the routes file. Missing or corrupt = {} (fail closed)."""
    try:
        with open(ROUTES_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        log_once(("badfile",), f"cannot read {ROUTES_FILE}: {e}; no routes")
        return {}
    entries = data.get("routes") if isinstance(data, dict) else None
    desired = {}
    for entry in entries if isinstance(entries, list) else []:
        try:
            port = entry["port"]
            allow = {str(ipaddress.IPv4Address(x)) for x in entry["allow"]}
            if isinstance(port, bool) or not isinstance(port, int) or not MIN_PORT <= port <= 65535:
                raise ValueError(f"port {port!r} is not in {MIN_PORT}-65535")
            if any(ipaddress.IPv4Address(x) not in MESH_NET for x in allow):
                raise ValueError("source addresses must be Meshnet addresses")
        except (KeyError, TypeError, ValueError) as e:
            log_once(("badentry", str(entry)), f"ignoring route {entry!r}: {e}")
            continue
        if allow:
            desired[port] = allow
    return desired


async def open_route(port, allow):
    route = Route(port, allow)
    try:
        route.server = await asyncio.start_server(lambda r, w: handle(route, r, w), host=BIND, port=port)
    except OSError as e:
        detail = ("la porta è già in uso sull'indirizzo Meshnet: il servizio ascolta già su tutte le interfacce? "
                  "Spegni l'inoltro" if e.errno == errno.EADDRINUSE else str(e))
        failed[port] = (detail, time.monotonic() + RETRY_SECONDS)
        log_once(("open", port), f"cannot listen on {BIND}:{port}: {e}")
        return
    routes[port] = route
    failed.pop(port, None)
    log(f"listening {BIND}:{port} -> {TARGET_HOST}:{port} allow={sorted(allow)}")


def kill_connections(route, ips):
    for ip in ips:
        for conn in list(route.conns.get(ip, ())):
            conn.abort()


async def close_route(port, why):
    route = routes.pop(port, None)
    if route is None:
        return
    route.server.close()
    kill_connections(route, list(route.conns))
    try:
        await asyncio.wait_for(route.server.wait_closed(), 2.0)
    except (asyncio.TimeoutError, OSError):
        pass
    log(f"closed listener port={port} ({why})")


def write_status(desired):
    state = {"bind": BIND, "updated": int(time.time()), "routes": {}}
    for port, allow in desired.items():
        if port in routes:
            state["routes"][str(port)] = {"state": "listening", "allow": sorted(allow)}
        elif port in failed:
            state["routes"][str(port)] = {"state": "error", "detail": failed[port][0]}
    fd, tmp = tempfile.mkstemp(dir=RUN_DIR, prefix=".forward.status.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        if os.path.exists(tmp):
            os.unlink(tmp)


async def reconcile(force):
    """Make the listeners match the routes file. `force` also retries routes that failed to listen."""
    desired = read_desired()
    for port in list(routes):
        if port not in desired:
            await close_route(port, "route removed")
    for port in list(failed):
        if port not in desired:
            failed.pop(port)
    for port, allow in desired.items():
        route = routes.get(port)
        if route is None:
            if port in failed and not force and time.monotonic() < failed[port][1]:
                continue
            await open_route(port, allow)
        elif route.allow != allow:
            removed = route.allow - allow
            route.allow = set(allow)
            kill_connections(route, removed)      # revoked sources lose their live connections immediately
            log(f"port={port} allow={sorted(allow)}" + (f" (closed connections of {sorted(removed)})" if removed else ""))
    write_status(desired)


def file_signature():
    try:
        st = os.stat(ROUTES_FILE)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


async def main():
    loop = asyncio.get_running_loop()
    wake, stop = asyncio.Event(), asyncio.Event()
    loop.add_signal_handler(signal.SIGHUP, wake.set)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log(f"started, bind={BIND}")
    last_signature = None
    write_status({})
    while not stop.is_set():
        signature = file_signature()
        retry_due = any(at <= time.monotonic() for _, at in failed.values())
        if wake.is_set() or signature != last_signature or retry_due:
            forced = wake.is_set() or signature != last_signature
            wake.clear()
            last_signature = signature
            await reconcile(forced)
        # Sleep until the next poll, but wake at once on SIGHUP (reload) or on a stop signal.
        waiters = [asyncio.ensure_future(stop.wait()), asyncio.ensure_future(wake.wait())]
        await asyncio.wait(waiters, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED)
        for waiter in waiters:
            waiter.cancel()
    for port in list(routes):
        await close_route(port, "shutting down")
    try:
        os.unlink(STATUS_FILE)
    except OSError:
        pass
    log("stopped")


def configure(bind, run_dir):
    global BIND, RUN_DIR, ROUTES_FILE, STATUS_FILE
    try:
        address = ipaddress.IPv4Address(bind)
    except ValueError:
        sys.exit(f"eden_forward: EDEN_FORWARD_BIND is not an IPv4 address: {bind!r}")
    if address not in MESH_NET:
        sys.exit(f"eden_forward: bind address {address} is outside the Meshnet range {MESH_NET}, refusing to start")
    BIND, RUN_DIR = str(address), run_dir
    ROUTES_FILE = os.path.join(run_dir, "forward.json")
    STATUS_FILE = os.path.join(run_dir, "forward.status.json")


def cli():
    for name in ("EDEN_FORWARD_BIND", "EDEN_RUN"):
        if not os.environ.get(name):
            sys.exit(f"eden_forward: {name} is not set (run through start.sh)")
    configure(os.environ["EDEN_FORWARD_BIND"], os.environ["EDEN_RUN"])
    asyncio.run(main())


if __name__ == "__main__":
    cli()
