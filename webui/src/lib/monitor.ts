// Live data for the Home page. useMonitor() (tiles, open connections, device presence) lives and dies with the page: its
// samples are requested only while the page is mounted, the tab is visible and Live traffic is on (useVisiblePoll).
// The chart is different: useHistory() asks the server for the stored history (kept by the sampler that runs while Live
// traffic is on), for the range chosen in the chart.
import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "./api";
import { currentLocale, type TextKey } from "./i18n";
import { useVisiblePoll } from "./usePoll";

export const SAMPLE_MS = 2000; // default of the fast endpoint (interface counters, open connections); Settings changes it
const SAMPLE_DOWN_MS = 5000; // while the VPN is down there is nothing to watch: look less often
const DEVICES_MS = 15000; // default of the slow endpoint (Nord peer list): names and presence of the devices
const HISTORY_POINTS = 90; // samples kept for the tiles
const MIN_GAP_S = 10; // a longer gap between two samples (tab was hidden), or five refresh steps: no rate for that one

export type Conn = {
  id: string;
  remote_ip: string;
  remote_port: number;
  local_port: number;
  direction: "in" | "out";
  kind: "service" | "remote" | "other";
  service: string | null;
  bytes_sent: number; // the Eden computer to the device, since the connection began
  bytes_received: number; // device to the Eden computer
  rtt_ms: number | null;
  idle_ms: number | null;
};
export type Snapshot = {
  vpn_up: boolean;
  t: number; // server clock, seconds: rates use this, not the browser's clock
  mesh_ip?: string;
  rx_bytes?: number;
  tx_bytes?: number;
  connections?: Conn[] | null; // null: ss could not be read, counters are still valid
  truncated?: boolean;
};
export type Peer = { name: string; ip: string | null; online: boolean; enabled?: boolean; status: string | null; untrusted?: boolean };
export type DevicesInfo = { peers_ok: boolean | null; devices: Peer[]; unknown: Peer[] };
export type Point = { t: number; label: string; rx: number; tx: number }; // bytes per second on the Meshnet interface
export type Row = Conn & { rate_sent: number; rate_received: number }; // bytes per second, this connection

type Prev = { t: number; rx: number; tx: number; conns: Map<string, { sent: number; received: number }> };

