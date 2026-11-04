# Run: python3 tests/test_sampler.py
import time

import _support  # noqa: F401  (import paths)
import eden_monitor as m
class Clk:
    t = 5000.0
    def __call__(s): s.t += 2; return s.t      # every call moves 2 s
clk = Clk(); cnt = [0, 0]
def counters():
    cnt[0] += 2000; cnt[1] += 1000; return tuple(cnt)
pres = {"a": {"name": "a", "ip": "1", "online": True, "untrusted": False}}
hs = m.History()
s = m.Sampler(hs, counters, lambda: dict(pres), step=0.02, presence_every=0.02, save_every=0)
s.start(); time.sleep(0.3)
pres["a"]["online"] = False
time.sleep(0.3)
pres["a"]["online"] = True
time.sleep(0.3)
s.stop()
assert not s.running
ev = list(hs.events)
assert [e["kind"] for e in ev][:2] == ["disconnect", "connect"], ev
assert len(hs.raw.points) > 5 and hs.raw.points[-1][1] > 0, hs.raw.points[-1]
s.start(); assert s.running; s.stop()
print("sampler ok", len(hs.raw.points), ev[0])
