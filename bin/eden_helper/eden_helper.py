#!/usr/bin/python3 -I
# Installed copy (the one sudo runs): /usr/local/libexec/eden/eden_helper.py
#
# Eden root helper. Fixed command set, standard library only, no free-form input:
# it never receives nft rules or shell text, only validated parameters, and it
# builds every command itself. Stores nothing. Every action goes to the system
# journal (syslog), which the calling user cannot edit.
#
# Commands:
#   daemon-start | daemon-stop        start/stop the Nord daemon units
#   nft-load [--rule PORT:IP ...]     atomically (re)load table "inet eden" [--check = syntax only]
#                                     (no --rule = guard table: drop everything on the Meshnet interface;
#                                     both tables also drop all forwarded traffic in or out of it, and both accept
#                                     the replies to connections that THIS host started on the Meshnet interface)
#   nft-delete                        remove table "inet eden" (idempotent)
#   nft-list                          print table "inet eden" (read only)
#   ports-list                        print the ports Eden may open, one per line (read only)
#
# The allowed ports live in /etc/eden/allowed_ports (root-owned, edited with sudo): see PORTS_FILE.

import argparse
import ipaddress
import os
import re
import subprocess
import sys
import syslog

# Absolute binaries: never resolved through the caller's PATH.
SYSTEMCTL = "/usr/bin/systemctl"
NFT = "/usr/sbin/nft"

NORD_UNITS_START = ("nordvpnd.socket", "nordvpnd.service")
NORD_UNITS_STOP = ("nordvpnd.service", "nordvpnd.socket")

MESH_NET = ipaddress.ip_network("100.64.0.0/10")   # Meshnet range
MESH_IFACE = "nordlynx"
TABLE = "eden"
MAX_RULES = 32

# Only ports Eden may open on the Meshnet interface. They come from a root-owned file, one port
# per line ("#" starts a comment), edited with sudo: the user can run this helper but cannot edit
# the file, so Eden local can show the list but never widen it, and no reinstall is needed.
# File missing = only DEFAULT_ALLOWED_PORTS. File present but unsafe or malformed = error (fail
# closed), never a fallback to something wider. An empty file means "nothing may be opened".
PORTS_FILE = "/etc/eden/allowed_ports"
DEFAULT_ALLOWED_PORTS = (8443,)   # Eden remote (login + TOTP); everything else must be listed in the file
MAX_ALLOWED_PORTS = 64


def log(msg):
    syslog.openlog("eden-helper", 0, syslog.LOG_AUTH)
    syslog.syslog(syslog.LOG_INFO, f"user={os.environ.get('SUDO_USER', '?')} {msg}")


def fail(msg, code=1):
    log(f"FAIL {msg}")
    print(f"eden-helper: {msg}", file=sys.stderr)
    sys.exit(code)


def unsafe_reason(path):
    """None if `path` and every parent directory (symlinks resolved) are root-owned and
    not group/other-writable, otherwise the reason. Used for this script and the ports file."""
    try:
        p = os.path.realpath(path)
        while True:
            st = os.stat(p)
            if st.st_uid != 0 or st.st_mode & 0o022:
                return f"{p} must be root-owned and not group/other-writable"
            if p == "/":
                return None
            p = os.path.dirname(p)
    except OSError as e:
        return f"cannot check {path}: {e}"


def check_install_integrity():
    """Refuse to run if this file or any parent directory is not root-owned
    and non-writable by others: otherwise the sudoers rule would be a hole."""
    reason = unsafe_reason(__file__)
    if reason:
        fail(f"unsafe install: {reason}", 3)


_allowed_ports = None


def load_allowed_ports():
    """The set of ports Eden may open (see PORTS_FILE). Raises ValueError with a readable reason."""
    global _allowed_ports
    if _allowed_ports is not None:
        return _allowed_ports
    if not os.path.lexists(PORTS_FILE):
        _allowed_ports = frozenset(DEFAULT_ALLOWED_PORTS)
        return _allowed_ports
    reason = unsafe_reason(PORTS_FILE)
    if reason:
        raise ValueError(f"unsafe ports file: {reason}")
    ports = set()
    try:
        with open(PORTS_FILE) as f:
            for lineno, raw in enumerate(f, 1):
                text = raw.split("#", 1)[0].strip()
                if not text:
                    continue
                if not re.fullmatch(r"[0-9]{1,5}", text) or not 1 <= int(text) <= 65535:
                    raise ValueError(f"{PORTS_FILE}:{lineno}: not a valid port: {text!r}")
                ports.add(int(text))
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"cannot read {PORTS_FILE}: {e}")
    if len(ports) > MAX_ALLOWED_PORTS:
        raise ValueError(f"{PORTS_FILE}: too many ports (max {MAX_ALLOWED_PORTS})")
    _allowed_ports = frozenset(ports)
    return _allowed_ports


def run(argv, stdin=None):
    """Run a fixed command with a minimal environment."""
    return subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=30,
                          env={"PATH": "/usr/bin:/usr/sbin"})


def mesh_ip(value):
    try:
        ip = ipaddress.IPv4Address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an IPv4 address: {value!r}")
    if ip not in MESH_NET:
        raise argparse.ArgumentTypeError(f"{ip} is outside the Meshnet range {MESH_NET}")
    return ip


