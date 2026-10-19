import {useEffect,useState} from "react";
import {intelligence, type FinancialOverview, type FundingScenario, type ProjectReview} from "../api";
const money = (n: number | null | undefined) => n == null ? "N/A" : `$${n.toLocaleString("en-US",{maximumFractionDigits:0})}`;
const ratioNames: Record<string,string> = {
  dso_days_estimate:"DSO days (year-end estimate)", dio_days_estimate:"DIO days (year-end estimate)",
  dpo_days:"DPO days (data required)", cash_conversion_cycle_days:"CCC days (data required)",
  net_working_capital_usd:"Net working capital ($)", receivables_to_revenue_pct:"Receivables / revenue %",
  inventory_to_cogs_pct:"Inventory / COGS %", operating_margin_pct:"Operating margin %",
  current_ratio:"Current ratio", quick_ratio:"Quick ratio", cash_ratio:"Cash ratio",
  gross_margin_pct:"Gross margin %", ebitda_margin_pct:"EBITDA margin %",
  interest_coverage:"Interest coverage", dscr_proxy:"DSCR proxy",
  debt_to_equity:"Debt / equity", cash_runway_months_gross_expenses:"Cash runway (months, zero receipts)"
};
const baseScenario = {marketing_increase_pct:25,receipts_delayed_pct:10,new_loan_usd:0,
  loan_apr_pct:15,horizon_months:3,minimum_reserve_usd:20000};
const baseProject = {contract_value_usd:200000,upfront_cost_usd:110000,remaining_cost_usd:55000,
  available_cash_usd:60000,minimum_reserve_usd:15000,advance_payment_pct:20,
  stress_cost_overrun_pct:15,loan_apr_pct:15,financing_days:90,
  workforce_required_hours:400,workforce_available_hours:300,outsourced_hourly_cost_usd:25};

