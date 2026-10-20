import { useI18n } from "../i18n";
import { usePreferences } from "../preferences";

const SUN = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);
const MOON = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);

/** Top-bar light/dark toggle. */
export function ThemeButton() {
  const { t } = useI18n();
  const { resolvedTheme, toggleTheme } = usePreferences();
  const dark = resolvedTheme === "dark";
  const label = t(dark ? "ui.light" : "ui.dark");
  return (
    <button className="icon-btn" type="button" aria-label={label} title={label} onClick={toggleTheme}>
      {dark ? SUN : MOON}
    </button>
  );
}
