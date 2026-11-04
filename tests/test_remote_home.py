# Run: python3 tests/test_remote_home.py
from _backend import *  # noqa: F401,F403
el.monitor_devices_data = lambda: el.build_monitor_devices()
r = el.remote_home("100.64.0.7")
assert r["trusted"] and r["device"]["name"] == "phone" and [s["name"] for s in r["services"]] == ["jelly", "llm"], r
assert all(set(s) == {"name", "port", "note", "avatar"} for s in r["services"])
g = el.remote_home("100.64.0.20")   # external peer, configured untrusted: trusted False, only its grant
assert not g["trusted"] and [s["name"] for s in g["services"]] == ["llm"], g
n = el.remote_home("100.64.0.9")         # known only by Nord: no services, untrusted
assert not n["trusted"] and n["services"] == [] and n["device"]["known"] is False, n
assert el.remote_home("9.9.9.9") == {"host_name": r["host_name"], "device": None, "trusted": False, "services": []}
assert code(el.remote_home, "nope") == 400
c = cfg(); c["services"][0]["enabled"] = False; c["devices"][0]["enabled"] = True; json.dump(c, open(os.environ["EDEN_CONFIG"], "w"))
assert [s["name"] for s in el.remote_home("100.64.0.7")["services"]] == ["llm"]
c["devices"][0]["enabled"] = False; json.dump(c, open(os.environ["EDEN_CONFIG"], "w"))
assert el.remote_home("100.64.0.7")["services"] == []
c["devices"][0]["enabled"] = True; c["devices"][0]["services"].append("rp"); c["services"].append({"name": "rp", "port": 8443, "enabled": True}); c["devices"][1]["services"].append("rp"); json.dump(c, open(os.environ["EDEN_CONFIG"], "w"))
assert "rp" in [s["name"] for s in el.remote_home("100.64.0.7")["services"]]
assert "rp" not in [s["name"] for s in el.remote_home("100.64.0.20")["services"]]
el.live_peers = lambda: None; el._monitor_devices_cache = (0, None)
print("remote_home ok")
