// UI language: English by default, Italian selectable in Settings. The choice is saved on the server ("ui.language" in
// eden.json, so the API's messages follow it too) and in this browser (localStorage), which answers before the first
// server reply. Texts live in lib/locales/en.ts (the source: its keys define what exists) and it.ts (must have every
// key: tsc fails otherwise). Components call useT(); code outside components (formatters, helpers) uses translate().
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { en } from "./locales/en";
import { it } from "./locales/it";
import { apiGet } from "./api";

export type Lang = "en" | "it";
export type TextKey = keyof typeof en;
type Vars = Record<string, string | number>;

const DICTS: Record<Lang, Record<TextKey, string>> = { en, it };
const STORAGE_KEY = "eden-language";
const LOCALES: Record<Lang, string> = { en: "en-GB", it: "it-IT" };

function readSaved(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "en" || v === "it") return v;
  } catch {
    /* storage unavailable: use the default */
  }
  return "en";
}

// The language used by translate(): updated by the provider while it renders, so every component below it already
// sees the new one in the same render.
let current: Lang = readSaved();

function fill(text: string, vars?: Vars): string {
  return vars ? text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m)) : text;
}

export function translate(key: TextKey, vars?: Vars): string {
  return fill(DICTS[current][key] ?? DICTS.en[key] ?? key, vars);
}

// For pages without the provider (the login page): the server tells which language to use.
export function setLanguage(l: string) {
  current = l === "it" ? "it" : "en";
  document.documentElement.lang = current;
}

export const currentLocale = () => LOCALES[current];

type Ctx = { lang: Lang; setLang: (l: Lang) => void; locale: string; t: (key: TextKey, vars?: Vars) => string };
const I18nContext = createContext<Ctx>({ lang: "en", setLang: () => undefined, locale: LOCALES.en, t: translate });

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readSaved);
  current = lang;

  const setLang = useCallback((l: Lang) => {
    current = l;
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* the choice just won't persist in this browser */
    }
  }, []);

  // The server's value wins once it answers (another browser may have changed it).
  useEffect(() => {
    apiGet<{ language?: string }>("/appearance")
      .then((a) => {
        if ((a.language === "en" || a.language === "it") && a.language !== readSaved()) setLang(a.language);
      })
      .catch(() => undefined);
  }, [setLang]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = useCallback((key: TextKey, vars?: Vars) => translate(key, vars), [lang]); // eslint-disable-line react-hooks/exhaustive-deps
  return <I18nContext.Provider value={{ lang, setLang, locale: LOCALES[lang], t }}>{children}</I18nContext.Provider>;
}

export const useT = () => useContext(I18nContext);
