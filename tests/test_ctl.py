# Tests of eden_ctl: peer-list parsing, the open (port, address) pairs, fail-closed behaviour, the Meshnet permission sync.
# Run: python3 tests/test_ctl.py
import contextlib
import io
import json

from _support import load

c = load("ctl", "bin", "eden_ctl", "eden_ctl.py")

REAL = """This device:
Nickname: workstation
Hostname: example-host.example
IP: 100.64.0.1
Public Key: HYP
OS: linux

Local Peers:
Nickname: phone
Hostname: example-phone.example
Status: disconnected
IP: 100.64.0.7
Public Key: TACH
OS: android
Allow Incoming Traffic: enabled
Allow Routing: disabled
Allow Local Network Access: disabled
Allow Sending Files: disabled
Allows Incoming Traffic: enabled

Hostname: example-tablet.example
Nickname: -
Status: disconnected
IP: 100.64.0.8
Public Key: EVER
OS: android
Allow Incoming Traffic: enabled
Allow Routing: disabled
Allow Local Network Access: disabled
Allow Sending Files: disabled


External Peers:
Hostname: friend-pc.example
Nickname: -
Status: disconnected
IP: 100.64.0.20
Public Key: GUEST
OS: windows
Allow Incoming Traffic: disabled
Allow Routing: disabled
Allow Local Network Access: disabled
Allow Sending Files: disabled
Allows Incoming Traffic: enabled
"""
this, peers = c.parse_peer_list(REAL)
assert this["Hostname"] == "example-host.example"
assert [p["Public Key"] for p in peers] == ["TACH", "EVER", "GUEST"], peers
assert [bool(p.get(c.EXTERNAL)) for p in peers] == [False, False, True]
assert c.parse_peer_list(REAL.split("External Peers:")[0] + "External Peers:\n[no peers]\n")[1][-1]["Public Key"] == "EVER"
print("parser ok")

cfg = {"remote_port": 8443,
       "services": [{"name": "jelly", "port": 8096, "enabled": True},
                    {"name": "llm", "port": 8788, "enabled": True, "forward": True},
                    {"name": "bad", "port": 8443, "enabled": False}],
       "devices": [{"name": "phone", "public_key": "TACH", "enabled": True, "services": ["jelly"]},
                   {"name": "guest", "public_key": "GUEST", "enabled": True, "untrusted": True, "services": ["llm"]}]}
c.allowed_ports = lambda: {8443, 8096, 8788}
ips, pairs = c.compute_rules(cfg, peers)
assert pairs == {(8443, "100.64.0.7"), (8096, "100.64.0.7"), (8788, "100.64.0.20")}, pairs
print("pairs ok:", sorted(pairs))

# external peer with NO flag in config is still untrusted
cfg2 = json.loads(json.dumps(cfg)); del cfg2["devices"][1]["untrusted"]
assert (8443, "100.64.0.20") not in c.compute_rules(cfg2, peers)[1]
# garbage flag fails closed
cfg3 = json.loads(json.dumps(cfg)); cfg3["devices"][0]["untrusted"] = None
assert (8443, "100.64.0.7") not in c.compute_rules(cfg3, peers)[1]
print("fail-closed flags ok")

# grant of a service on the remote port to an untrusted device -> PolicyError, even with the service off
cfg4 = json.loads(json.dumps(cfg)); cfg4["devices"][1]["services"].append("bad")
try: c.compute_rules(cfg4, peers); raise SystemExit("NO ERROR")
except c.PolicyError as e: print("policy error ok:", e)
# same grant to a trusted device is not touched
cfg5 = json.loads(json.dumps(cfg)); cfg5["devices"][0]["services"].append("bad")
c.compute_rules(cfg5, peers)
# independent check on the finished pairs
import eden_policy
orig = eden_policy.rule_pairs
eden_policy.rule_pairs = lambda *a, **k: orig(*a, **k) | {(8443, "100.64.0.20")}
try: c.compute_rules(cfg, peers); raise SystemExit("NO ERROR 2")
except c.PolicyError as e: print("second check ok:", e)
eden_policy.rule_pairs = orig

# fail_closed loads guard table and exits non-zero
calls = []
c.write_forward = lambda r: calls.append(("fwd", r)); c.helper = lambda *a: calls.append(a)
try: c.fail_closed("x"); raise SystemExit("NO EXIT")
except SystemExit as e: assert str(e.code).startswith("eden_ctl: refused"), e.code
assert calls == [("fwd", []), ("nft-load",)], calls
print("fail_closed ok")

# sync_incoming: commands issued + read-back
issued = []
state = {}
def fake_nord(*a):
    issued.append(a[2:]); return 0, ""
c.nordvpn = fake_nord
c.live_peers = lambda: peers   # all four "Allow" lines disabled for the guest
f = c.sync_incoming(cfg, peers)
assert f == 0, f
cmds = [" ".join(x) for x in issued]
assert "routing deny friend-pc.example" in cmds and "local deny friend-pc.example" in cmds and "fileshare deny friend-pc.example" in cmds, cmds
assert not any(x.startswith("routing") and "himalayas" in x for x in cmds)   # trusted peers: untouched
assert "incoming allow friend-pc.example" in cmds and "incoming allow example-phone.example" in cmds and "incoming deny example-tablet.example" in cmds
print("sync ok:", len(cmds), "commands")
# read-back catches a leaked permission
import copy
leak = copy.deepcopy(peers); leak[2]["Allow Routing"] = "enabled"
c.live_peers = lambda: leak
with contextlib.redirect_stderr(io.StringIO()) as err: f = c.sync_incoming(cfg, peers)
assert f == 1 and "still has 'Routing'" in err.getvalue(), (f, err.getvalue())
# missing line = failure (fail closed)
miss = copy.deepcopy(peers); del miss[2]["Allow Sending Files"]
c.live_peers = lambda: miss
with contextlib.redirect_stderr(io.StringIO()): assert c.sync_incoming(cfg, peers) == 1
# deny command failing counts
c.live_peers = lambda: peers
c.nordvpn = lambda *a: (1, "boom") if a[2] == "routing" else (0, "")
with contextlib.redirect_stderr(io.StringIO()): assert c.sync_incoming(cfg, peers) == 1
print("read-back ok")

# incoming allow: unresolved untrusted device is skipped, unresolved trusted exits
c.nordvpn = lambda *a: (0, "")
c.load_config = lambda: cfg
c.live_peers = lambda: [p for p in peers if p["Public Key"] != "GUEST"]
with contextlib.redirect_stderr(io.StringIO()): c.cmd_incoming_allow(None)
cfg["devices"][0]["public_key"] = "GONE"
try:
    with contextlib.redirect_stderr(io.StringIO()): c.cmd_incoming_allow(None); raise SystemExit("NO EXIT")
except SystemExit as e: assert "not found" in str(e.code)
print("incoming allow ok")
print("ALL TESTS PASSED")

# nickname "-" is reported as empty
import io as _io, contextlib as _c, json as _j
c.live_peers = lambda: peers if False else c.parse_peer_list(REAL.replace("Nickname: phone", "Nickname: -"))[1]
with _c.redirect_stdout(_io.StringIO()) as _o: c.cmd_live_peers(None)
out = _j.loads(_o.getvalue()); assert out[0]["nickname"] == "" and out[2]["external"] is True and out[0]["external"] is False, out
print("live-peers nickname ok")
