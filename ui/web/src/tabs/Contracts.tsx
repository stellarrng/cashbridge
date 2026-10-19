import {useState} from "react";
import {intelligence,type ContractReview,type DraftContract,type ReconcileContract} from "../api";
const example = `SUPPLY AGREEMENT — SYNTHETIC SAMPLE
Buyer: Northern Retail LLC
Supplier: Binh Duong Timberworks
Total consideration: USD 200,000
Payment: 30% advance after signing
Payment: 40% upon delivery
Payment: 30% upon written acceptance
Supplier delivery date: 30 November 2026.
Termination: Either party may terminate with written notice.
All changes to beneficiary bank account require independent confirmation.`;
const usd=(n:number)=>`$${n.toLocaleString("en-US",{maximumFractionDigits:2})}`;
export function Contracts(){
  const [text,setText]=useState(example);
  const [invoice,setInvoice]=useState("Invoice INV-1150\nAmount: USD 260,000\nBuyer: Northern Retail LLC");
  const [amount,setAmount]=useState("");
  const [review,setReview]=useState<ContractReview|null>(null);
  const [comparison,setComparison]=useState<ReconcileContract|null>(null);
  const [draft,setDraft]=useState<DraftContract|null>(null);
  const [form,setForm]=useState({contract_type:"supply",supplier:"Binh Duong Timberworks (synthetic)",customer:"Northern Retail (synthetic)",
        scope:"Supply 100 units of finished timber components, subject to verified purchase order and acceptance.",amount:200000,governing_law:"To be confirmed with counsel"});
  const [busy,setBusy]=useState("");const [error,setError]=useState("");const [method,setMethod]=useState("");
  async function work(which:"review"|"reconcile"|"draft"){
    setBusy(which);setError("");
    try{if(which==="review")setReview(await intelligence.review(text,amount?Number(amount):undefined));
      if(which==="reconcile")setComparison(await intelligence.reconcile(text,invoice));
      if(which==="draft")setDraft(await intelligence.draft(form));}
    catch(e){setError((e as Error).message);}finally{setBusy("");}
  }
  async function upload(file?:File){if(!file)return;setBusy("upload");setError("");
    try{const extracted=await intelligence.upload(file);setText(extracted.text);setMethod(`${extracted.method}, ${extracted.pages} page(s). Verify OCR manually.`);setReview(null);}
    catch(e){setError((e as Error).message);}finally{setBusy("");}}
  function saveDraft(){if(!draft)return;const objectUrl=URL.createObjectURL(new Blob([draft.draft],{type:"text/plain;charset=utf-8"}));
    const anchor=document.createElement("a");anchor.href=objectUrl;anchor.download="CashBridge_unsigned_contract_draft.txt";anchor.click();URL.revokeObjectURL(objectUrl);}
  return <div className="intelligence-screen"><div className="intelligence-lead"><div className="label">CONTRACT INTELLIGENCE · HUMAN-IN-THE-LOOP</div><h2>Draft, verify and finance contracts.</h2>
    <p>OCR and rule-based risk signals turn payment terms into reviewable evidence. Contracts are never auto-signed, and suspected fraud is never presented as a conviction.</p></div>
    {error&&<p role="alert" className="intel-error">{error}</p>}
    <section className="intel-panel"><h3>1. Extract and review a contract</h3>
      <label className="intel-file">Upload a PDF / scanned image / TXT (max 5 MB, 10 PDF pages)<input type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" disabled={!!busy} onChange={e=>upload(e.target.files?.[0])}/></label>
      {method&&<p className="intel-note">Processed locally: {method}</p>}
      <textarea className="intel-textarea" rows={11} value={text} onChange={e=>{setText(e.target.value);setReview(null);}} aria-label="Contract text"/>
      <div className="intel-actions"><label>Optional invoice amount USD <input type="number" min="0" placeholder="e.g. 200000" value={amount} onChange={e=>setAmount(e.target.value)} /></label>
      <button className="intel-primary" onClick={()=>work("review")} disabled={!!busy}>Review contract</button></div>
      {review&&<><div className="intel-stat-grid"><div className="intel-stat"><small>Risk signals, not fraud findings</small><strong>{review.risk_signal_count}</strong></div>
        <div className="intel-stat"><small>Payment percentages detected</small><strong>{review.extracted.payment_percentage_sum==null?"N/A":`${review.extracted.payment_percentage_sum}%`}</strong></div>
        <div className="intel-stat"><small>Contract USD amounts</small><strong>{review.extracted.amounts_usd.map(usd).join(", ")||"N/A"}</strong></div></div>
        {review.flags.map((f,i)=><div className="intel-flag" key={`${f.code}${i}`}><strong>{f.severity.toUpperCase()} · {f.code}</strong><p>{f.description}</p><small>Evidence: {f.evidence}</small></div>)}
        {!review.flags.length&&<p className="intel-note">No rule-based flags. This does not establish authenticity or completeness.</p>}
        <p className="intel-note">{review.limitations.join(" ")}</p></>}
    </section>
    <section className="intel-panel"><h3>2. Contract ↔ invoice reconciliation</h3><p className="intel-note">Paste a corresponding invoice to flag amount differences; the example deliberately contains a discrepancy.</p>
      <textarea className="intel-textarea" rows={4} value={invoice} onChange={e=>{setInvoice(e.target.value);setComparison(null);}} aria-label="Invoice text"/>
      <button className="intel-primary" onClick={()=>work("reconcile")} disabled={!!busy}>Compare contract and invoice</button>
      {comparison&&<><p className={comparison.amount_mismatch?"intel-error":"intel-note"}>Invoice amount mismatch: {comparison.amount_mismatch?"REVIEW REQUIRED":"not detected"}. {comparison.limitations}</p>
        <p>Contract amounts: {comparison.contract_amounts_usd.map(usd).join(", ")||"not detected"} | Invoice amounts: {comparison.invoice_amounts_usd.map(usd).join(", ")||"not detected"}</p>
        <p className="intel-note">{comparison.flags.map(f=>f.code).join(" · ")}</p></>}
    </section>
    <section className="intel-panel"><h3>3. Generate an unsigned agreement draft</h3>
      <div className="intel-input-grid">
        <label>Contract type<select value={form.contract_type} onChange={e=>setForm({...form,contract_type:e.target.value})}><option value="supply">Supply</option><option value="services">Services</option><option value="construction">Construction services</option></select></label>
        <label>Supplier / contractor<input value={form.supplier} onChange={e=>setForm({...form,supplier:e.target.value})}/></label>
        <label>Customer / client<input value={form.customer} onChange={e=>setForm({...form,customer:e.target.value})}/></label>
        <label>Contract amount<input type="number" min="0" value={form.amount} onChange={e=>setForm({...form,amount:Number(e.target.value)})}/></label>
        <label>Governing law (counsel to confirm)<input value={form.governing_law} onChange={e=>setForm({...form,governing_law:e.target.value})}/></label>
        <label>Scope<input value={form.scope} onChange={e=>setForm({...form,scope:e.target.value})}/></label>
      </div>
      <p className="intel-note">Sample payment structure: 30% on signing, 40% on delivery, 30% on acceptance. Editable milestone API available.</p>
      <button className="intel-primary" onClick={()=>work("draft")} disabled={!!busy}>Generate contract draft</button>
      {draft&&<><p className="intel-note">Status: {draft.status}. This is a template-assisted draft, not a legally reviewed final agreement.</p>
        <textarea className="intel-textarea" rows={16} value={draft.draft} readOnly aria-label="Generated draft"/>
        <div className="intel-actions"><button onClick={saveDraft}>Save .txt draft</button><button onClick={()=>navigator.clipboard?.writeText(draft.draft)}>Copy draft text</button></div>
        <h4>Before signing</h4><ul>{draft.review_checklist.map(x=><li key={x}>{x}</li>)}</ul></>}
    </section>
  </div>;
}
