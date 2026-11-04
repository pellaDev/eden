# Run: python3 tests/test_remote_services.py
from _backend import *  # noqa: F401,F403
for p in PEERS: p["allows_in"] = p["public_key"] == "GUEST"; p["allow_in"] = False
B = el.RemoteServiceBody
s = el.get_remote_services()
assert s["services"] == [] and len(s["peers"]) == 3 and [p["offered"] for p in s["peers"]] == [False, True, False], s
r = el.add_remote_service(B(name="webapp", public_key="GUEST", port=8080, note="friend's dashboard"))
x = r["services"][0]
assert x["device"] == "guest" and x["address"] == "100.64.0.20:8080" and x["online"] and x["offered"], x
assert cfg()["remote_services"][0]["device_name"] == "guest"
assert code(el.add_remote_service, B(name="webapp", public_key="GUEST", port=1)) == 409
assert code(el.add_remote_service, B(name="Bad Name", public_key="GUEST", port=1)) == 400
assert code(el.add_remote_service, B(name="a", public_key="GUEST", port=0)) == 400
assert code(el.add_remote_service, B(name="a", port=80)) == 400
assert code(el.add_remote_service, B(name="a", public_key="GUEST", port=80, note="x" * 200)) == 400
el.add_remote_service(B(name="other", public_key="TACH", port=22))
assert code(el.edit_remote_service, "other", B(name="webapp")) == 409
r = el.edit_remote_service("webapp", B(port=3080)); assert r["services"][0]["address"].endswith(":3080") and r["services"][0]["note"]
r = el.edit_remote_service("webapp", B(name="webapp2")); assert r["services"][0]["name"] == "webapp2"
assert code(el.edit_remote_service, "nope", B(port=1)) == 404
el.live_peers = lambda: None          # VPN down: stored hint still names the device, no address
r = el.get_remote_services(); y = r["services"][0]
assert not r["peers_ok"] and y["device"] == "guest" and y["address"] is None and not y["found"], y
el.live_peers = lambda: PEERS
r = el.delete_remote_service("webapp2"); assert [x["name"] for x in r["services"]] == ["other"]
assert code(el.delete_remote_service, "webapp2") == 404
assert cfg()["devices"] and "services" in cfg()
print("remote services ok")
