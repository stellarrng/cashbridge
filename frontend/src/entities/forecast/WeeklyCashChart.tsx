import { ColumnChart } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { usd, usd2 } from "@/shared/lib/format";
import type { ForecastWeek } from "./types";

/** Weekly closing cash as columns coloured by status, with an optional "with the advance" line and a legend. */
export function WeeklyCashChart({ weeks, after }: { weeks: ForecastWeek[]; after?: number[] }) {
  const { t } = useI18n();
  return (
    <>
      <ColumnChart
        label={t("ov.weekly")}
        items={weeks.map((w) => ({
          label: "W" + w.week,
          value: w.closing,
          cls: w.status === "shortfall" ? "cb-neg" : w.status === "at_risk" ? "cb-risk" : "cb-good",
          tip: `${t("lbl.week", { w: w.week })}: ${usd2(w.closing)}\n${t("lbl.in")} ${usd(w.inflows)} · ${t("lbl.out")} ${usd(w.outflows)}`,
        }))}
        overlay={after}
        overlayTip={(v, i) => `${t("lbl.withAdvance")} ${t("lbl.week", { w: i + 1 })}: ${usd2(v)}`}
      />
      <ul className="legend-inline">
        <li><i className="cb-good" />{t("ov.lg.ok")}</li>
        <li><i className="cb-risk" />{t("ov.lg.risk")}</li>
        <li><i className="cb-neg" />{t("ov.lg.neg")}</li>
        {after && <li><i className="line" />{t("lbl.withAdvance")}</li>}
      </ul>
    </>
  );
}
