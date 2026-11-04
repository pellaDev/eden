// Name of the computer Eden runs on ("host_name" in eden.json, set in Impostazioni). Fetched once when the app loads:
// a change made in Settings reaches the rest of the UI after the page is reloaded (setHostName updates it at once here).
import { createContext, useContext, useEffect, useState } from "react";
import { apiGet } from "./api";

type HostCtx = { hostName: string; setHostName: (n: string) => void };
const Ctx = createContext<HostCtx>({ hostName: "Eden", setHostName: () => undefined });

export function HostProvider({ children }: { children: React.ReactNode }) {
  const [hostName, setHostName] = useState("Eden"); // neutral until the backend answers
  useEffect(() => {
    apiGet<{ host_name: string }>("/host")
      .then((h) => setHostName(h.host_name))
      .catch(() => undefined);
  }, []);
  return <Ctx.Provider value={{ hostName, setHostName }}>{children}</Ctx.Provider>;
}

export const useHost = () => useContext(Ctx);
