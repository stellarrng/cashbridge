import { compactUsd } from "../lib/format";
import { niceStep, ticks } from "./scale";

export interface LineSeries {
  name: string;
  values: number[];
  color: string;
  width?: number;
  dash?: string;
  muted?: boolean;
}

interface Props {
  labels: string[];
  series: LineSeries[];
  /** Tooltip value format. */
  fmt?: (v: number) => string;
  /** Axis label format (defaults to compact USD). */
  yfmt?: (v: number) => string;
  /** Direct labels at the right end instead of relying on the legend alone. */
  endLabels?: boolean;
  annotate?: { index: number; text: string };
  tipExtra?: (index: number) => string;
  dots?: "all" | "ends";
  width?: number;
  height?: number;
  label?: string;
}

/** Line chart over shared categories. Muted series are drawn first so the focus series sits on top. */
export function LineChart({ labels, series, fmt, yfmt = compactUsd, endLabels, annotate, tipExtra, dots = "all", width = 720, height = 230, label = "" }: Props) {
  const W = width, H = height, L = 54, R = endLabels ? 132 : 16, T = annotate ? 26 : 12, B = 26;
  const all = series.flatMap((s) => s.values);
  let max = Math.max(...all);
  const min = Math.min(0, ...all);
  const step = niceStep(max - min || 1);
  max = Math.ceil(max / step) * step;
  const x = (i: number) => L + (i * (W - L - R)) / (labels.length - 1);
  const y = (v: number) => T + ((max - v) * (H - T - B)) / (max - min || 1);
  const last = labels.length - 1;
  const colW = (W - L - R) / labels.length;

  const placed = series.map((s) => ({ name: s.name, y: y(s.values[last]), color: s.color })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < placed.length; i++) if (placed[i].y - placed[i - 1].y < 15) placed[i].y = placed[i - 1].y + 15;

  const ordered = series.map((s) => s).sort((a, b) => Number(Boolean(b.muted)) - Number(Boolean(a.muted)));

  return (
    <>
      <ul className="legend-inline">
        {series.map((s, i) => (
          <li key={i}>
            <i style={{ background: s.color, opacity: s.dash ? 0.75 : undefined }} />
            {s.name}
          </li>
        ))}
      </ul>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        {ticks(min, max, step).map((v) => (
          <g key={v}>
            <line className="cg" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
            <text className="ct" x={L - 6} y={y(v) + 4} textAnchor="end">{yfmt(v)}</text>
          </g>
        ))}
        {labels.map((l, i) => i % 2 === 0 && <text key={i} className="ct" x={x(i)} y={H - 8} textAnchor="middle">{l}</text>)}
        {annotate && (
          <>
            <line x1={x(annotate.index)} x2={x(annotate.index)} y1={T - 4} y2={H - B} stroke="var(--ink-3)" strokeDasharray="3 4" strokeWidth={1} />
            <text className="ct" x={Math.min(x(annotate.index) + 6, W - R - 4)} y={T - 10} textAnchor={x(annotate.index) + 160 > W - R ? "end" : "start"}>{annotate.text}</text>
          </>
        )}
        {ordered.map((s, i) => (
          <path
            key={i}
            className={s.dash ? "line-soft" : "line-draw"}
            pathLength={s.dash ? undefined : 1}
            fill="none"
            stroke={s.color}
            strokeWidth={s.width || 2}
            strokeDasharray={s.dash}
            opacity={s.muted ? 0.75 : 1}
            strokeLinejoin="round"
            strokeLinecap="round"
            d={s.values.map((v, j) => (j ? "L" : "M") + x(j).toFixed(1) + " " + y(v).toFixed(1)).join(" ")}
          />
        ))}
        {labels.map((l, i) => {
          const tip = l + "\n" + series.map((s) => `${s.name}: ${fmt ? fmt(s.values[i]) : s.values[i]}`).join("\n") + (tipExtra ? "\n" + tipExtra(i) : "");
          return (
            <g key={i}>
              <rect className="hit" x={x(i) - colW / 2} y={T} width={colW} height={H - T - B} data-tip={tip} />
              {series.map((s, j) =>
                dots === "all" || i === last ? (
                  <circle key={j} cx={x(i)} cy={y(s.values[i])} r={dots === "all" ? 3 : 4} fill={s.color} stroke="var(--surface, #fff)" strokeWidth={2} className="lpt" />
                ) : null,
              )}
            </g>
          );
        })}
        {endLabels &&
          placed.map((p, i) => (
            <g key={i}>
              <line x1={x(last) + 7} x2={x(last) + 17} y1={p.y} y2={p.y} stroke={p.color} strokeWidth={2} />
              <text className="ct cl" x={x(last) + 21} y={p.y + 4}>{p.name}</text>
            </g>
          ))}
      </svg>
    </>
  );
}
