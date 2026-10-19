import {useEffect,useState} from "react";
import {intelligence,type BankReview} from "../api";
export function BankReviewer(){
  const [review,setReview]=useState<BankReview|null>(null);
  const [error,setError]=useState("");
  const [token,setToken]=useState("");
  const refresh=()=>{if(!token){setReview(null);return;}
    intelligence.bank(token).then(x=>{setReview(x);setError("");}).catch((e:Error)=>{setReview(null);setError(e.message);});};
  useEffect(()=>{setReview(null);},[token]);
  return <div className="intelligence-screen"><div className="intelligence-lead"><div className="label">BANK REVIEWER VIEW · SYNTHETIC READ-ONLY PREVIEW</div>
    <h2>Traceable SME financing assessment.</h2><p>Evidence, contract flags, financial health and green-document readiness in one reviewer workspace.</p>
    <p className="intel-note"><strong>Security notice:</strong> The server enforces a bank reviewer Bearer token (synthetic, single-case demo). Switching tabs never grants bank permissions. This is not production IAM or a credit decision.</p></div>
    <section className="intel-panel"><label>Server-configured reviewer token (memory only, never saved)
      <input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} placeholder="CASHBRIDGE_BANK_REVIEW_TOKEN" />
      </label><button className="intel-primary" onClick={refresh}>Unlock / refresh evidence</button>
      <button onClick={()=>{setToken("");setReview(null);setError("");}}>Lock</button></section>
    {error&&<p className="intel-error">{error}</p>}
    {review&&<><section className="intel-panel"><h3>Case evidence</h3><div className="intel-stat-grid">
      <div className="intel-stat"><small>Case</small><strong>{review.case_id}</strong></div>
      <div className="intel-stat"><small>Audit chain intact</small><strong>{review.evidence.audit_chain_ok?"YES":"NO — investigate"}</strong></div>
      <div className="intel-stat"><small>Invoice registry blocks</small><strong>{review.evidence.invoice_registry_blocks}</strong></div>
      <div className="intel-stat"><small>Credit workflow state</small><strong>{review.case_state}</strong></div></div>
      <p className="intel-note">Source: {review.evidence.source_id}. Data is synthetic; cross-institution duplicates cannot be checked in this MVP.</p></section>
      <section className="intel-panel"><h3>Financial indicators</h3><div className="intel-stat-grid">
        {Object.entries(review.financial_ratios).map(([k,v])=><div key={k} className="intel-stat"><small>{k.replace(/_/g," ")}</small><strong>{v??"N/A"}</strong></div>)}
      </div></section>
      <section className="intel-panel"><h3>Contract and fraud-signal review</h3>
        {!review.evidence.document_review?<p className="intel-note">No contract reviewed in this session. Open Contracts, review a document and refresh this view.</p>:
        <><p>Review state: {review.evidence.document_review.status}</p>{review.evidence.document_review.flags.map((f,i)=><div className="intel-flag" key={`${i}-${f.code}`}><strong>{f.code} · {f.severity}</strong><p>{f.description}</p></div>)}</>}
      </section>
      <section className="intel-panel"><h3>Funding options & green evidence</h3>
        <div className="intel-table"><table><thead><tr><th>Funding option</th><th>APR (%)</th><th>Eligibility (demo)</th></tr></thead><tbody>
          {review.funding_options.map((f)=><tr key={f.id}><td>{f.name}</td><td>{f.apr_pct?.toFixed(2)??"N/A"}</td><td>{f.eligible?"Preliminary yes":"Not eligible"}</td></tr>)}
        </tbody></table></div>
        {review.green_projects.map(p=><p key={p.project_id} className="intel-note">{p.name}: evidence completeness {p.documentation_completeness_pct}%, review {p.review_status}</p>)}
      </section><section className="intel-panel"><h3>Human underwriting checklist</h3><ul>{review.review_checklist.map(x=><li key={x}>{x}</li>)}</ul>
        <p className="intel-note">{review.notice}</p></section></>}
  </div>;
}
