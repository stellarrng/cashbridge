import type { CSSProperties } from "react";
import { compactUsd } from "../lib/format";
import { niceStep, ticks } from "./scale";

export interface ColumnItem {
  label: string;
  value: number;
  cls?: string;
  tip?: string;
}

interface Props {
  items: ColumnItem[];
  /** Optional line drawn over the bars (e.g. closing cash with the advance). */
  overlay?: number[];
  overlayTip?: (value: number, index: number) => string;
  width?: number;
  height?: number;
  label?: string;
  sparseLabels?: boolean;
}

/** Vertical bars around a zero line, with rounded data ends. Draws only what the backend computed. */
export function ColumnChart({ items, overlay, overlayTip, width = 720, height = 240, label = "", sparseLabels }: Props) {
  const W = width, H = height, L = 54, R = 10, T = 12, B = 26;
  const all = items.map((d) => d.value).concat(overlay ?? []);
  let max = Math.max(0, ...all);
  let min = Math.min(0, ...all);
  const step = niceStep(max - min || 1);
  max = Math.ceil(max / step) * step;
  min = Math.floor(min / step) * step;
  const y = (v: number) => T + ((max - v) * (H - T - B)) / (max - min || 1);
  const bw = (W - L - R) / items.length;
  const gap = Math.max(2, bw * 0.22);

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label || `Chart of ${items.length} values: ` + items.slice(0, 13).map((d) => `${d.label} ${d.tip ?? d.value}`).join("; ")}>
      {ticks(min, max, step).map((v) => (
        <g key={v}>
          <line className="cg" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
          <text className="ct" x={L - 6} y={y(v) + 4} textAnchor="end">{compactUsd(v)}</text>
        </g>
      ))}
      {items.map((d, i) => {
        const x = L + i * bw + gap / 2;
        const w = bw - gap;
        const top = Math.min(y(0), y(d.value));
        const h = Math.max(1.5, Math.abs(y(d.value) - y(0)));
        const r = Math.min(4, w / 2, h);
        // rounded data end, square at the baseline
        const path =
          d.value >= 0
            ? `M${x} ${top + h}V${top + r}Q${x} ${top} ${x + r} ${top}H${x + w - r}Q${x + w} ${top} ${x + w} ${top + r}V${top + h}Z`
            : `M${x} ${top}V${top + h - r}Q${x} ${top + h} ${x + r} ${top + h}H${x + w - r}Q${x + w} ${top + h} ${x + w} ${top + h - r}V${top}Z`;
        return (
          <g key={i}>
            <path className={d.cls || "cb-s1"} d={path} data-tip={d.tip || d.label} style={{ "--i": i } as CSSProperties} />
            {(!sparseLabels || i % 2 === 0 || items.length < 9) && (
              <text className="ct" x={x + w / 2} y={H - 8} textAnchor="middle">{d.label}</text>
            )}
          </g>
        );
      })}
      {overlay && (
        <>
          <path className="cline" d={overlay.map((v, i) => (i ? "L" : "M") + (L + i * bw + bw / 2).toFixed(1) + " " + y(v).toFixed(1)).join(" ")} />
          {overlay.map((v, i) => (
            <circle key={i} className="cdot" cx={L + i * bw + bw / 2} cy={y(v)} r={4} data-tip={overlayTip ? overlayTip(v, i) : ""} />
          ))}
        </>
      )}
      <line className="cz" x1={L} x2={W - R} y1={y(0)} y2={y(0)} />
    </svg>
  );
}
