import type { CSSProperties } from "react";

export interface HBarItem {
  label: string;
  value: number;
  display: string;
  cls?: string;
  tip?: string;
  strong?: boolean;
}

/** Horizontal bars with a zero line. */
export function HBars({ items, note }: { items: HBarItem[]; note?: string }) {
  const max = Math.max(0, ...items.map((d) => d.value));
  const min = Math.min(0, ...items.map((d) => d.value));
  const span = max - min || 1;
  const zero = ((0 - min) / span) * 100;
  return (
    <div className="hbars">
      {items.map((d, i) => {
        const w = (Math.abs(d.value) / span) * 100;
        const left = d.value >= 0 ? zero : zero - w;
        return (
          <div key={i} className={"hb" + (d.strong ? " strong" : "")} data-tip={d.tip || d.label + ": " + d.display}>
            <span className="hb-l">{d.label}</span>
            <span className="hb-track">
              <i className="hb-zero" style={{ left: zero + "%" }} />
              <i className={`hb-bar ${d.cls || "cb-s1"}${d.value < 0 ? " neg" : ""}`} style={{ left: left + "%", width: Math.max(0.6, w) + "%", "--i": i } as CSSProperties} />
            </span>
            <b className="hb-v">{d.display}</b>
          </div>
        );
      })}
      {note && <p className="note">{note}</p>}
    </div>
  );
}
