// Calls `fn` on mount and then every `ms` milliseconds while the tab is visible.
import { useEffect, useRef } from "react";

export function usePoll(fn: () => void, ms: number) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    ref.current();
    const id = setInterval(() => {
      if (!document.hidden) ref.current();
    }, ms);
    return () => clearInterval(id);
  }, [ms]);
}

// Like usePoll, but there is NO timer at all while the tab is hidden: the interval is cleared on "hidden" and started
// again (with an immediate call) on "visible", and it is cleared on unmount. Used by the Home monitor, which must cost
// nothing when it is not on screen (or when `enabled` is false).
export function useVisiblePoll(fn: () => void, ms: number, enabled = true) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!enabled) return; // switched off (Live traffic): no timer at all
    let id: number | undefined;
    const start = () => {
      if (id !== undefined) return;
      ref.current();
      id = window.setInterval(() => ref.current(), ms);
    };
    const stop = () => {
      if (id === undefined) return;
      window.clearInterval(id);
      id = undefined;
    };
    const onVisibility = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) start();
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [ms, enabled]);
}
