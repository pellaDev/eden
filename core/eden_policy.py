# Eden policy: WHICH (port, address) pairs may be open, and for whom. Pure computation: no operating system calls,
# no subprocess, no files, no network. It is shared by the Linux and the Windows editions and is the one place where
# the rules of the design live (untrusted devices never get the remote-login port, a service that is off opens
# nothing, a port outside the allowed list stays closed). Each edition feeds it the same input and turns the answer
# into its own firewall rules (Linux: nftables through the root helper; Windows: Windows Firewall).
#
# Input shapes (plain data, so both editions and the tests build them the same way):
#   config   the parsed eden.json
#   devices  [{"name", "enabled", "ip", "untrusted"}] one per configured device; "ip" is None when the device
#            could not be resolved (Linux: public key not in the peer list; Windows: no address configured)
#   allowed  set of ports the privileged helper accepts (a service on another port stays closed)
# Keep this file free of OS-specific imports: tests/test_core_pure.py fails if one appears.

import sys


class PolicyError(Exception):
    """The configuration would break an untrusted-device rule: nothing may be opened."""


def flag_untrusted(dev):
    """The device's untrusted flag in the config. Fail closed: anything but false (true, null, garbage) means
    untrusted; a missing flag is a trusted device created before the feature existed."""
    return dev.get("untrusted", False) is not False


def rule_pairs(config, ips, allowed, *, untrusted, warn=None):
    """(port, ip) pairs to open: remote access for every resolved+enabled TRUSTED device, plus
    each globally-enabled service for the devices granted it. Empty when no device
    is resolved+enabled (which yields the drop-all guard state). A service whose port
    is not in the helper's allowed ports is skipped with a warning (its port stays
    closed) instead of making the whole load fail; the remote port is never skipped:
    if it is not allowed the helper rejects the load, which is the right failure.
    `untrusted` (set of device names) is required on purpose, so no caller can forget it.
    An untrusted device never gets the remote port: not as remote access, and not through a grant
    on a service that sits on that port. The grant is refused (PolicyError) even while the service
    is off, because switching it on later would open the port."""
    warn = warn or (lambda text: print(text, file=sys.stderr))
    remote_port = config["remote_port"]
    for dev in config["devices"]:
        if dev["name"] not in untrusted:
            continue
        for svc in config.get("services", []):
            if svc["name"] in dev.get("services", []) and svc["port"] == remote_port:
                raise PolicyError(f"untrusted device {dev['name']} is granted service {svc['name']} on the "
                                  f"Eden remote-login port {remote_port}")
    pairs = {(remote_port, ip) for name, ip in ips.items() if name not in untrusted}
    for svc in config.get("services", []):
        if not svc.get("enabled"):
            continue   # off = no rule at all for this port, not "allowed but idle"
        if svc["port"] not in allowed:
            warn(f"eden_ctl: service {svc['name']} skipped: port {svc['port']} is not in the helper's allowed ports")
            continue
        for dev in config["devices"]:
            if svc["name"] in dev.get("services", []) and dev["name"] in ips:
                pairs.add((svc["port"], ips[dev["name"]]))
    return pairs


def compute_pairs(config, devices, allowed, *, warn=None):
    """(ips, pairs) for the current config and the resolved devices: ips = {device name: IP} of resolved, enabled
    devices (unresolved/disabled are skipped instead of failing, so one bad device doesn't block the others);
    pairs = what the firewall opens. Raises PolicyError if the result would give an untrusted device the remote
    port: checked twice, in rule_pairs from the config and here from the finished pairs, so a future mistake in
    either place is still caught."""
    ips = {d["name"]: d["ip"] for d in devices if d["enabled"] and d["ip"]}
    untrusted = {d["name"] for d in devices if d["untrusted"]}
    pairs = rule_pairs(config, ips, allowed, untrusted=untrusted, warn=warn)
    bad = {ips[n] for n in untrusted if n in ips}
    leaked = sorted(ip for port, ip in pairs if port == config["remote_port"] and ip in bad)
    if leaked:
        raise PolicyError(f"the remote-login port {config['remote_port']} would be open to untrusted address(es) "
                          f"{', '.join(leaked)}")
    return ips, pairs


def forward_routes(config, pairs):
    """Routes for the forwarder (eden_forward): services marked "forward" (they listen only on 127.0.0.1) that
    are on and have at least one open (port, ip) pair, with exactly the source IPs that pair list allows.
    Derived from the same pairs given to the firewall, so the firewall and the forwarder can never disagree."""
    routes = []
    for svc in config.get("services", []):
        if not (svc.get("forward") and svc.get("enabled")):
            continue
        ips = sorted({str(ip) for port, ip in pairs if port == svc["port"]})
        if ips:
            routes.append({"port": svc["port"], "allow": ips})
    return routes
