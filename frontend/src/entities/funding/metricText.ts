import { pct, usd2 } from "@/shared/lib/format";
import type { Vars } from "@/shared/i18n";
import type { LockedMetric } from "./types";

/** Render a locked pack figure with its unit. `t` supplies the "Week {w}" wording. */
export function metricText(m: LockedMetric, t: (key: string, vars?: Vars) => string): string {
  if (m.unit === "USD") return usd2(Number(m.value));
  if (m.unit === "%") return pct(Number(m.value));
  if (m.unit === "week") return t("lbl.week", { w: m.value });
  return m.value + " " + m.unit;
}
