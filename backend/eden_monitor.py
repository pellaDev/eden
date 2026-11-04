# Meshnet traffic history for the Home page, kept by a sampler that runs only while "Live traffic" is on.
# Standard library only, no import-time work: nothing starts until Sampler.start() is called.
#
# What it keeps, all bounded (the counts are caps; the retention setting prunes by age on top of them):
#   raw     one rate sample per refresh step (default 2 s), at most the last hour at 1 s
#   minute  one average per minute, up to 35 days
#   coarse  one average per 10 minutes, up to about 35 days
#   events  the last 2000 times a device went online or offline
# A query picks the finest tier that still reaches back to the start of the range, then averages neighbouring points
# so a chart never gets more than max_points. The history is written to one small JSON file (atomically, every few
# minutes and at shutdown) so a restart of Eden does not lose it; the gap while Eden was down shows as a break.
import json
import math
import os
import tempfile
import threading
import time
from collections import deque

RAW_STEP, RAW_KEEP = 2, 3600            # nominal step; the real one is set by History.set_step
MINUTE_STEP, MINUTE_KEEP = 60, 50400    # 35 days
COARSE_STEP, COARSE_KEEP = 600, 5040    # 35 days
EVENTS_KEEP = 2000
FILE_VERSION = 1
PRUNE_EVERY = 3600   # seconds between two prunings while running (the first one is at startup, by the caller)

# Ranges the UI offers, in seconds; None = everything since the scan was first left on.
RANGES = {"30m": 1800, "1h": 3600, "12h": 43200, "24h": 86400, "48h": 172800, "7d": 604800, "all": None}


class _Level:
    """One tier: the points kept, plus the bucket currently being averaged."""

    def __init__(self, step, keep):
        self.step, self.points = step, deque(maxlen=keep)
        self.bucket, self.rx, self.tx, self.n = None, 0.0, 0.0, 0

    def reset(self, bucket):
        self.bucket, self.rx, self.tx, self.n = bucket, 0.0, 0.0, 0


class History:
    def __init__(self):
        self._lock = threading.RLock()
        self.raw = _Level(RAW_STEP, RAW_KEEP)
        self.minute = _Level(MINUTE_STEP, MINUTE_KEEP)
        self.coarse = _Level(COARSE_STEP, COARSE_KEEP)
        self.events = deque(maxlen=EVENTS_KEEP)
        self.since = None

    # ---- writing ----
    def add(self, t, rx, tx):
        """One sample: bytes per second received and sent on the Meshnet interface at time t."""
        with self._lock:
            if self.since is None:
                self.since = t
            self.raw.points.append((t, rx, tx))
            self._feed(self.minute, self.coarse, t, rx, tx)

    def _feed(self, level, nxt, t, rx, tx):
        bucket = int(t // level.step)
        if level.bucket is not None and bucket != level.bucket and level.n:
            p = (level.bucket * level.step, level.rx / level.n, level.tx / level.n)
            level.points.append(p)
            if nxt is not None:
                self._feed(nxt, None, *p)
        if level.bucket != bucket:
            level.reset(bucket)
        level.rx += rx
        level.tx += tx
        level.n += 1

    def add_event(self, event):
        with self._lock:
            self.events.append(event)

    def set_step(self, step):
        """The refresh step of the raw tier (seconds between samples); used to tell a gap from normal spacing."""
        with self._lock:
            self.raw.step = step

    def prune(self, cutoff):
        """Drop everything older than `cutoff` (epoch seconds); returns how many entries went away."""
        with self._lock:
            n = 0
            for level in (self.raw, self.minute, self.coarse):
                keep = [p for p in level.points if p[0] >= cutoff]
                n += len(level.points) - len(keep)
                level.points.clear()
                level.points.extend(keep)
            ev = [e for e in self.events if e["t"] >= cutoff]
            n += len(self.events) - len(ev)
            self.events.clear()
            self.events.extend(ev)
            firsts = [l.points[0][0] for l in (self.raw, self.minute, self.coarse) if l.points]
            if firsts:
                self.since = min(firsts)
            elif n:
                self.since = None
            return n

    # ---- reading ----
    def info(self):
        with self._lock:
            return {"since": self.since, "samples": len(self.raw.points), "minutes": len(self.minute.points),
                    "coarse": len(self.coarse.points), "events": len(self.events)}

    def query(self, from_t, to_t, max_points=600):
        """Points [t, rx, tx] (None, None marks a gap) and the events inside [from_t, to_t]."""
        with self._lock:
            tiers = [self.raw, self.minute, self.coarse]
            anchor = max(from_t, self.since) if self.since is not None else from_t
            tier = next((l for l in tiers if l.points and l.points[0][0] <= anchor + l.step), None)
            if tier is None:   # nothing reaches back far enough: the coarsest tier that has anything
                tier = next((l for l in reversed(tiers) if l.points), None)
            pts = [p for p in tier.points if from_t <= p[0] <= to_t] if tier else []
            step = tier.step if tier else RAW_STEP
            events = [e for e in self.events if from_t <= e["t"] <= to_t]
        k = max(1, math.ceil(len(pts) / max_points))
        if k > 1:
            pts = [(sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g), sum(p[2] for p in g) / len(g))
                   for g in (pts[i:i + k] for i in range(0, len(pts), k))]
        step *= k
        deltas = sorted(b[0] - a[0] for a, b in zip(pts, pts[1:]))
        spacing = max(step, deltas[len(deltas) // 2] if deltas else 0)   # a refresh changed over time must not look like holes
        out = []
        for p in pts:
            if out and out[-1][1] is not None and p[0] - out[-1][0] > 3 * spacing:
                out.append([(out[-1][0] + p[0]) / 2, None, None])   # a hole: Eden or the VPN was down
            out.append([round(p[0], 1), round(p[1], 1), round(p[2], 1)])
        return {"step": step, "points": out, "events": events}

    # ---- file ----
    def save(self, path):
        with self._lock:
            data = {"v": FILE_VERSION, "since": self.since, "events": list(self.events),
                    "raw": [[round(a, 1), round(b, 1), round(c, 1)] for a, b, c in self.raw.points],
                    "minute": [[round(a, 1), round(b, 1), round(c, 1)] for a, b, c in self.minute.points],
                    "coarse": [[round(a, 1), round(b, 1), round(c, 1)] for a, b, c in self.coarse.points]}
        d = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".monitor_history.")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, separators=(",", ":"))
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load(self, path):
        """Read the file back; a missing, unreadable or foreign file leaves the history empty (never an error)."""
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("v") != FILE_VERSION:
                return False
            with self._lock:
                for level, key in ((self.raw, "raw"), (self.minute, "minute"), (self.coarse, "coarse")):
                    level.points.extend((float(a), float(b), float(c)) for a, b, c in data.get(key, []))
                self.events.extend(e for e in data.get("events", []) if isinstance(e, dict) and "t" in e)
                self.since = data.get("since")
            return True
        except (OSError, ValueError, TypeError, AttributeError):
            return False


