# Tests of the shared policy (eden_policy.py). Plain asserts: run with `python3 test_eden_policy.py` or pytest.
# The fixtures are invented (example addresses and names): no real device appears here.
import ast
import os

import eden_policy as p

HERE = os.path.dirname(os.path.abspath(__file__))
# Modules the policy may import: nothing that talks to the operating system.
PURE_IMPORTS = {"sys"}


def config():
    return {"remote_port": 8443,
            "services": [{"name": "media", "port": 8096, "enabled": True},
                         {"name": "llm", "port": 8788, "enabled": True, "forward": True},
                         {"name": "off", "port": 9000, "enabled": False}],
            "devices": [{"name": "laptop", "services": ["media", "llm", "off"]},
                        {"name": "guest", "untrusted": True, "services": ["llm"]}]}


def devices(**over):
    base = [{"name": "laptop", "enabled": True, "ip": "100.64.0.10", "untrusted": False},
            {"name": "guest", "enabled": True, "ip": "100.64.0.20", "untrusted": True}]
    for d in base:
        d.update(over.get(d["name"], {}))
    return base


ALLOWED = {8443, 8096, 8788, 9000}


def raises(fn, error=p.PolicyError):
    try:
        fn()
    except error:
        return True
    return False


def test_core_is_pure():
    """The policy imports nothing OS-specific: both editions rely on it staying that way."""
    tree = ast.parse(open(os.path.join(HERE, "eden_policy.py")).read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= PURE_IMPORTS, f"eden_policy imports {sorted(names - PURE_IMPORTS)}"


def test_pairs():
    ips, pairs = p.compute_pairs(config(), devices(), ALLOWED)
    assert ips == {"laptop": "100.64.0.10", "guest": "100.64.0.20"}
    # trusted device: remote port + its services; untrusted: only the granted service, never the remote port
    assert pairs == {(8443, "100.64.0.10"), (8096, "100.64.0.10"), (8788, "100.64.0.10"), (8788, "100.64.0.20")}


def test_off_service_and_disallowed_port_open_nothing():
    warnings = []
    _, pairs = p.compute_pairs(config(), devices(), {8443, 8096}, warn=warnings.append)
    assert (9000, "100.64.0.10") not in pairs and (8788, "100.64.0.10") not in pairs
    assert len(warnings) == 1 and "8788" in warnings[0]   # "off" is silent, the disallowed port is reported


def test_unresolved_or_disabled_device_is_skipped():
    _, pairs = p.compute_pairs(config(), devices(laptop={"ip": None}, guest={"enabled": False}), ALLOWED)
    assert pairs == set()


def test_untrusted_device_never_gets_the_remote_port():
    cfg = config()
    cfg["services"].append({"name": "rp", "port": 8443, "enabled": False})
    cfg["devices"][1]["services"].append("rp")          # refused even while the service is off
    assert raises(lambda: p.compute_pairs(cfg, devices(), ALLOWED))


def test_second_check_on_the_finished_pairs():
    orig = p.rule_pairs
    p.rule_pairs = lambda *a, **k: orig(*a, **k) | {(8443, "100.64.0.20")}
    try:
        assert raises(lambda: p.compute_pairs(config(), devices(), ALLOWED))
    finally:
        p.rule_pairs = orig


def test_flag_untrusted_fails_closed():
    assert not p.flag_untrusted({}) and not p.flag_untrusted({"untrusted": False})
    assert p.flag_untrusted({"untrusted": True}) and p.flag_untrusted({"untrusted": None}) and p.flag_untrusted({"untrusted": "no"})


def test_forward_routes_follow_the_pairs():
    _, pairs = p.compute_pairs(config(), devices(), ALLOWED)
    assert p.forward_routes(config(), pairs) == [{"port": 8788, "allow": ["100.64.0.10", "100.64.0.20"]}]
    assert p.forward_routes(config(), set()) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL POLICY TESTS PASSED")
