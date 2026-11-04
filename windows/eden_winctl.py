# Eden, Windows edition: the counterpart of bin/eden_ctl/eden_ctl.py. It turns eden.json into the open (port, address)
# pairs with the shared policy (core/eden_policy.py) and hands them to the elevated helper. There is no Nord CLI on
# Windows, so devices are identified by the Meshnet ADDRESS typed by the user ("address" in eden.json), not by public
# key, and a device is untrusted unless the config says otherwise is NOT possible: a missing or garbage flag counts as
# untrusted for devices added on Windows (see new_device in eden_local's Windows overrides). Nothing of this file is
# imported by the Linux edition.
#
#   guard     block everything from the Meshnet adapter (Eden down, or any failure)
#   final     compute the pairs from the config, hand the forwarder its routes, apply the pairs
#   reload    same as final (the launcher calls it while the VPN is up)
#   deny-all  same as guard
# Environment (set by eden.py): EDEN_CONFIG, EDEN_RUN.

import ipaddress
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eden_policy import PolicyError, compute_pairs, flag_untrusted, forward_routes  # noqa: E402
import eden_winclient as client  # noqa: E402

MESH_NET = ipaddress.ip_network("100.64.0.0/10")


def env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"eden_winctl: {name} is not set (run through eden.py)")
    return value


def load_config():
    with open(env("EDEN_CONFIG"), encoding="utf-8") as f:
        return json.load(f)


def device_address(dev):
    """The device's Meshnet address, or None when it is missing or not an address inside 100.64.0.0/10."""
    try:
        ip = ipaddress.IPv4Address(dev.get("address"))
    except (ValueError, TypeError):
        return None
    return str(ip) if ip in MESH_NET else None


def resolve(config):
    """The plain device list the policy wants: name, enabled, ip (None when not usable), untrusted (fail closed)."""
    return [{"name": d["name"], "enabled": bool(d.get("enabled", True)), "ip": device_address(d),
             "untrusted": flag_untrusted(d)} for d in config.get("devices", [])]


def helper(cmd, **params):
    answer = client.call(cmd, **params)
    if not answer.get("ok"):
        sys.exit(f"eden_winctl: helper {cmd} refused: {answer.get('error')}")
    return answer


def write_forward(routes):
    """Hand the forwarder its routes: atomic file. The forwarder polls it, so no signal is needed (Windows has no
    SIGHUP). Always called BEFORE the rules are applied: when something opens, the forwarder listens first; when
    something closes, the forwarder lets go first."""
    path = os.path.join(env("EDEN_RUN"), "forward.json")
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".forward.json.")
        with os.fdopen(fd, "w") as f:
            json.dump({"routes": routes}, f)
        os.replace(tmp, path)
    except OSError as e:
        sys.exit(f"eden_winctl: cannot write the forwarder routes: {e}")


def allowed_ports():
    return set(helper("ports-list")["ports"])


def compute(config, allowed):
    return compute_pairs(config, resolve(config), allowed)


def fail_closed(error):
    """A rule the design forbids was asked for: close everything and stop, instead of applying a filtered set."""
    try:
        write_forward([])
        client.call("guard")
    except SystemExit:
        pass    # already reported; the exit below is non-zero anyway
    sys.exit(f"eden_winctl: refused, guard rules applied (everything blocked): {error}")


def cmd_guard(_=None):
    helper("guard")
    print("guard rules applied (everything from the Meshnet adapter is blocked)")


def cmd_final(_=None):
    config = load_config()
    try:
        ips, pairs = compute(config, allowed_ports())
    except PolicyError as e:
        fail_closed(e)
    if not pairs:
        write_forward([])
        helper("guard")
        print("no device is enabled: guard rules applied")
        return
    write_forward(forward_routes(config, pairs))
    helper("apply", pairs=sorted([port, ip] for port, ip in pairs))
    print(f"rules applied: {len(pairs)} pair(s) for {', '.join(sorted(ips))}")


COMMANDS = {"guard": cmd_guard, "deny-all": cmd_guard, "final": cmd_final, "reload": cmd_final}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit("usage: eden_winctl.py guard|final|reload|deny-all")
    COMMANDS[sys.argv[1]]()
