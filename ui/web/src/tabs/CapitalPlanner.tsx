import { useState } from "react";
import { api, type CapitalPlanInput, type CapitalPlanResult } from "../api";

const initial: CapitalPlanInput = {
  available_cash_usd: 100000, minimum_reserve_usd: 20000,
  working_capital_usd: 50000, marketing_usd: 20000, green_investment_usd: 60000,
};
const fields: Array<[keyof CapitalPlanInput, string]> = [
  ["available_cash_usd", "Available cash (USD)"],
  ["minimum_reserve_usd", "Minimum liquidity reserve (USD)"],
  ["working_capital_usd", "Working capital spending (USD)"],
  ["marketing_usd", "Marketing budget (USD)"],
  ["green_investment_usd", "Green investment spending (USD)"],
];
const usd = (n: number) => `$${n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
export function CapitalPlanner() {
  const [plan, setPlan] = useState<CapitalPlanInput>(initial);
  const [result, setResult] = useState<CapitalPlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function evaluate() {
    setBusy(true); setError(null);
    try { setResult(await api.evaluateCapitalPlan(plan)); }
    catch (e) { setResult(null); setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="green-screen">
    <div className="green-banner">
      <div className="label">SME CAPITAL PLANNING · SYNTHETIC SCENARIOS</div>
      <h2>Decide what to fund, not just how to borrow.</h2>
      <p>Test a liquidity reserve, marketing spending, working capital needs and green projects before considering external finance. No borrowing is triggered.</p>
    </div>
    <section className="green-project">
      <h3>Budget allocation scenario</h3>
      <div className="planner-fields">
        {fields.map(([key, label]) => <label key={key}>{label}<input type="number" min="0" max="1000000000" step="100" value={plan[key]} onChange={(e) => { setPlan({...plan, [key]: Number(e.target.value)}); setResult(null); }} /></label>)}
      </div>
      <div className="green-actions"><button onClick={evaluate} disabled={busy}>{busy ? "Calculating…" : "Analyze budget"}</button><span className="muted">Calculations performed by the Python backend.</span></div>
      {error && <p role="alert">{error}</p>}
      {result && <div aria-live="polite">
        <div className="green-metrics">
          <div><small>Deployable cash after reserve</small><strong>{usd(result.deployable_cash_usd)}</strong></div>
          <div><small>Total planned expenditure</small><strong>{usd(result.planned_spend_usd)}</strong></div>
          <div><small>Illustrative external funding gap</small><strong>{usd(result.funding_gap_usd)}</strong></div>
        </div>
        <div className="green-review"><h4>What-if: defer marketing spending</h4>
          <p>Gap with marketing deferred: <strong>{usd(result.gap_if_marketing_deferred_usd)}</strong>. Potential immediate gap reduction: <strong>{usd(result.potential_gap_reduction_usd)}</strong>.</p>
          <h4>Model limitations</h4><ul>{result.notes.map(note => <li key={note}>{note}</li>)}</ul>
        </div>
      </div>}
    </section>
  </div>;
}
