#!/usr/bin/env python3
# Eden control, Nord/Meshnet side. Runs as the normal user (standard library only).
# Root actions go through the root helper with "sudo -n". Devices are identified by
# public key, never by nickname/hostname/IP (those get reassigned). Configuration
# comes from environment variables exported by start.sh (vars.env).
#
# Commands:
#   settings          enforce Nord settings: fail if routing/auto-connect/kill switch are on,
#                     switch notify/tray/virtual-location off
#   peers             resolve configured devices against the live peer list (JSON)
#   nft-guard         load the guard table: drop everything on the Meshnet interface
#   nft-final         load the final table: accept only resolved, enabled devices on the Eden port
#   incoming allow    allow incoming traffic for resolved, enabled devices only
#   deny-all          deny incoming + fileshare for EVERY local peer (used by down)
#   nord-settings     read-only JSON of the Nord settings Eden controls (needs the daemon)
#   live-peers        live peers (local and external) as JSON (nickname, hostname, ip, public_key,
#                     status, external, allow_in, allows_in)
#   reload            re-apply nft rules AND incoming permissions from the config while the
#                     VPN is up; with no enabled device it loads the guard table (drop-all)
#
# Untrusted devices: a device with "untrusted" set in the config (anything but false counts), or
# any peer Nord lists under "External Peers" (another account), is untrusted. It never gets the
# remote-login port (a configuration that tries is refused and the guard table is loaded), only the
# services granted to it, and Meshnet routing, local-network access and file sharing stay denied
# (set after every change, then read back from the peer list).

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile

# The policy (which pairs may be open) is shared with the Windows edition and lives in core/.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "core"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Everything that runs or reads the nordvpn command lives in nord_cli.py (one place to fix when Nord changes its output).
from nord_cli import EXTERNAL, NordFormatError, nordvpn, parse_peer_list, parse_settings, peer_target  # noqa: E402,F401
import nord_cli  # noqa: E402
from eden_policy import PolicyError, compute_pairs, flag_untrusted, forward_routes, rule_pairs  # noqa: E402,F401

MUST_BE_OFF = ("Routing", "Kill Switch", "Auto-connect")
FORCE_OFF = {"Notify": "notify", "Tray": "tray", "Virtual Location": "virtual-location"}

# Permissions an untrusted peer must never hold: peer subcommand -> peer-list field ("Allow <field>" is OUR grant).
UNTRUSTED_DENIED = {"routing": "Routing", "local": "Local Network Access", "fileshare": "Sending Files"}


def env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"eden_ctl: {name} is not set (run through start.sh)")
    return value


