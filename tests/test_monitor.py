# Tests of the traffic history. Run: python3 tests/test_monitor.py
import tempfile

import _support  # noqa: F401  (import paths)
import eden_monitor as m

# history tiers
h = m.History()
t0 = 1_000_000.0
for i in range(5000):                       # 10000 s of 2 s samples
    h.add(t0 + 2*i, 100.0, 50.0)
assert len(h.raw.points) == 3600
assert len(h.minute.points) >= 160, len(h.minute.points)
q = h.query(t0 + 9000, t0 + 10000)
assert q["step"] == 2 and 400 <= len(q["points"]) <= 600, (q["step"], len(q["points"]))
q = h.query(t0, t0 + 10000)                  # raw only reaches the last hour -> minute tier
assert q["step"] >= 60 and all(p[1] == 100.0 for p in q["points"] if p[1] is not None), q["step"]
q = h.query(t0, t0 + 10000, 20)
assert len(q["points"]) <= 20 + 2
# gap detection
h2 = m.History()
for i in range(10): h2.add(t0 + 2*i, 1, 1)
for i in range(10): h2.add(t0 + 1000 + 2*i, 1, 1)
q = h2.query(t0, t0 + 2000)
assert any(p[1] is None for p in q["points"])
# save / load
d = tempfile.mkdtemp(); f = d + "/h.json"
h.add_event({"t": t0 + 5, "kind": "connect", "name": "x"})
h.save(f)
h3 = m.History(); assert h3.load(f) and len(h3.raw.points) == 3600 and len(h3.events) == 1 and h3.since == h.since
assert not m.History().load(d + "/nope.json")
open(f, "w").write("garbage"); assert not m.History().load(f)

# prune + set_step + mixed spacing
hp = m.History()
for i in range(100): hp.add(t0 + 60*i, 1, 1)
hp.add_event({"t": t0 + 10, "kind": "connect", "name": "x"}); hp.add_event({"t": t0 + 5000, "kind": "connect", "name": "y"})
n = hp.prune(t0 + 3000)
assert n > 0 and hp.raw.points[0][0] >= t0 + 3000 and [e["name"] for e in hp.events] == ["y"] and hp.since >= t0 + 3000 - 600, hp.since
hp.prune(t0 + 10**7); assert hp.since is None and not hp.raw.points
hs = m.History(); hs.set_step(30)
for i in range(20): hs.add(t0 + 30*i, 1, 1)
assert not any(p[1] is None for p in hs.query(t0, t0 + 700)["points"])
print("monitor history ok")
