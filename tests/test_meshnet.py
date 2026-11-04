# Run: python3 tests/test_meshnet.py
from _backend import *  # noqa: F401,F403
E = el.EditDeviceBody
assert code(el.edit_device, "guest", E(meshnet="theirs")) == 200 and cfg()["devices"][1]["meshnet"] == "theirs"
d = {x["name"]: x for x in el.devices_state(cfg(), PEERS)["devices"]}
assert d["guest"]["meshnet"] == "theirs" and d["phone"]["meshnet"] is None
assert code(el.edit_device, "guest", E(meshnet="bad")) == 400
assert code(el.edit_device, "guest", E(name="guest")) == 200 and cfg()["devices"][1]["meshnet"] == "theirs"
assert code(el.edit_device, "guest", E(meshnet="")) == 200 and "meshnet" not in cfg()["devices"][1]
print("meshnet ok")
