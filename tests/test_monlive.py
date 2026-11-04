# Run: python3 tests/test_monlive.py
from _backend import *  # noqa: F401,F403
import time
assert el.host_name()
assert el.set_host(el.HostBody(host_name="  workstation ")) == {"host_name": "workstation"} and el.get_host()["host_name"] == "workstation"
for bad in ("", "a/b", "x"*40, "-x"):
    assert code(el.set_host, el.HostBody(host_name=bad)) == 400, bad
st = el.get_monitor_live(); assert st["live"] is True and st["refresh_seconds"] == 2 and st["retention_days"] == 7 and st["record_when_closed"] is True, st
st = el.set_monitor_live(el.LiveBody(live=False)); assert st["live"] is False and not st["running"]
assert cfg()["monitor"]["live"] is False
el.monitor_history.add(time.time()-5, 10, 5); el.monitor_history.add(time.time()-3, 20, 5)
h = el.get_monitor_history("all"); assert h["range"] == "all" and len(h["points"]) == 2, h
assert code(el.get_monitor_history, "5y") == 400
el.iface_counters = lambda i: (1, 1)
st = el.set_monitor_live(el.LiveBody(live=True)); assert st["live"] and st["running"]
st = el.set_monitor_live(el.LiveBody(live=False)); assert not st["running"]

st = el.set_monitor_settings(el.MonitorSettingsBody(refresh_seconds=5, presence_seconds=30, retention_days=3, record_when_closed=False))
assert st["refresh_seconds"] == 5 and el.monitor_sampler.step == 5 and el.monitor_sampler.retention_s == 3*86400 and el.monitor_history.raw.step == 5
for kw in ({"refresh_seconds":0},{"refresh_seconds":61},{"presence_seconds":4},{"retention_days":0},{"retention_days":36}):
    b = dict(refresh_seconds=5, presence_seconds=30, retention_days=3, record_when_closed=False); b.update(kw)
    assert code(el.set_monitor_settings, el.MonitorSettingsBody(**b)) == 400, kw
assert cfg()["monitor"]["live"] is False and cfg()["monitor"]["retention_days"] == 3
# gate: record_when_closed off -> only with a UI seen
el._ui_seen = 0.0; assert not el.monitor_gate()
el.get_monitor_live(); assert el.monitor_gate()
# prune through the endpoint: old points go
el.monitor_history.add(time.time()-10*86400, 1, 1)
el.set_monitor_settings(el.MonitorSettingsBody(refresh_seconds=5, presence_seconds=30, retention_days=3, record_when_closed=True))
assert all(p[0] > time.time()-3*86400 for p in el.monitor_history.raw.points)
print("monlive ok")