def allowed_port(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a port number: {value!r}")
    try:
        allowed = load_allowed_ports()
    except ValueError as e:                  # argparse would swallow a bare ValueError into a generic message
        raise argparse.ArgumentTypeError(str(e))
    if port not in allowed:
        raise argparse.ArgumentTypeError(f"port {port} is not in the allowed list ({PORTS_FILE})")
    return port


def rule_pair(value):
    """'PORT:IP' -> (validated port, validated Meshnet ip). This is the only way
    to specify a rule: no free-form ports or addresses reach nft."""
    port_s, sep, ip_s = value.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError(f"expected PORT:IP, got {value!r}")
    return allowed_port(port_s), mesh_ip(ip_s)


def build_ruleset(pairs):
    """Atomic replace of the table: accept only the given (port, ip) pairs, drop
    everything else arriving on the Meshnet interface. Priority -10 runs before
    Nord's own table, so Eden can only narrow access, never widen it. A service
    that is off simply has no pair here, so its port is dropped like any other -
    no separate "disable" path, no leftover attack surface.
    The forward chain drops everything routed in or out of the Meshnet interface, always, also in the guard
    table: this host has IPv4 forwarding on, and without this chain a Meshnet peer could use it as a router
    towards the LAN (Meshnet routing and local-network permissions are denied, but this does not depend on them).
    Eden never needs kernel forwarding on that interface: its forwarder is a userspace process.
    The first input rule accepts packets in the REPLY direction of a connection that this host started (a client
    on the Meshnet, for example this computer calling a service of a peer): without it the final drop would discard the
    answers. `ct direction reply` is deliberate: a connection a peer started is in the original direction, so it is
    still accepted only by a (port, ip) pair below, and revoking a pair cuts that peer's connections at once.
    Nothing here opens a port for a peer."""
    rules = "\n".join(
        f'    iifname "{MESH_IFACE}" ip saddr {ip} tcp dport {port} accept'
        for port, ip in sorted(set(pairs)))
    return (
        f"add table inet {TABLE}\n"
        f"delete table inet {TABLE}\n"
        f"table inet {TABLE} {{\n"
        f"  chain input {{\n"
        f"    type filter hook input priority -10; policy accept;\n"
        f'    ct direction reply ct state established iifname "{MESH_IFACE}" accept\n'
        f"{rules}\n"
        f'    iifname "{MESH_IFACE}" drop\n'
        f"  }}\n"
        f"  chain forward {{\n"
        f"    type filter hook forward priority -10; policy accept;\n"
        f'    iifname "{MESH_IFACE}" drop\n'
        f'    oifname "{MESH_IFACE}" drop\n'
        f"  }}\n"
        f"}}\n")


def parse():
    ap = argparse.ArgumentParser(prog="eden_helper", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daemon-start")
    sub.add_parser("daemon-stop")
    load = sub.add_parser("nft-load", allow_abbrev=False)
    load.add_argument("--rule", type=rule_pair, action="append", default=[],
                      metavar="PORT:IP", help="repeatable; no --rule = guard table (drop-all)")
    load.add_argument("--check", action="store_true", help="syntax check only, load nothing")
    sub.add_parser("nft-delete")
    sub.add_parser("nft-list")
    sub.add_parser("ports-list")
    return ap.parse_args()


def main():
    args = parse()                       # every parameter is validated before anything else
    if os.geteuid() != 0:
        fail("must run as root (through sudo)", 4)
    check_install_integrity()

    if args.cmd in ("daemon-start", "daemon-stop"):
        verb = "start" if args.cmd == "daemon-start" else "stop"
        units = NORD_UNITS_START if verb == "start" else NORD_UNITS_STOP
        r = run([SYSTEMCTL, verb, *units])
        if r.returncode:
            fail(f"systemctl {verb} failed: {r.stderr.strip()}")
        log(f"OK {args.cmd}")

    elif args.cmd == "nft-load":
        pairs = sorted(set(args.rule))
        if len(pairs) > MAX_RULES:
            fail(f"too many rules (max {MAX_RULES})", 2)
        ruleset = build_ruleset(pairs)
        r = run([NFT, *(["-c"] if args.check else []), "-f", "-"], stdin=ruleset)
        if r.returncode:
            fail(f"nft rejected the ruleset: {r.stderr.strip()}")
        summary = ",".join(f"{p}:{ip}" for p, ip in pairs)
        log(f"OK nft-load{' (check only)' if args.check else ''} rules={summary or '(none, guard table)'}")

    elif args.cmd == "nft-delete":
        r = run([NFT, "-f", "-"], stdin=f"add table inet {TABLE}\ndelete table inet {TABLE}\n")
        if r.returncode:
            fail(f"nft delete failed: {r.stderr.strip()}")
        log("OK nft-delete")

    elif args.cmd == "nft-list":
        r = run([NFT, "list", "table", "inet", TABLE])
        if r.returncode:
            fail(f"table inet {TABLE} not loaded")
        print(r.stdout, end="")

    elif args.cmd == "ports-list":
        try:
            ports = load_allowed_ports()
        except ValueError as e:
            fail(str(e))
        print("\n".join(str(p) for p in sorted(ports)))


if __name__ == "__main__":
    main()
