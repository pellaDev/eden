# Tests of the Windows rule set (eden_winfw.py) with a model of how Windows Firewall decides: a matching Block always
# wins, otherwise a matching Allow lets the packet in, otherwise Nord's own broad Allow for its peers lets it in (the
# worst case: that rule is there on a real machine, see RELEASE_PLAN section 6, run 4). Run: python3 test_eden_winfw.py
import ast
import ipaddress
import os
import sys
import random

import eden_winfw as w

HERE = os.path.dirname(os.path.abspath(__file__))


def in_ranges(ip, ranges):
    n = int(ipaddress.IPv4Address(ip))
    for r in ranges:
        lo, _, hi = r.partition("-")
        if int(ipaddress.IPv4Address(lo)) <= n <= int(ipaddress.IPv4Address(hi or lo)):
            return True
    return False


def port_in(port, ranges):
    for r in ranges:
        lo, _, hi = r.partition("-")
        if int(lo) <= port <= int(hi or lo):
            return True
    return False


def matches(rule, proto, ip, port):
    if rule["protocol"] not in ("Any", proto):
        return False
    if rule["remote"] == [w.IPV6_ALL]:
        return False   # an IPv4 packet never matches the IPv6 rule
    if rule["remote"] and not in_ranges(ip, rule["remote"]):
        return False
    if rule["local_port"] and (proto != "TCP" or not port_in(port, rule["local_port"])):
        return False
    return True


def allowed(rules, proto, ip, port=None):
    hits = [r for r in rules if matches(r, proto, ip, port)]
    if any(r["action"] == "Block" for r in hits):
        return False
    return True   # an Allow or Nord's broad Allow: either way the packet gets in


def test_ranges():
    assert w.port_ranges([]) == ["1-65535"]
    assert w.port_ranges([1, 65535]) == ["2-65534"]
    assert w.port_ranges([80, 81, 443]) == ["1-79", "82-442", "444-65535"]
    assert w.address_ranges([]) == ["100.64.0.0-100.127.255.255"]
    assert w.address_ranges(["100.64.0.0", "100.127.255.255"]) == ["100.64.0.1-100.127.255.254"]
    assert w.address_ranges(["100.64.0.10"]) == ["100.64.0.0-100.64.0.9", "100.64.0.11-100.127.255.255"]
    try:
        w.address_ranges(["192.0.2.1"])
        raise SystemExit("an address outside the Meshnet range must be refused")
    except ValueError:
        pass


def test_guard_blocks_everything():
    r = w.guard_rules()
    for proto, port in (("TCP", 80), ("UDP", 53), ("ICMPv4", None)):
        assert not allowed(r, proto, "100.64.0.5", port)


def test_only_the_pairs_are_open():
    pairs = {(8096, "100.64.0.10"), (8443, "100.64.0.10"), (8788, "100.64.0.20"), (8096, "100.64.0.20")}
    r = w.up_rules(pairs)
    for ip in ("100.64.0.10", "100.64.0.20", "100.64.0.30", "100.127.255.255"):
        for port in (22, 80, 8096, 8443, 8788, 65535):
            want = (port, ip) in pairs
            assert allowed(r, "TCP", ip, port) == want, (ip, port)
        assert not allowed(r, "UDP", ip, 8096) and not allowed(r, "ICMPv4", ip)


def test_no_pairs_blocks_every_address():
    r = w.up_rules(set())
    assert not allowed(r, "TCP", "100.64.0.10", 8096) and not allowed(r, "ICMPv4", "100.100.1.1")


def test_random_sets():
    rng = random.Random(7)
    for _ in range(200):
        ips = [f"100.{rng.randint(64, 127)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}" for _ in range(rng.randint(1, 5))]
        pairs = {(rng.choice((22, 80, 8096, 8443, 18080, 65535)), rng.choice(ips)) for _ in range(rng.randint(0, 8))}
        r = w.up_rules(pairs)
        for ip in ips + ["100.100.100.100"]:
            for port in (22, 80, 8096, 8443, 18080, 65535, 1, 9999):
                assert allowed(r, "TCP", ip, port) == ((port, ip) in pairs), (pairs, ip, port)
            assert not allowed(r, "UDP", ip, 80) and not allowed(r, "ICMPv4", ip)


def test_blocks_come_before_their_allow():
    r = w.up_rules({(8096, "100.64.0.10"), (22, "100.64.0.20")})
    for i, rule in enumerate(r):
        if rule["action"] == "Allow":
            assert all(x["action"] == "Block" for x in r[:i] if x["remote"] and set(x["remote"]) & set(rule["remote"]))
    assert r[0]["name"] == "rest" and r[1]["name"] == "ipv6" and r[1]["remote"] == [w.IPV6_ALL]
    assert not any(x["name"] == "ipv6" for x in w.up_rules(set(), ipv6=False))


def test_same_ports_share_rules():
    r = w.up_rules({(8096, "100.64.0.10"), (8096, "100.64.0.11")})
    assert len([x for x in r if x["action"] == "Allow"]) == 1


def test_windows_edition_stays_apart_from_linux():
    """Nothing here imports the Linux edition (eden_ctl, eden_helper, nft)."""
    for fn in os.listdir(HERE):
        if fn.endswith(".py"):
            tree = ast.parse(open(os.path.join(HERE, fn)).read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                    assert not any(n.startswith(("eden_ctl", "eden_helper", "eden_local")) for n in names), (fn, names)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print("ok", name)
        except Exception as e:
            failed.append(name)
            print(f"FAIL {name}: {e!r}")
    if failed:
        # Stopping at the first failure hid every test after it and left the exit code at 0, so a runner could not
        # tell a pass from a broken suite.
        sys.exit(f"{len(failed)} of {len(tests)} failed: {', '.join(failed)}")
    print("ALL WINDOWS FIREWALL TESTS PASSED")
