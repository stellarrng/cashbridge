import type { CSSProperties } from "react";

export interface DonutPart {
  label: string;
  value: number;
  color: string;
  display?: string | number;
  flag?: string;
}

interface Props {
  parts: DonutPart[];
  center?: string;
  centerSub?: string;
  label?: string;
}

/** Part-to-whole ring (up to ~6 parts) with a legend. */
export function DonutChart({ parts, center, centerSub, label = "" }: Props) {
  const total = parts.reduce((s, p) => s + Math.max(0, p.value), 0) || 1;
  const R = 62, r = 40, C = 80;
  let a0 = -Math.PI / 2;
  const pt = (rad: number, ang: number): [number, number] => [C + rad * Math.cos(ang), C + rad * Math.sin(ang)];

  const segments = parts.map((p, i) => {
    const frac = Math.max(0, p.value) / total;
    if (frac <= 0) return null;
    const a1 = a0 + frac * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const [x0, y0] = pt(R, a0), [x1, y1] = pt(R, a1 - 1e-6), [x2, y2] = pt(r, a1 - 1e-6), [x3, y3] = pt(r, a0);
    const d =
      frac >= 0.9999
        ? `M${C - R} ${C}a${R} ${R} 0 1 0 ${2 * R} 0a${R} ${R} 0 1 0 ${-2 * R} 0M${C - r} ${C}a${r} ${r} 0 1 1 ${2 * r} 0a${r} ${r} 0 1 1 ${-2 * r} 0Z`
        : `M${x0} ${y0}A${R} ${R} 0 ${large} 1 ${x1} ${y1}L${x2} ${y2}A${r} ${r} 0 ${large} 0 ${x3} ${y3}Z`;
    a0 = a1;
    return <path key={i} d={d} fill={p.color} className="dseg" style={{ "--i": i } as CSSProperties} fillRule="evenodd" data-tip={`${p.label}: ${p.display ?? p.value} (${Math.round(frac * 100)}%)`} />;
  });

  return (
    <div className="donut">
      <svg viewBox="0 0 160 160" role="img" aria-label={label}>
        {segments}
        {center && (
          <>
            <text className="dc1" x={C} y={C - 2} textAnchor="middle">{center}</text>
            <text className="dc2" x={C} y={C + 16} textAnchor="middle">{centerSub ?? ""}</text>
          </>
        )}
      </svg>
      <ul className="legend-list">
        {parts.map((p, i) => (
          <li key={i}>
            <i style={{ background: p.color }} />
            <span>{p.label}</span>
            <b>{p.display ?? p.value}</b>
            <em>{Math.round((Math.max(0, p.value) / total) * 100)}%</em>
            {p.flag && <span className="pill bad">{p.flag}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
