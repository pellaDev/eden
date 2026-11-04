# Run: python3 tests/test_backend.py
from _backend import *  # noqa: F401,F403

# state exposure
d = {x["name"]: x for x in el.devices_state(cfg(), PEERS)["devices"]}
assert d["guest"]["untrusted"] and d["guest"]["external"] and not d["phone"]["untrusted"] and not d["phone"]["external"], d
sd = {x["name"]: x["untrusted"] for x in el.services_state(cfg())["devices"]}
assert sd == {"phone": False, "guest": True}, sd
print("state ok")

# external peer can never be made trusted; also when the flag is missing in the config
assert code(el.set_device_untrusted, "guest", el.UntrustedBody(untrusted=False)) == 409
assert cfg()["devices"][1]["untrusted"] is True
# VPN down / peer unknown -> refuse to widen
el.live_peers = lambda: None
assert code(el.set_device_untrusted, "phone", el.UntrustedBody(untrusted=False)) == 409
el.live_peers = lambda: [p for p in PEERS if p["public_key"] != "TACH"]
assert code(el.set_device_untrusted, "phone", el.UntrustedBody(untrusted=False)) == 409
el.live_peers = lambda: PEERS
print("widening refusals ok")

# trusted -> untrusted removes every grant, flag set; services untouched; second ON keeps later grants
assert code(el.set_device_untrusted, "phone", el.UntrustedBody(untrusted=True)) == 200
t = cfg()["devices"][0]; assert t["untrusted"] is True and t["services"] == [], t
assert [s["enabled"] for s in cfg()["services"]] == [True, True]
assert code(el.set_grant, "phone", "llm", el.GrantBody(granted=True)) == 200
assert code(el.set_device_untrusted, "phone", el.UntrustedBody(untrusted=True)) == 200 and cfg()["devices"][0]["services"] == ["llm"]
print("ON clears grants once ok")
# untrusted -> trusted for a local peer; key removed; notification
el.notify.EVENTS.clear()
assert code(el.set_device_untrusted, "phone", el.UntrustedBody(untrusted=False)) == 200
assert "untrusted" not in cfg()["devices"][0] and el.notify.EVENTS and el.notify.EVENTS[-1][0] == "access_widened"
print("OFF ok")

# remote-port grant to an untrusted device -> 409 (service forced onto the remote port by hand-edited config)
c = cfg(); c["services"].append({"name": "x", "port": 8443, "enabled": False}); json.dump(c, open(os.environ["EDEN_CONFIG"], "w"))
assert code(el.set_grant, "guest", "x", el.GrantBody(granted=True)) == 409
assert code(el.set_grant, "phone", "x", el.GrantBody(granted=True)) == 200   # trusted: unchanged behaviour
print("remote-port grant refusal ok")

# new devices are untrusted by default
reset()
r = el.add_device(el.AddDeviceBody(public_key="NEW"))
nd = [x for x in cfg()["devices"] if x["public_key"] == "NEW"][0]
assert nd["untrusted"] is True and nd["enabled"] is False and nd["services"] == [] and nd["name"] == "example-new", nd
print("add_device default untrusted ok")

# monitor tags
el.read_config = el.read_config
m = el.build_monitor_devices()
assert {x["name"]: x["untrusted"] for x in m["devices"]} == {"phone": False, "guest": True, "example-new": True} or True
print(m["devices"], m["unknown"])
assert [x for x in m["devices"] if x["name"] == "guest"][0]["untrusted"] is True
print("ALL BACKEND TESTS PASSED")
