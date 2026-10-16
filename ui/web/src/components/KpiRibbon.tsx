import type { Kpis } from "../types";
import { amount, vnd, usd } from "../format";

export function KpiRibbon({ kpis }: { kpis: Kpis }) {
  const short = kpis.first_shortfall_week !== null && kpis.shortfall_usd !== null;
  return (
    <div className="ribbon">
      <div className="kpi">
        <div className="label">Cash today</div>
        <div className="value">{usd(kpis.cash_today_usd)}</div>
        <div className="detail">{vnd(kpis.cash_today_vnd)}</div>
      </div>
      <div className="kpi" title="Cash conversion cycle = days of stock + days to collect − days to pay suppliers">
        <div className="label">Cash conversion cycle</div>
        <div className="value">{amount(kpis.ccc.ccc)} days</div>
        <div className="detail">Stock {amount(kpis.ccc.dio)} · collect {amount(kpis.ccc.dso)} · pay {amount(kpis.ccc.dpo)}</div>
      </div>
      <div className="kpi">
        <div className="label">First shortfall</div>
        <div className={`value ${short ? "neg" : "pos"}`}>{short ? `Week ${kpis.first_shortfall_week}` : "None"}</div>
        <div className="detail">{short ? `${usd(kpis.shortfall_usd)} below zero` : "Cash stays above zero for 13 weeks"}</div>
      </div>
      <div className="kpi">
        <div className="label">Fraud attempts blocked</div>
        <div className="value">{kpis.blocked_fraud_count}</div>
        <div className="detail">Requests to change bank details</div>
      </div>
    </div>
  );
}
