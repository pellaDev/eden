// "Live traffic": the switch in the subheader that turns the Meshnet traffic scan (and its history) on or off, plus its
// settings (refresh, retention...). The state lives on the server (monitor in eden.json); this context shares it between
// the subheader, Home and Settings. It asks the server every 10 s while a tab is visible: that is also how the server
// knows a UI is open (needed by "record only while Eden is open"), and it keeps several tabs in agreement.
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { apiGet, apiPost } from "./api";
import { useVisiblePoll } from "./usePoll";

export type MonitorSettings = { refresh_seconds: number; presence_seconds: number; retention_days: number; record_when_closed: boolean };
export type LiveInfo = MonitorSettings & {
  live: boolean;
  running: boolean;
  since: number | null;
  samples: number;
  minutes: number;
  coarse: number;
  events: number;
};
type LiveCtx = {
  info: LiveInfo | null;
  busy: boolean;
  error: string | null;
  setLive: (v: boolean) => Promise<void>;
  saveSettings: (s: MonitorSettings) => Promise<boolean>;
};
const Ctx = createContext<LiveCtx>({ info: null, busy: false, error: null, setLive: async () => undefined, saveSettings: async () => false });
const HEARTBEAT_MS = 10000;

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const [info, setInfo] = useState<LiveInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const writing = useRef(false); // a poll that crosses a save must not bring the old values back
  const refresh = useCallback(() => {
    apiGet<LiveInfo>("/monitor/live")
      .then((i) => {
        if (!writing.current) setInfo(i);
      })
      .catch((e) => setError(String(e)));
  }, []);
  useVisiblePoll(refresh, HEARTBEAT_MS);
  const saveSettings = useCallback(async (v: MonitorSettings) => {
    setBusy(true);
    setError(null);
    writing.current = true;
    try {
      setInfo(await apiPost<LiveInfo>("/monitor/settings", v));
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }, []);
  const setLive = useCallback(async (v: boolean) => {
    setBusy(true);
    setError(null);
    writing.current = true;
    try {
      setInfo(await apiPost<LiveInfo>("/monitor/live", { live: v }));
    } catch (e) {
      setError(String(e));
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }, []);
  return <Ctx.Provider value={{ info, busy, error, setLive, saveSettings }}>{children}</Ctx.Provider>;
}

export const useLive = () => useContext(Ctx);
