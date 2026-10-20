/** Display helpers. The browser only formats numbers the backend computed; it never derives money. */

export type Num = number | null | undefined;

export function usd(x: Num, digits = 0): string {
  if (x == null || Number.isNaN(Number(x))) return "n/a";
  const n = Number(x);
  return (n < 0 ? "−" : "") + "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export const usd2 = (x: Num): string => usd(x, 2);

export function pct(x: Num, digits = 1): string {
  return x == null ? "n/a" : Number(x).toFixed(digits) + "%";
}

/** 0.873 -> "87%" (probabilities). */
export function pp(x: Num): string {
  return x == null ? "–" : Math.round(x * 100) + "%";
}

/** "AWAITING_APPROVAL" -> "awaiting approval". */
export function human(s: unknown): string {
  return String(s ?? "").replaceAll("_", " ").toLowerCase();
}

/** First letter capital: for status text that stands on its own ("awaiting approval" -> "Awaiting approval"). */
export function sentence(s: unknown): string {
  const t = String(s ?? "");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Compact axis label: 12500 -> "$13k", 2_500_000 -> "$2.5M". */
export function compactUsd(v: number): string {
  if (v === 0) return "$0";
  const a = Math.abs(v);
  return (v < 0 ? "−" : "") + "$" + (a >= 1e6 ? (a / 1e6).toFixed(1) + "M" : Math.round(a / 1000) + "k");
}

export function formatExpiry(value: string | number, lang: string): string {
  const d = typeof value === "number" || /^\d+$/.test(String(value)) ? new Date(Number(value) * 1000) : new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const locale = ({ en: "en-GB", vi: "vi-VN", zh: "zh-CN" } as Record<string, string>)[lang] ?? "en-GB";
  return d.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}
