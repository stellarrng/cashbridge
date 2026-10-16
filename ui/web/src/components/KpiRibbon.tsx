import type { Kpis } from "../types";
import { amount, vnd, usd } from "../format";

export function KpiRibbon({ kpis }: { kpis: Kpis }) {
  const short = kpis.first_shortfall_week !== null && kpis.shortfall_usd !== null;
  return (
    <div className="ribbon">
      <div className="kpi">
        <div className="micro">Cash today</div>
        <div className="value">{usd(kpis.cash_today_usd)}</div>
        <div className="detail">{vnd(kpis.cash_today_vnd)}</div>
      </div>
      <div className="kpi" title="CCC = DIO + DSO - DPO, computed from the ledger">
        <div className="micro">Cash conversion cycle</div>
        <div className="value">{amount(kpis.ccc.ccc)} days</div>
        <div className="detail">DIO {amount(kpis.ccc.dio)} · DSO {amount(kpis.ccc.dso)} · DPO {amount(kpis.ccc.dpo)}</div>
      </div>
      <div className="kpi">
        <div className="micro">First shortfall</div>
        <div className={`value ${short ? "neg" : "pos"}`}>{short ? `Week ${kpis.first_shortfall_week}` : "None"}</div>
        <div className="detail">{short ? `${usd(kpis.shortfall_usd)} below zero` : "13 weeks above zero"}</div>
      </div>
      <div className="kpi">
        <div className="micro">Fraud attempts blocked</div>
        <div className="value">{kpis.blocked_fraud_count}</div>
        <div className="detail">Bank-detail change requests</div>
      </div>
    </div>
  );
}
