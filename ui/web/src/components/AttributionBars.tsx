import type { Attribution } from "../types";
import { usd } from "../format";

// Bar lengths are proportional to |amount| for drawing only.
export function AttributionBars({ items, shortfall }: { items: Attribution[]; shortfall: number | null }) {
  if (items.length === 0) return <div className="empty">No shortfall in this scenario, so there is nothing to attribute.</div>;
  const largest = Math.max(...items.map((i) => Math.abs(i.amount_usd)));
  const ordered = [...items].sort((a, b) => (a.amount_usd === b.amount_usd ? 0 : a.amount_usd < b.amount_usd ? 1 : -1)); // comparison only
  return (
    <div className="bars">
      {ordered.map((item) => (
        <div className="line" key={item.source_ref + item.driver}>
          <span>{item.driver}</span>
          <span className={`num right ${item.amount_usd < 0 ? "muted" : ""}`}>
            {item.amount_usd < 0 ? "offset " : ""}{usd(Math.abs(item.amount_usd))}
          </span>
          <div className="track">
            <div className={`fill ${item.amount_usd < 0 ? "offset" : ""}`} style={{ width: `${(Math.abs(item.amount_usd) / largest) * 100}%` }} />
          </div>
        </div>
      ))}
      {shortfall !== null && (
        <div className="line" style={{ borderBottom: "1px solid var(--ink)" }}>
          <strong>Shortfall in the first negative week</strong>
          <strong className="num right neg">{usd(shortfall, true)}</strong>
        </div>
      )}
    </div>
  );
}
