import { useEffect, useState } from "react";
import { useI18n } from "@/shared/i18n";
import { usd } from "@/shared/lib/format";
import { fetchPublicOverview, type BridgeView, type Robustness } from "./api";

interface ChartData {
  company: string;
  weeks: number[];
  bridge: BridgeView | null;
  robustness?: Robustness;
  firstWeek: number;
  shortfall: number;
}

/** A labelled static preview, replaced by the live forecast as soon as the API answers. */
const SAMPLE: ChartData = {
  company: "Binh Duong Timberworks Co., Ltd. (SYNTHETIC)",
  weeks: [40250.4, 21219.72, 14694.66, 7975.06, 12450.3, 27757.42, -42831.63, -17358.91, 19619.13, 41137.79, 31516.0, 46503.38, 71238.16],
  bridge: {
    amount_usd: 48000, apr_pct: 17.12, funding_week: 7, trough_week: 7, residual_gap_usd: 0,
    closing_after: [40250.4, 21219.72, 14694.66, 7975.06, 12450.3, 27757.42, 5168.37, 30641.09, 18267.9, 39786.56, 30164.77, 45152.15, 69886.93],
  },
  robustness: { single_pack_p: 0.28, core_p: 0.87, core_packs: 3 },
  firstWeek: 7,
  shortfall: 42831.63,
};

export function HeroCashChart() {
  const { t } = useI18n();
  const [d, setD] = useState<ChartData>(SAMPLE);

  useEffect(() => {
    let alive = true;
    fetchPublicOverview()
      .then((o) => {
        if (!alive || !o.kpis.first_shortfall_week) return;
        setD({ company: o.company, weeks: o.weeks.map((w) => w.closing), bridge: o.bridge, robustness: o.robustness, firstWeek: o.kpis.first_shortfall_week, shortfall: o.kpis.shortfall_usd });
      })
      .catch(() => undefined); // static preview: keep the labelled sample
    return () => {
      alive = false;
    };
  }, []);

  const W = 640, H = 360, L = 58, R = 16, T = 18, B = 34;
  const all = d.weeks.concat(d.bridge ? d.bridge.closing_after : []);
  const max = Math.max(60000, ...all);
  const min = Math.min(0, ...all);
  const x = (i: number) => L + (i * (W - L - R)) / (d.weeks.length - 1);
  const y = (v: number) => T + ((max - v) * (H - T - B)) / (max - min);
  const step = 50000;
  const grid: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) grid.push(v);
  const path = (vals: number[]) => vals.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
  const area = "M" + x(0) + " " + y(0) + " " + d.weeks.map((v, i) => "L" + x(i).toFixed(1) + " " + y(Math.min(0, v)).toFixed(1)).join(" ") + " L" + x(d.weeks.length - 1) + " " + y(0) + "Z";
  const fi = d.firstWeek - 1;
  const b = d.bridge;

  const residualNote = d.robustness
    ? t("lc.robust", { a: Math.round(d.robustness.single_pack_p * 100), b: Math.round(d.robustness.core_p * 100) })
    : b && b.residual_gap_usd > 0
      ? t("lc.by", { a: usd(b.residual_gap_usd), w: b.trough_week })
      : "";

  return (
    <figure className="hero-chart glass" aria-labelledby="chartCaption">
      <div className="chart-head">
        <div>
          <span className="chart-company">{d.company.replace(" Co., Ltd.", "").replace("(SYNTHETIC)", "(synthetic)")}</span>
          <span className="chart-title">{t("chart.title")}</span>
        </div>
        <div className="legend">
          <span><i className="sw base" /><span>{t("chart.base")}</span></span>
          <span><i className="sw bridged" /><span>{t("chart.bridged")}</span></span>
        </div>
      </div>
      <svg id="cashChart" viewBox="0 0 640 360" role="img" aria-label="Weekly closing cash for 13 weeks">
        {grid.map((v) => (
          <g key={v}>
            <line className={v === 0 ? "zero" : "grid"} x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
            <text x={L - 8} y={y(v) + 4} textAnchor="end">{v === 0 ? "$0" : (v < 0 ? "−" : "") + "$" + Math.abs(v / 1000) + "k"}</text>
          </g>
        ))}
        {d.weeks.map((_, i) => i % 2 === 0 && <text key={i} x={x(i)} y={H - 10} textAnchor="middle">W{i + 1}</text>)}
        <path className="deficit-area" d={area} />
        <path className="base" d={path(d.weeks)} />
        {b && (
          <>
            <path className="bridged draw" d={path(b.closing_after)} style={{ "--len": 1400 } as React.CSSProperties} />
            <line className="span" x1={x(b.funding_week - 1)} x2={x(b.funding_week - 1)} y1={y(d.weeks[b.funding_week - 1])} y2={y(b.closing_after[b.funding_week - 1])} strokeDasharray="3 3" />
            <text className="label bridge" x={x(b.funding_week - 1) + 8} y={y(b.closing_after[b.funding_week - 1]) - 8}>{t("lc.advance", { a: usd(b.amount_usd) })}</text>
            {b.residual_gap_usd > 0 && (
              <text className="label deficit" x={x(b.trough_week - 1) - 14} y={y(b.closing_after[b.trough_week - 1]) + 4} textAnchor="end">{t("lc.still", { a: usd(b.residual_gap_usd) })}</text>
            )}
          </>
        )}
        <circle className="pulse" cx={x(fi)} cy={y(d.weeks[fi])} r={6} />
        {d.weeks.map((v, i) => v < 0 && <circle key={i} className="dot-neg" cx={x(i)} cy={y(v)} r={3.5} />)}
        <text className="label deficit" x={x(fi) - 8} y={y(d.weeks[fi]) + 4} textAnchor="end">W{d.firstWeek}: −{usd(d.shortfall)}</text>
      </svg>
      <figcaption id="chartCaption" className="chart-notes">
        <div><b>{t("lc.week", { w: d.firstWeek, a: usd(d.shortfall) })}</b><span>{t("chart.gap")}</span></div>
        <div><b>{b ? t("lc.apr", { a: usd(b.amount_usd), p: Number(b.apr_pct).toFixed(1) }) : ""}</b><span>{t("chart.bridge")}</span></div>
        <div><b>{residualNote}</b><span>{t("chart.residual")}</span></div>
      </figcaption>
    </figure>
  );
}
