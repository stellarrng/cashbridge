import { useEffect, useState } from "react";
import { api, type GreenFinanceResponse } from "../api";

export function GreenFinance() {
  const [data, setData] = useState<GreenFinanceResponse | null>(null);
  const [price,setPrice] = useState(0.12);
  const [opex,setOpex] = useState(1500);
  const [economics,setEconomics] = useState<Record<string,{annual_energy_savings_kwh:number;estimated_net_savings_usd_per_year:number;simple_payback_years:number|null;limitation:string}>>({});
  const [role, setRole] = useState<"sme" | "bank">("sme");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.getGreenFinance().then(setData).catch((e: Error) => setError(e.message)); }, []);
  async function calculateEconomics(id:string){
    setBusy(id);
    try {const x=await api.greenEconomics(id,price,opex);setEconomics(previous=>({...previous,[id]:x}));setError(null);}
    catch(e){setError((e as Error).message);}finally{setBusy(null);}
  }
  async function requestReview(id: string) {
    setBusy(id);
    try { setData(await api.requestGreenReview(id)); setError(null); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }
  return <div className="green-screen">
    <div className="green-banner">
      <div className="label">GREEN FINANCE READINESS · SYNTHETIC DEMO</div>
      <h2>Green projects, backed by evidence.</h2>
      <p>Screen project documentation and illustrative environmental impact before a bank makes any credit or green-eligibility decision.</p>
      <div className="green-switch" aria-label="Dashboard role">
        <button aria-pressed={role === "sme"} onClick={() => setRole("sme")}>SME view</button>
        <button aria-pressed={role === "bank"} onClick={() => setRole("bank")}>Bank reviewer view</button>
      </div>
    </div>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Loading green finance projects…</p>}
    {data?.projects.map((p) => <section className="green-project" key={p.project_id}>
      <div className="green-heading"><div><div className="label">{p.project_id} · {p.activity_name}</div><h3>{p.name}</h3></div><span className="green-status">{p.review_status === "PENDING_HUMAN_REVIEW" ? "Pending human review" : "Pre-screen only"}</span></div>
      <div className="green-metrics">
        <div><small>Requested financing</small><strong>${p.requested_loan_usd.toLocaleString()}</strong></div>
        <div><small>Evidence completeness</small><strong>{p.documentation_completeness_pct}%</strong></div>
        <div><small>Estimated impact / year</small><strong>{p.illustrative_annual_impact_tco2e === null ? "Unavailable" : `${p.illustrative_annual_impact_tco2e.toLocaleString()} tCO₂e`}</strong></div>
      </div>
      <p className="muted">{p.impact_basis}. Estimate only, using an illustrative emissions factor; not independently verified.</p>
      <h4>{role === "sme" ? "Documents to prepare" : "Evidence for independent verification"}</h4>
      <ul className="green-checklist">{p.evidence.map((e) => <li key={e.id}><span>{e.label}</span><span className={e.status === "missing" ? "green-missing" : "green-provided"}>{e.status === "missing" ? "Missing" : "Provided · unverified"}</span></li>)}</ul>
      {role === "bank" && <div className="green-review"><h4>Reviewer checklist</h4><p>Verify primary documents, applicable taxonomy, use of proceeds, environmental assumptions and creditworthiness. No automated approval is available.</p><ul>{p.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
      <div className="green-review"><h4>Financial payback scenario (illustrative)</h4>
        <div className="planner-fields"><label>Electricity price (USD / kWh)<input type="number" min="0" max="10" step="0.01" value={price} onChange={e=>setPrice(Number(e.target.value))}/></label>
        <label>Yearly operating costs (USD)<input type="number" min="0" value={opex} onChange={e=>setOpex(Number(e.target.value))}/></label></div>
        <div className="green-actions"><button disabled={busy!==null} onClick={()=>calculateEconomics(p.project_id)}>Estimate payback</button></div>
        {economics[p.project_id]&&<p>Net annual savings: ${economics[p.project_id].estimated_net_savings_usd_per_year.toLocaleString()};
          payback: {economics[p.project_id].simple_payback_years??"not achievable"} years. {economics[p.project_id].limitation}</p>}
      </div>
      <div className="green-actions"><button disabled={busy !== null || p.review_status === "PENDING_HUMAN_REVIEW"} onClick={() => requestReview(p.project_id)}>{p.review_status === "PENDING_HUMAN_REVIEW" ? "Review requested" : busy === p.project_id ? "Submitting…" : "Request human review"}</button><span className="muted">Demo-only internal queue; no external bank contacted.</span></div>
    </section>)}
  </div>;
}
