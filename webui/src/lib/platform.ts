// Which edition of Eden this is, from /api/platform: the Windows edition words the texts that name files and tools
// differently, and some pages exist only where the backend says so (`session`). Asked once per page load; until the
// answer arrives nothing optional is shown and the Linux wording is used.
import { useEffect, useState } from "react";
import { apiGet } from "./api";

type Info = { session: boolean; windows: boolean; version: string };
let cached: Promise<Info> | null = null;
const ask = () =>
  (cached ??= apiGet<{ session?: boolean; platform?: string; version?: string }>("/platform")
    .then((s) => ({ session: s.session === true, windows: s.platform === "windows", version: s.version ?? "" }))
    .catch(() => ({ session: false, windows: false, version: "" })));

function useInfo(): Info {
  const [info, setInfo] = useState<Info>({ session: false, windows: false, version: "" });
  useEffect(() => {
    let live = true;
    void ask().then((i) => live && setInfo(i));
    return () => {
      live = false;
    };
  }, []);
  return info;
}

export const useSessionAvailable = (): boolean => useInfo().session;
export const useVersion = (): string => useInfo().version;
export const useWindows = (): boolean => useInfo().windows;
