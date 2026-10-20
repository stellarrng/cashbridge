import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en from "./locales/en.json";
import vi from "./locales/vi.json";
import zh from "./locales/zh.json";

/** Interface text only. Text produced by the engines (findings, letters, evidence claims) stays English: it is part of the hashed record. */
export type Lang = "en" | "vi" | "zh";
export type Vars = Record<string, string | number>;

const DICTIONARIES: Record<Lang, Record<string, string>> = { en, vi, zh };
export const LANGS: ReadonlyArray<{ id: Lang; label: string }> = [
  { id: "en", label: "EN" },
  { id: "vi", label: "VI" },
  { id: "zh", label: "中文" },
];

const STORAGE_KEY = "cb.lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "vi" || saved === "zh") return saved;
  } catch {
    /* private mode */
  }
  const nav = (navigator.language || "").toLowerCase();
  return nav.startsWith("vi") ? "vi" : nav.startsWith("zh") ? "zh" : "en";
}

export interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string, vars?: Vars) => string;
  has: (key: string) => boolean;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode */
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const dict = DICTIONARIES[lang];
    return {
      lang,
      setLang,
      has: (key) => key in en,
      t: (key, vars) => {
        let s = dict[key] ?? en[key as keyof typeof en] ?? key;
        if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll("{" + k + "}", String(v));
        return s;
      },
    };
  }, [lang, setLang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}
