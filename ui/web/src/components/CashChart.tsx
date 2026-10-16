import { useState } from "react";
import type { WeekRow } from "../types";
import { amount, dayMonth, usd } from "../format";
import { Status } from "./common";

// Geometry only: positions are derived from values for drawing. No financial value is computed here.
const W = 960, H = 320, L = 64, R = 16, T = 18, B = 34;

interface Props {
  weeks: WeekRow[];
  buffer: number;
  scenario?: WeekRow[] | null;
}

export function CashChart({ weeks, buffer, scenario }: Props) {
  const firstShort = weeks.find((w) => w.status === "shortfall")?.week ?? 1;
  const [selected, setSelected] = useState<number>(firstShort);
  const values = [...weeks, ...(scenario ?? [])].map((w) => w.closing);
  const top = Math.max(buffer * 1.15, ...values);
  const bottom = Math.min(0, ...values);
  const y = (v: number) => T + ((top - v) / (top - bottom)) * (H - T - B);
  const slot = (W - L - R) / weeks.length;
  const row = weeks.find((w) => w.week === selected) ?? weeks[0];
  const ticks = [top, buffer, 0, bottom].filter((t, i, all) => all.indexOf(t) === i);

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Closing cash balance by week">
        {weeks.map((w, i) => {
          const x = L + i * slot;
          const barX = x + slot * 0.22;
          const barW = slot * 0.56;
          const y0 = y(0), yv = y(w.closing);
          const cls = w.status === "shortfall" ? "bar-short" : w.status === "at_risk" ? "bar-risk" : "bar-ok";
          return (
            <g key={w.week} onClick={() => setSelected(w.week)} style={{ cursor: "pointer" }}>
              {w.week === selected && <rect className="sel" x={x} y={T} width={slot} height={H - T - B} />}
              <rect className={cls} x={barX} y={Math.min(y0, yv)} width={barW} height={Math.max(Math.abs(yv - y0), 1)}>
                <title>{`Week ${w.week}: closing ${usd(w.closing)}`}</title>
              </rect>
              <text x={x + slot / 2} y={H - 12} textAnchor="middle">W{w.week}</text>
            </g>
          );
        })}
        {ticks.map((t) => (
          <text key={t} x={L - 10} y={y(t) + 3.5} textAnchor="end">{amount(t)}</text>
        ))}
        <line className="buffer" x1={L} x2={W - R} y1={y(buffer)} y2={y(buffer)} />
        <text x={W - R} y={y(buffer) - 6} textAnchor="end">Buffer {usd(buffer)}</text>
        <line className="zero" x1={L} x2={W - R} y1={y(0)} y2={y(0)} />
        {scenario?.map((w, i) => (
          <line key={w.week} className="scn" x1={L + i * slot + slot * 0.12} x2={L + (i + 1) * slot - slot * 0.12} y1={y(w.closing)} y2={y(w.closing)}>
            <title>{`Scenario, week ${w.week}: ${usd(w.closing)}`}</title>
          </line>
        ))}
      </svg>
      <div className="legend">
        <span><i style={{ background: "#55585b" }} />Above buffer</span>
        <span><i style={{ border: "1px solid var(--ink)" }} />Below buffer (at risk)</span>
        <span><i style={{ background: "var(--negative)" }} />Below zero (shortfall)</span>
        {scenario && <span><i style={{ background: "var(--accent)", height: 2, verticalAlign: 3 }} />Scenario closing balance</span>}
      </div>
      <table style={{ marginTop: 18 }}>
        <thead>
          <tr><th>Week</th><th>Starts</th><th className="num">Opening</th><th className="num">Inflows</th><th className="num">Outflows</th><th className="num">Closing</th><th>Status</th></tr>
        </thead>
        <tbody>
          <tr>
            <td className="num" style={{ textAlign: "left" }}>{row.week}</td>
            <td>{dayMonth(row.start_date)}</td>
            <td className="num">{amount(row.opening)}</td>
            <td className="num">{amount(row.inflows)}</td>
            <td className="num">{amount(row.outflows)}</td>
            <td className={`num ${row.closing < 0 ? "neg" : ""}`}>{amount(row.closing)}</td>
            <td>
              <Status
                text={row.status === "at_risk" ? "At risk" : row.status === "shortfall" ? "Shortfall" : "Above buffer"}
                tone={row.status === "shortfall" ? "neg" : ""}
                solid={row.status === "shortfall"}
              />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