class Sampler:
    """Two daemon threads while running: one reads the interface counters every `step` seconds and feeds the rates
    to the history; the other asks for the peers' presence every `presence_every` seconds and records the changes.
    `read_counters()` returns (rx_bytes, tx_bytes) or None (VPN down); `read_presence()` returns
    {key: {"name", "ip", "online", "untrusted"}} or None (cannot tell). Both may be slow or fail: errors are
    swallowed here, the sampler never takes the web server down."""

    MAX_GAP_FACTOR = 5   # a gap longer than this many steps between two reads gives no rate

    def __init__(self, history, read_counters, read_presence, *, path=None, step=2.0, presence_every=15.0,
                 save_every=300.0, retention_s=None, gate=None, clock=time.time):
        self.history, self.read_counters, self.read_presence = history, read_counters, read_presence
        self.path, self.step, self.presence_every, self.save_every, self.clock = path, step, presence_every, save_every, clock
        self.retention_s = retention_s     # prune entries older than this once an hour (None: never)
        self.gate = gate or (lambda: True)  # False: nothing is read or recorded this round (no UI open and not asked to record)
        self.history.set_step(step)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = []

    def configure(self, step=None, presence_every=None, retention_s=None):
        """Takes effect on the next round of the running threads."""
        if step is not None:
            self.step = step
            self.history.set_step(step)
        if presence_every is not None:
            self.presence_every = presence_every
        if retention_s is not None:
            self.retention_s = retention_s

    @property
    def running(self):
        return any(t.is_alive() for t in self._threads) and not self._stop.is_set()

    def start(self):
        with self._lock:
            if self.running:
                return
            self._stop = threading.Event()
            self._threads = [threading.Thread(target=self._rates, args=(self._stop,), name="eden-monitor-rates", daemon=True),
                             threading.Thread(target=self._presence, args=(self._stop,), name="eden-monitor-presence", daemon=True)]
            for t in self._threads:
                t.start()

    def stop(self):
        with self._lock:
            self._stop.set()
            for t in self._threads:
                t.join(timeout=2)   # the presence thread may sit in the Nord CLI: it is a daemon, and checks the flag after
            self._threads = []
        self.save()

    def save(self):
        if self.path:
            try:
                self.history.save(self.path)
            except OSError:
                pass   # a full disk must not stop the monitor

    def _rates(self, stop):
        prev, next_save = None, self.clock() + self.save_every
        next_prune = self.clock() + PRUNE_EVERY
        while not stop.is_set():
            now = self.clock()
            try:
                c = self.read_counters() if self.gate() else None
            except Exception:
                c = None
            if c is None:
                prev = None
            else:
                if prev is not None:
                    dt = now - prev[0]
                    if 0 < dt <= self.step * self.MAX_GAP_FACTOR:
                        rx, tx = (c[0] - prev[1]) / dt, (c[1] - prev[2]) / dt
                        if rx >= 0 and tx >= 0:   # a counter that went back (interface recreated) gives no sample
                            self.history.add(now, rx, tx)
                prev = (now, c[0], c[1])
            if self.retention_s and now >= next_prune:
                self.history.prune(now - self.retention_s)
                next_prune = now + PRUNE_EVERY
            if self.save_every and now >= next_save:
                self.save()
                next_save = now + self.save_every
            stop.wait(self.step)

    def _presence(self, stop):
        state = {}   # key -> (online, since)
        while not stop.is_set():
            try:
                open_ = self.gate()
                snap = self.read_presence() if open_ else None
            except Exception:
                open_, snap = True, None
            if not open_:
                state.clear()   # nothing was watched meanwhile: a change seen later is not an event of that moment
            if snap is not None and not stop.is_set():
                now = self.clock()
                for key, p in snap.items():
                    old = state.get(key)
                    if old is None:
                        state[key] = (bool(p["online"]), now)   # first sight: a state, not an event
                    elif old[0] != bool(p["online"]):
                        self.history.add_event({"t": round(now, 1), "kind": "connect" if p["online"] else "disconnect",
                                                "name": p.get("name"), "ip": p.get("ip"),
                                                "untrusted": bool(p.get("untrusted")), "after_s": round(now - old[1])})
                        state[key] = (bool(p["online"]), now)
            stop.wait(self.presence_every)
