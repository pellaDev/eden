# Fixture of the backend tests: the real eden_local with the Meshnet and the launcher replaced by fakes, a sample
# configuration (two services, a trusted phone and an untrusted guest) and a sample peer list.
import json
import os
import sys

from _support import load

sys.argv = ["x"]
el = load("eden_local", "backend", "eden_local.py")
# No e-mail is ever sent from a test: events are recorded instead.
el.notify.EVENTS = []
el.notify.event = lambda *a, **k: el.notify.EVENTS.append(a)
from fastapi import HTTPException  # noqa: E402

CFG = {"remote_port": 8443,
       "services": [{"name": "jelly", "port": 8096, "enabled": True}, {"name": "llm", "port": 8788, "enabled": True, "forward": True}],
       "devices": [{"name": "phone", "public_key": "TACH", "enabled": True, "services": ["jelly", "llm"]},
                   {"name": "guest", "public_key": "GUEST", "enabled": True, "untrusted": True, "services": ["llm"]}]}
def reset(): json.dump(CFG, open(os.environ["EDEN_CONFIG"], "w"))
reset()
PEERS = [{"public_key": "TACH", "nickname": "phone", "hostname": "h1.example", "ip": "100.64.0.7", "status": "connected", "external": False},
         {"public_key": "GUEST", "nickname": "", "hostname": "friend-pc.example", "ip": "100.64.0.20", "status": "connected", "external": True},
         {"public_key": "NEW", "nickname": "", "hostname": "example-new.example", "ip": "100.64.0.9", "status": "disconnected", "external": False}]
el.live_peers = lambda: PEERS
el.vpn_is_up = lambda: True
el.run_start = lambda *a, **k: {"ok": True, "stdout": "RELOAD: applied", "stderr": ""}
el.allowed_ports = lambda: {8443, 8096, 8788}
cfg = lambda: json.load(open(os.environ["EDEN_CONFIG"]))
def code(fn, *a):
    try: fn(*a); return 200
    except HTTPException as e: return e.status_code