export function Analytics() {
  const [overview,setOverview] = useState<FinancialOverview|null>(null);
  const [scenarioParams,setScenarioParams] = useState<Record<string,number>>(baseScenario);
  const [projectParams,setProjectParams] = useState<Record<string,number>>(baseProject);
  const [scenario,setScenario] = useState<FundingScenario|null>(null);
  const [project,setProject] = useState<ProjectReview|null>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState("");
  useEffect(()=>{intelligence.summary().then(setOverview).catch((e:Error)=>setError(e.message));},[]);
  async function run(name:"scenario"|"project") {
    setBusy(name);setError("");
    try {if(name === "scenario")setScenario(await intelligence.scenario(scenarioParams));
    else setProject(await intelligence.project(projectParams));}
    catch(e){setError((e as Error).message);} finally{setBusy("");}
  }
  return <div className="intelligence-screen">
    <div className="intelligence-lead"><div className="label">SOURCE-LINKED EDA · SYNTHETIC LEDGER</div>
      <h2>Financial Intelligence Lab</h2><p>Deterministic finance ratios, expense analytics, marketing trade-offs and project funding stress tests. Not a credit approval engine.</p></div>
    {error && <p className="intel-error" role="alert">{error}</p>}
    {!overview && <p>Loading financial ledger…</p>}
    {overview && <section className="intel-panel"><div className="intel-heading"><h3>SME financial health</h3><small>Evidence: {overview.source_id}</small></div>
      <div className="intel-stat-grid">{Object.entries(overview.ratios).map(([key,value])=><div key={key} className="intel-stat"><small>{ratioNames[key]??key}</small><strong>{value == null ? "N/A" : `${value.toLocaleString("en-US",{maximumFractionDigits:3})}${key.endsWith("_pct")?"%":""}`}</strong></div>)}</div>
      <p className="intel-note">DSCR is an EBITDA / annual debt-service proxy, not cash flow available for debt service. Runway assumes zero receipts. DPO and CCC require verified accounts payable data; unavailable metrics display N/A, never guessed values. All financial inputs are illustrative.</p>
    </section>}
    {overview && <section className="intel-panel"><h3>Exploratory data analysis (12 months)</h3>
      <div className="intel-stat-grid"><div className="intel-stat"><small>Average monthly expenses</small><strong>{money(overview.highlights.avg_monthly_expenses_usd)}</strong></div>
      <div className="intel-stat"><small>Average monthly marketing</small><strong>{money(overview.highlights.avg_monthly_marketing_usd)}</strong></div>
      <div className="intel-stat"><small>Estimated EBITDA / year</small><strong>{money(overview.highlights.ebitda_usd)}</strong></div></div>
      <div className="intel-table"><table><thead><tr><th>Month</th><th>Revenue</th><th>Expenses</th><th>Marketing</th><th>Payroll</th><th>Supplier</th></tr></thead><tbody>
      {overview.eda.monthly.map(x=><tr key={x.month}><td>{x.month}</td><td>{money(x.revenue)}</td><td>{money(x.expenses)}</td><td>{money(x.marketing)}</td><td>{money(x.payroll)}</td><td>{money(x.supplier)}</td></tr>)}
      </tbody></table></div><p className="intel-note">Expense z-score flags: {overview.eda.expense_outliers.length?overview.eda.expense_outliers.map(x=>`${x.month} (${x.z_score})`).join(", "):"None above threshold"}. Statistical outliers are not fraud findings.</p>
    </section>}
    <section className="intel-panel"><h3>Marketing budget & financing what-if</h3>
      <div className="intel-input-grid">{Object.entries(baseScenario).map(([key])=><label key={key}>{key.replace(/_/g," ")}
      <input type="number" value={scenarioParams[key]} step={key==="marketing_increase_pct"?5:1} onChange={e=>{setScenarioParams({...scenarioParams,[key]:Number(e.target.value)});setScenario(null);}} /></label>)}</div>
      <button className="intel-primary" onClick={()=>run("scenario")} disabled={busy!==""}>Run cash simulation</button>
      {scenario && <><div className="intel-stat-grid"><div className="intel-stat"><small>Baseline ending cash</small><strong>{money(scenario.baseline_ending_cash_usd)}</strong></div>
      <div className="intel-stat"><small>Scenario ending cash</small><strong>{money(scenario.scenario_ending_cash_usd)}</strong></div><div className="intel-stat"><small>Minimum cash</small><strong>{money(scenario.minimum_cash_usd)}</strong></div></div>
      <p className={scenario.reserve_breach?"intel-error":"intel-note"}>Minimum cash reserve {scenario.reserve_breach?"BREACHED — intervention required":"not breached"} under these assumptions.</p>
      <div className="intel-bars">{scenario.schedule.map(x=><div key={x.month}><span>Month {x.month}</span><div className="intel-bar-track"><div style={{width:`${Math.min(100,Math.max(1,x.closing_cash_usd/Math.max(1,scenario.baseline_ending_cash_usd)*100))}%`}} /></div><strong>{money(x.closing_cash_usd)}</strong></div>)}</div>
      <ul>{scenario.limitations.map(x=><li key={x}>{x}</li>)}</ul></>}
    </section>
    <section className="intel-panel"><h3>Project / bid financial feasibility</h3><p className="intel-note">Assess peak funding gap and a delayed-advance + cost-overrun stress scenario before accepting a project.</p>
      <div className="intel-input-grid">{Object.entries(baseProject).map(([key])=><label key={key}>{key.replace(/_/g," ")}<input type="number" step="1" value={projectParams[key]}
        onChange={e=>{setProjectParams({...projectParams,[key]:Number(e.target.value)});setProject(null);}}/></label>)}</div>
      <button className="intel-primary" onClick={()=>run("project")} disabled={busy!==""}>Assess project</button>
      {project&&<><div className="intel-stat-grid"><div className="intel-stat"><small>Upfront funding gap</small><strong>{money(project.initial_funding_gap_usd)}</strong></div>
        <div className="intel-stat"><small>Stress funding gap</small><strong>{money(project.stress_gap_if_advance_delayed_and_cost_overruns_usd)}</strong></div>
        <div className="intel-stat"><small>Indicative margin after interest</small><strong>{project.estimated_margin_pct}%</strong></div></div>
        <p className="intel-note">Team capacity gap: {project.workforce_readiness.uncovered_team_hours} hours. Estimated incremental outsourcing: {money(project.workforce_readiness.indicative_outsourcing_cost_usd)}.</p>
        <ul>{project.limitations.map(x=><li key={x}>{x}</li>)}</ul><p className="intel-note">Final bid decision requires human review.</p></>}
    </section>
  </div>;
}
