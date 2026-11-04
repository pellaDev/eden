// PDS ships full ".dark { ... }" CSS variable overrides but does not provide a
// theme switcher itself (verified against its config.js: setPdsConfig only
// touches brand colors, font, and field style). Toggling dark mode is a plain
// "dark" class on <html>, the same convention PDS's own CSS was built for.
import { useEffect, useState } from "react";

const KEY = "eden-theme";
export type Theme = "light" | "dark";

function systemPrefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// Saved choice if valid, otherwise the system preference.
function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage unavailable: fall through to the system preference */
  }
  return systemPrefersDark() ? "dark" : "light";
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

// Called once from main.tsx before the first render: the saved theme must apply on every page,
// not only when a component using useTheme (the Settings page) happens to mount.
export function initTheme() {
  apply(readTheme());
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    apply(theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* storage unavailable: the choice just won't persist */
    }
  }, [theme]);

  return { theme, setTheme };
}
