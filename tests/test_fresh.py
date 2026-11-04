# A fresh install has no eden.json yet: the backend must start with nothing exposed and nothing known.
# Run: python3 tests/test_fresh.py
from _backend import *  # noqa: F401,F403

os.remove(os.environ["EDEN_CONFIG"])
c = el.read_config()
assert c["services"] == [] and c["devices"] == [] and c["remote_port"] == 8443, c
assert el.devices_state(c, [])["devices"] == [] and el.services_state(c)["services"] == []
print("fresh install ok")
