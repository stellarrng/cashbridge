import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/** Display preferences. They live on this device only and change nothing on the server. */
export type ThemeChoice = "system" | "light" | "dark";

export const PREFS = {
  view: ["advanced", "simple"],
  text: ["normal", "large"],
  motion: ["normal", "reduce"],
  contrast: ["normal", "high"],
} as const;

export type PrefKey = keyof typeof PREFS;
type PrefValues = { [K in PrefKey]: (typeof PREFS)[K][number] };

const store = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* private mode: keep for this page only */
    }
  },
  remove(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  },
};

function readPref<K extends PrefKey>(key: K): PrefValues[K] {
  const v = store.get("cb." + key);
  return ((PREFS[key] as readonly string[]).includes(v ?? "") ? v : PREFS[key][0]) as PrefValues[K];
}

function readTheme(): ThemeChoice {
  const v = store.get("cb.theme");
  return v === "light" || v === "dark" ? v : "system";
}

function paintDocument(theme: ThemeChoice, prefs: PrefValues): void {
  const root = document.documentElement;
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
  for (const k of Object.keys(prefs) as PrefKey[]) root.dataset[k] = prefs[k];
}

/** Call once before the first render so there is no flash of the wrong theme. */
export function applyStoredPreferences(): void {
  paintDocument(readTheme(), { view: readPref("view"), text: readPref("text"), motion: readPref("motion"), contrast: readPref("contrast") });
}

interface Preferences extends PrefValues {
  theme: ThemeChoice;
  /** What the screen actually shows right now (resolves "system"). */
  resolvedTheme: "light" | "dark";
  setTheme: (theme: ThemeChoice) => void;
  /** Flip between light and dark (the top-bar button). */
  toggleTheme: () => void;
  setPref: <K extends PrefKey>(key: K, value: PrefValues[K]) => void;
}

const Ctx = createContext<Preferences | null>(null);

const systemDark = () => typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeChoice>(readTheme);
  const [prefs, setPrefs] = useState<PrefValues>(() => ({ view: readPref("view"), text: readPref("text"), motion: readPref("motion"), contrast: readPref("contrast") }));
  const [, force] = useState(0);

  useEffect(() => paintDocument(theme, prefs), [theme, prefs]);

  // "system" follows the OS: repaint the toggle icon when it changes.
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => force((n) => n + 1);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((next: ThemeChoice) => {
    setThemeState(next);
    if (next === "system") store.remove("cb.theme");
    else store.set("cb.theme", next);
  }, []);

  const setPref = useCallback(<K extends PrefKey>(key: K, value: PrefValues[K]) => {
    setPrefs((p) => ({ ...p, [key]: value }));
    store.set("cb." + key, value);
  }, []);

  const value = useMemo<Preferences>(() => {
    const resolvedTheme = theme === "system" ? (systemDark() ? "dark" : "light") : theme;
    return { ...prefs, theme, resolvedTheme, setTheme, setPref, toggleTheme: () => setTheme(resolvedTheme === "dark" ? "light" : "dark") };
  }, [prefs, theme, setTheme, setPref]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePreferences(): Preferences {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePreferences must be used inside <PreferencesProvider>");
  return ctx;
}