def helper_output(*args):
    """Run a root helper command through sudo; returns its stdout, exits on failure."""
    r = subprocess.run(["sudo", "-n", env("EDEN_HELPER"), *map(str, args)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode:
        sys.exit(f"eden_ctl: helper {args[0]} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def helper(*args):
    helper_output(*args)


def allowed_ports():
    """Ports the root helper will accept: the single source of truth is its root-owned ports file."""
    return {int(x) for x in helper_output("ports-list").split()}


def is_untrusted(dev, peer):
    """True for a device the config marks untrusted, or whose live peer is external. Fail closed: any value of
    the config flag other than false (true, null, garbage) means untrusted. A missing flag is a trusted device
    created before this feature existed."""
    if flag_untrusted(dev):
        return True
    return bool(peer and peer.get(EXTERNAL))


def untrusted_keys(config, peers):
    """Public keys of every untrusted peer: external ones (configured or not) and the configured untrusted ones."""
    by_key = {p.get("Public Key"): p for p in peers}
    keys = {k for k, p in by_key.items() if p.get(EXTERNAL)}
    keys |= {d["public_key"] for d in config["devices"] if is_untrusted(d, by_key.get(d["public_key"]))}
    return keys


def load_config():
    with open(env("EDEN_CONFIG")) as f:
        return json.load(f)


def live_peers():
    rc, out = nordvpn("meshnet", "peer", "list")
    if rc:
        sys.exit(f"eden_ctl: peer list failed: {out.strip()}")
    this, peers = parse_peer_list(out)
    try:
        nord_cli.check_peer_list(out, this, peers)
    except NordFormatError as e:
        sys.exit(f"eden_ctl: Nord's output is not what Eden expects: {e}")
    return peers


def resolve(config, peers):
    """Match configured devices to live peers by public key."""
    by_key = {p.get("Public Key"): p for p in peers}
    return [{"name": d["name"], "enabled": d.get("enabled", True),
             "peer": by_key.get(d["public_key"]),
             "untrusted": is_untrusted(d, by_key.get(d["public_key"]))} for d in config["devices"]]


def cmd_settings(_):
    rc, out = nordvpn("settings")
    if rc:
        sys.exit(f"eden_ctl: settings failed: {out.strip()}")
    s = parse_settings(out)
    unknown = [k for k in MUST_BE_OFF if k not in s]
    if unknown:
        # A missing safety setting cannot be verified: refuse, and say it is the format, not the value.
        sys.exit(f"eden_ctl: Nord's output is not what Eden expects: 'nordvpn settings' does not report {', '.join(unknown)}; "
                 "cannot verify that it is disabled")
    bad = [k for k in MUST_BE_OFF if s.get(k) != "disabled"]
    if bad:
        sys.exit(f"eden_ctl: refusing to continue, must be disabled: {', '.join(bad)}")
    for key, name in FORCE_OFF.items():
        if key not in s:
            # A Nord version that no longer has the setting (6.0.1 dropped "Virtual Location"): nothing to switch
            # off. Only the forced-off cosmetics are skipped this way; the MUST_BE_OFF checks above stay strict,
            # because a missing safety setting cannot be verified.
            print(f"eden_ctl: note: this Nord version reports no '{key}' setting, skipped", file=sys.stderr)
            continue
        if s[key] != "disabled":
            rc, out = nordvpn("set", name, "off")
            if rc:
                sys.exit(f"eden_ctl: could not set {name} off: {out.strip()}")
    print("settings ok")


def cmd_peers(_):
    print(json.dumps(resolve(load_config(), live_peers()), indent=2))


def cmd_nft_guard(_):
    helper("nft-load")   # no --rule at all = drop-all guard table
    print("guard table loaded (drop-all on the Meshnet interface)")


def compute_rules(config, peers):
    """(ips, pairs) for the current config and live peers: the Nord peer list is resolved to plain devices here
    (Linux side), and the policy itself lives in core/eden_policy.py, shared with the Windows edition."""
    devices = [{"name": d["name"], "enabled": d["enabled"], "ip": d["peer"]["IP"] if d["peer"] else None,
                "untrusted": d["untrusted"]} for d in resolve(config, peers)]
    return compute_pairs(config, devices, allowed_ports())


def fail_closed(error):
    """A rule the design forbids was asked for: close everything (forwarder without routes, drop-all guard table)
    and stop with an error, instead of loading a quietly filtered table."""
    try:
        write_forward([])
        helper("nft-load")
    except SystemExit:
        pass    # already reported on stderr; the exit below is non-zero anyway
    sys.exit(f"eden_ctl: refused, guard table loaded (drop-all): {error}")


def forwarder_pid():
    """PID of the running forwarder from its pid file, confirmed through /proc: a stale pid file must never
    make us signal an unrelated process."""
    try:
        with open(os.path.join(env("EDEN_RUN"), "eden_forward.pid")) as f:
            pid = int(f.read().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return pid if b"eden_forward.py" in f.read() else None
    except (OSError, ValueError):
        return None


def write_forward(routes):
    """Hand the forwarder its routes: atomic file, then SIGHUP so it reloads at once (it also polls the file).
    Always called BEFORE the nft rules are loaded: when something opens, the forwarder is listening first; when
    something closes, the forwarder lets go first. If the file cannot be written the load stops (fail closed)."""
    path = os.path.join(env("EDEN_RUN"), "forward.json")
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".forward.json.")
        with os.fdopen(fd, "w") as f:
            json.dump({"routes": routes}, f)
        os.replace(tmp, path)
    except OSError as e:
        sys.exit(f"eden_ctl: cannot write the forwarder routes: {e}")
    pid = forwarder_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError:
            pass


def deny_extras(peer):
    """Routing, local-network access and file sharing are never granted to an untrusted peer: deny all three.
    Returns the number of failed commands ("already denied" is the desired state)."""
    failed, target = 0, peer_target(peer)
    for verb in UNTRUSTED_DENIED:
        rc, out = nordvpn("meshnet", "peer", verb, "deny", target)
        if rc and "already" not in out.lower():
            failed += 1
            print(f"eden_ctl: {verb} deny failed for {target}: {out.strip()}", file=sys.stderr)
    return failed


def verify_untrusted(config, peers, wanted):
    """Read the peer list back and check what the CLI reports as OUR grants ("Allow ..." lines; "Allows ..." is
    the peer's side). For every untrusted peer routing, local-network access and file sharing must read
    "disabled": anything else (or a missing line) counts as a failure, so a changed Nord output format fails
    closed instead of passing unnoticed. Incoming that differs from the config is only warned about.
    Returns the number of failures."""
    untrusted = untrusted_keys(config, peers)
    if not untrusted:
        return 0
    try:
        fresh = live_peers()
    except SystemExit as e:
        print(f"eden_ctl: cannot read the permissions back: {e}", file=sys.stderr)
        return 1
    failed = 0
    for p in fresh:
        key, label = p.get("Public Key"), peer_target(p)
        if key in untrusted:
            for field in UNTRUSTED_DENIED.values():
                value = p.get(f"Allow {field}", "").lower()
                if value != "disabled":
                    failed += 1
                    print(f"eden_ctl: untrusted peer {label} still has '{field}' = {value or 'missing'}", file=sys.stderr)
        want = "enabled" if key in wanted else "disabled"
        if p.get("Allow Incoming Traffic", "").lower() != want:
            print(f"eden_ctl: warning: incoming for {label} reads '{p.get('Allow Incoming Traffic', 'missing')}', "
                  f"expected '{want}'", file=sys.stderr)
    return failed


def sync_incoming(config, peers):
    """Make Meshnet's per-peer incoming permission match the config: allowed for
    enabled devices, denied for every other peer (disabled or not configured, external
    included). For untrusted peers (configured as such, or external) routing, local-network
    access and file sharing are denied as well, then read back (verify_untrusted).
    Always issues the command, and an "already allowed/denied" reply from the CLI is
    treated as success."""
    wanted = {d["public_key"] for d in config["devices"] if d.get("enabled", True)}
    untrusted = untrusted_keys(config, peers)
    failed = 0
    for p in peers:
        target = peer_target(p)
        if not target:
            continue
        verb = "allow" if p.get("Public Key") in wanted else "deny"
        rc, out = nordvpn("meshnet", "peer", "incoming", verb, target)
        if rc and "already" not in out.lower():
            failed += 1
            print(f"eden_ctl: incoming {verb} failed for {target}: {out.strip()}", file=sys.stderr)
        if p.get("Public Key") in untrusted:
            failed += deny_extras(p)
    return failed + verify_untrusted(config, peers, wanted)


def cmd_nft_final(_):
    config = load_config()
    try:
        ips, pairs = compute_rules(config, live_peers())
    except PolicyError as e:
        fail_closed(e)
    # An empty configuration is a legitimate state, not a failure: nothing is exposed, the guard table already
    # drops everything. Exiting non-zero here used to deadlock a fresh install - the device list needs the daemon
    # and Meshnet up, and vpn-up tore the whole VPN group down, so no device could ever be added. Same shape as
    # cmd_reload: guard table, no rules, exit 0.
    if not ips:
        write_forward([])
        print("final table loaded: no enabled device yet, guard table only (drop-all), nothing exposed")
        return

    allowed = allowed_ports()

    write_forward(forward_routes(config, pairs))     # forwarder first, firewall second
    helper("nft-load", *[f"--rule={p}:{ip}" for p, ip in sorted(pairs)])
    on_services = [s["name"] for s in config.get("services", []) if s.get("enabled") and s["port"] in allowed]
    print(f"final table loaded: {len(ips)} device(s) on remote access, "
          f"services on: {', '.join(on_services) or '(none)'}")


def cmd_incoming_allow(_):
    for d in resolve(load_config(), live_peers()):
        if not d["enabled"]:
            continue
        if not d["peer"]:
            if d["untrusted"]:
                # An outside guest can unlink himself at any time: that must not stop Eden from starting.
                print(f"eden_ctl: untrusted device {d['name']} not in the peer list, skipped", file=sys.stderr)
                continue
            sys.exit(f"eden_ctl: device {d['name']} not found in the peer list (public key mismatch?)")
        rc, out = nordvpn("meshnet", "peer", "incoming", "allow", peer_target(d["peer"]))
        if rc and "already" not in out.lower():   # "already allowed" is the desired state (an interrupted run leaves it behind)
            sys.exit(f"eden_ctl: incoming allow failed for {d['name']}: {out.strip()}")
        if d["untrusted"] and deny_extras(d["peer"]):
            sys.exit(f"eden_ctl: could not deny routing/local network/file sharing for untrusted device {d['name']}")
        print(f"incoming allowed: {d['name']}")


def cmd_deny_all(_):
    failed = 0
    for p in live_peers():
        target = peer_target(p)
        if not target:
            continue
        for verb in ("incoming", "fileshare"):
            rc, out = nordvpn("meshnet", "peer", verb, "deny", target)
            if rc and "already" not in out.lower():   # already denied = desired state
                failed += 1
                print(f"eden_ctl: {verb} deny failed for {target}: {out.strip()}", file=sys.stderr)
    print("all peers denied" if not failed else f"{failed} deny command(s) failed")
    sys.exit(1 if failed else 0)


def cmd_nord_settings(_):
    rc, out = nordvpn("settings")
    if rc:
        sys.exit(f"eden_ctl: settings failed: {out.strip()}")
    s = parse_settings(out)
    print(json.dumps([{"name": k, "value": s.get(k, "?")} for k in (*MUST_BE_OFF, *FORCE_OFF)]))


def cmd_live_peers(_):
    # Nord prints "-" for a peer with no nickname: report it as empty, so no screen shows a dash as the device name.
    print(json.dumps([{"nickname": "" if p.get("Nickname", "") == "-" else p.get("Nickname", ""), "hostname": p.get("Hostname", ""),
                       "ip": p.get("IP", ""), "public_key": p.get("Public Key", ""),
                       "status": p.get("Status", ""), "external": bool(p.get(EXTERNAL)),
                       # Direction of the link, as Nord reports it: "Allow ..." is OUR grant toward the peer (it can reach
                       # this machine), "Allows ..." is the peer's grant toward us (we can reach it, it offers us its ports).
                       "allow_in": p.get("Allow Incoming Traffic", "").lower() == "enabled",
                       "allows_in": p.get("Allows Incoming Traffic", "").lower() == "enabled"} for p in live_peers()]))


def cmd_reload(_):
    config, peers = load_config(), live_peers()
    try:
        ips, pairs = compute_rules(config, peers)
    except PolicyError as e:
        fail_closed(e)
    write_forward(forward_routes(config, pairs))     # forwarder first, firewall second
    helper("nft-load", *[f"--rule={p}:{ip}" for p, ip in sorted(pairs)])
    print(f"rules reloaded: {len(ips)} device(s) on remote access" if ips
          else "rules reloaded: no enabled device, guard table (drop-all)")
    failed = sync_incoming(config, peers)
    sys.exit(1 if failed else 0)


def main():
    ap = argparse.ArgumentParser(prog="eden_ctl", allow_abbrev=False)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("settings", cmd_settings), ("peers", cmd_peers), ("nft-guard", cmd_nft_guard),
                     ("nft-final", cmd_nft_final), ("deny-all", cmd_deny_all),
                     ("live-peers", cmd_live_peers), ("reload", cmd_reload),
                     ("nord-settings", cmd_nord_settings)):
        sub.add_parser(name).set_defaults(fn=fn)
    inc = sub.add_parser("incoming")
    inc.add_argument("action", choices=["allow"])
    inc.set_defaults(fn=cmd_incoming_allow)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