const nf = (digits: number) => new Intl.NumberFormat(currentLocale(), { maximumFractionDigits: digits });
export function formatBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Math.max(0, n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${nf(i === 0 ? 0 : v < 10 ? 1 : 0).format(v)} ${units[i]}`;
}
export const formatRate = (n: number) => `${formatBytes(n)}/s`;

export function useMonitor(enabled = true, sampleMs = SAMPLE_MS, devicesMs = DEVICES_MS) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [history, setHistory] = useState<Point[]>([]);
  const [devices, setDevices] = useState<DevicesInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prev = useRef<Prev | null>(null);
  const sampling = useRef(false); // a slow answer never piles up a second request
  const loadingDevices = useRef(false);
  // The peer list (a Python process plus the Nord CLI) is asked for only after a sample has said the VPN is up, and
  // never while it is down: so a closed VPN costs one cheap sample, not a process.
  const vpnUp = useRef(false);

  const loadDevices = useCallback(async () => {
    if (loadingDevices.current || !vpnUp.current) return;
    loadingDevices.current = true;
    try {
      setDevices(await apiGet<DevicesInfo>("/monitor/devices"));
    } catch {
      /* the table falls back to addresses; the main error line already reports a dead backend */
    } finally {
      loadingDevices.current = false;
    }
  }, []);

  const sample = useCallback(async () => {
    if (sampling.current) return;
    sampling.current = true;
    try {
      const s = await apiGet<Snapshot>("/monitor");
      setSnap(s);
      setError(null);
      const wasUp = vpnUp.current;
      vpnUp.current = s.vpn_up;
      if (s.vpn_up && !wasUp) void loadDevices(); // first sample, or the VPN just came back: the names should not wait for the 15 s timer
      if (!s.vpn_up || s.rx_bytes === undefined || s.tx_bytes === undefined) {
        prev.current = null;
        setRows([]);
        return;
      }
      const before = prev.current;
      const dt = before ? s.t - before.t : 0;
      const usable = before !== null && dt > 0 && dt <= Math.max(MIN_GAP_S, (5 * sampleMs) / 1000);
      const rate = (now: number, then: number) => (usable ? Math.max(0, (now - then) / dt) : 0);
      const conns = s.connections ?? [];
      setRows(
        conns.map((c) => {
          const old = usable ? before!.conns.get(c.id) : undefined;
          return {
            ...c,
            rate_sent: old ? rate(c.bytes_sent, old.sent) : 0,
            rate_received: old ? rate(c.bytes_received, old.received) : 0,
          };
        }),
      );
      if (usable) {
        const point: Point = {
          t: s.t,
          label: new Date(s.t * 1000).toLocaleTimeString(currentLocale()),
          rx: rate(s.rx_bytes, before!.rx),
          tx: rate(s.tx_bytes, before!.tx),
        };
        setHistory((h) => [...h, point].slice(-HISTORY_POINTS));
      }
      prev.current = {
        t: s.t,
        rx: s.rx_bytes,
        tx: s.tx_bytes,
        conns: new Map(conns.map((c) => [c.id, { sent: c.bytes_sent, received: c.bytes_received }])),
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      sampling.current = false;
    }
  }, [loadDevices, sampleMs]);

  useVisiblePoll(sample, snap && !snap.vpn_up ? Math.max(SAMPLE_DOWN_MS, sampleMs) : sampleMs, enabled);
  useVisiblePoll(loadDevices, devicesMs, enabled);
  return { snap, rows, history, devices, error };
}


// ---- stored history (the chart) ----
export type RangeId = "30m" | "1h" | "12h" | "24h" | "48h" | "7d" | "all";
export const RANGE_OPTIONS: { value: RangeId; label: TextKey; refreshMs: number }[] = [
  { value: "30m", label: "range.30m", refreshMs: 2000 },
  { value: "1h", label: "range.1h", refreshMs: 2000 },
  { value: "12h", label: "range.12h", refreshMs: 10000 },
  { value: "24h", label: "range.24h", refreshMs: 10000 },
  { value: "48h", label: "range.48h", refreshMs: 20000 },
  { value: "7d", label: "range.7d", refreshMs: 30000 },
  { value: "all", label: "range.all", refreshMs: 30000 },
];
export type HistoryEvent = {
  t: number; // seconds
  kind: "connect" | "disconnect";
  name: string | null;
  ip: string | null;
  untrusted: boolean;
  after_s: number; // how long the device had been in the previous state when this was seen
};
// points: [t, rx, tx] in seconds and bytes per second; rx and tx are null in a gap (Eden or the VPN was not running).
export type HistoryData = {
  range: RangeId;
  from: number;
  to: number;
  step: number;
  since: number | null;
  points: [number, number | null, number | null][];
  events: HistoryEvent[];
};

export function useHistory(range: RangeId, enabled: boolean, minRefreshMs = 0) {
  const [data, setData] = useState<HistoryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0); // only the newest request may set the state (a slow old range must not overwrite a new one)
  const rangeRef = useRef(range);
  rangeRef.current = range;
  const load = useCallback(async () => {
    const id = ++latest.current;
    try {
      const d = await apiGet<HistoryData>(`/monitor/history?range=${rangeRef.current}`);
      if (id === latest.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (id === latest.current) setError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  useEffect(() => {
    if (enabled) void load();
  }, [range, enabled, load]);
  useVisiblePoll(load, Math.max(minRefreshMs, RANGE_OPTIONS.find((o) => o.value === range)?.refreshMs ?? 10000), enabled);
  return { data: data && data.range === range ? data : null, error };
}
