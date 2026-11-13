# Tests of the Windows policy glue with a fake helper. Run: python3 test_eden_winctl.py
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

import eden_winctl as c


class FakeClient:
    def __init__(self, ports=(8443, 8096, 8788)):
        self.calls, self.ports, self.refuse = [], list(ports), None

    def call(self, cmd, **params):
        self.calls.append((cmd, params))
        if self.refuse == cmd:
            return {"ok": False, "error": "no"}
        return {"ok": True, "ports": self.ports}


def setup(config):
    d = tempfile.mkdtemp()
    os.environ["EDEN_CONFIG"] = os.path.join(d, "eden.json")
    os.environ["EDEN_RUN"] = d
    json.dump(config, open(os.environ["EDEN_CONFIG"], "w"))
    fake = FakeClient()
    c.client = fake
    return fake, d


CFG = {"remote_port": 8443,
       "services": [{"name": "media", "port": 8096, "enabled": True}, {"name": "llm", "port": 8788, "enabled": True, "forward": True}],
       "devices": [{"name": "laptop", "address": "100.64.0.10", "enabled": True, "services": ["media", "llm"]},
                   {"name": "guest", "address": "100.64.0.20", "enabled": True, "untrusted": True, "services": ["llm"]},
                   {"name": "bad", "address": "192.0.2.1", "enabled": True, "services": ["media"]},
                   {"name": "off", "address": "100.64.0.30", "enabled": False, "services": ["media"]}]}


def run(fn):
    out = io.StringIO()
    with redirect_stdout(out):
        fn()
    return out.getvalue()


def exits(fn):
    try:
        fn()
    except SystemExit as e:
        return str(e)
    return None


def test_final_applies_the_pairs():
    fake, d = setup(CFG)
    run(c.cmd_final)
    cmd, params = fake.calls[-1]
    assert cmd == "apply"
    assert params["pairs"] == sorted([[8096, "100.64.0.10"], [8443, "100.64.0.10"], [8788, "100.64.0.10"], [8788, "100.64.0.20"]])
    # the forwarder file was written first, with exactly the allowed sources
    routes = json.load(open(os.path.join(d, "forward.json")))["routes"]
    assert routes == [{"port": 8788, "allow": ["100.64.0.10", "100.64.0.20"]}]


def test_unusable_and_disabled_devices_open_nothing():
    fake, _ = setup(CFG)
    run(c.cmd_final)
    sent = json.dumps(fake.calls[-1][1])
    assert "192.0.2.1" not in sent and "100.64.0.30" not in sent


def test_garbage_untrusted_flag_counts_as_untrusted():
    cfg = json.loads(json.dumps(CFG))
    cfg["devices"][0]["untrusted"] = None
    fake, _ = setup(cfg)
    run(c.cmd_final)
    assert [8443, "100.64.0.10"] not in fake.calls[-1][1]["pairs"]


def test_no_enabled_device_applies_the_guard():
    cfg = {"remote_port": 8443, "services": [], "devices": []}
    fake, d = setup(cfg)
    out = run(c.cmd_final)
    assert fake.calls[-1][0] == "guard" and "guard rules applied" in out
    assert json.load(open(os.path.join(d, "forward.json"))) == {"routes": []}


def test_policy_violation_fails_closed():
    cfg = json.loads(json.dumps(CFG))
    cfg["services"].append({"name": "rp", "port": 8443, "enabled": False})
    cfg["devices"][1]["services"].append("rp")           # an untrusted device on the remote-login port
    fake, d = setup(cfg)
    msg = exits(c.cmd_final)
    assert msg and "refused" in msg and "guard rules applied" in msg
    assert fake.calls[-1][0] == "guard" and not any(x[0] == "apply" for x in fake.calls)
    assert json.load(open(os.path.join(d, "forward.json"))) == {"routes": []}


def test_helper_refusal_stops():
    fake, _ = setup(CFG)
    fake.refuse = "apply"
    assert "refused" in exits(c.cmd_final)


def test_guard_command():
    fake, _ = setup(CFG)
    run(c.cmd_guard)
    assert fake.calls[-1][0] == "guard"


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
    print("ALL WINDOWS CTL TESTS PASSED")
