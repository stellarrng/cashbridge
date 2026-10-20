import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, EngineNote, Kpi, Kpis, Note, PageHead, Panel } from "@/shared/ui";
import { analyzeContract, downloadDraftDocx, draftContract, extractUpload, reconcileInvoice, type ContractAnalysis, type DraftInput, type ReconcileResult } from "./api";
import { FlagList } from "./FlagList";

const SAMPLE_CONTRACT =
  "SUPPLY AGREEMENT (SYNTHETIC SAMPLE)\nCustomer: Northern Retail LLC\nTotal consideration: USD 200,000\nPayment 30% advance\nPayment 40% upon delivery\nPayment 30% after acceptance\nTermination: Either party may terminate after written notice.\nChanges to bank account require callback verification.";
const SAMPLE_INVOICE = "Invoice INV-1188, USD 260,000";

// Kept between visits so navigating away and back does not lose what was pasted (like the original app).
const kept = { contract: SAMPLE_CONTRACT, invoice: SAMPLE_INVOICE };

type Outcome = { kind: "review"; data: ContractAnalysis } | { kind: "compare"; data: ReconcileResult } | null;

export default function ContractsScreen(_: ScreenProps) {
  const { t } = useI18n();
  const act = useAct();
  const [contract, setContract] = useState(kept.contract);
  const [invoice, setInvoice] = useState(kept.invoice);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [draft, setDraft] = useState("");
  const draftForm = useRef<HTMLFormElement>(null);

  const editContract = (v: string) => { kept.contract = v; setContract(v); };
  const editInvoice = (v: string) => { kept.invoice = v; setInvoice(v); };

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const d = await act(() => extractUpload(f), (r) => `Read locally (${r.method}). Check every amount and party.`);
    if (d) editContract(d.text);
  }

  const draftData = (): DraftInput => {
    const p = Object.fromEntries(new FormData(draftForm.current as HTMLFormElement).entries());
    return { ...(p as unknown as DraftInput), amount: Number(p.amount) };
  };

  async function review() {
    const data = await act(() => analyzeContract(contract));
    if (data) setOutcome({ kind: "review", data });
  }
  async function compare() {
    const data = await act(() => reconcileInvoice(contract, invoice));
    if (data) setOutcome({ kind: "compare", data });
  }
  async function generate(e: FormEvent) {
    e.preventDefault();
    const r = await act(() => draftContract(draftData()));
    if (r) setDraft(r.draft);
  }

  return (
    <>
      <PageHead title={t("ctr.title")} lede={t("ctr.lede")} />
      <EngineNote />
      <Panel title="1" sub="PDF / PNG / JPG / TXT ≤ 5 MB">
        <label className="field">File<input type="file" accept=".txt,.pdf,.png,.jpg,.jpeg" onChange={upload} /></label>
        <label className="field mt-2">Contract<textarea rows={9} value={contract} onChange={(e) => editContract(e.target.value)} /></label>
        <label className="field mt-2">Invoice<textarea rows={2} value={invoice} onChange={(e) => editInvoice(e.target.value)} /></label>
        <div className="row mt-2">
          <Button variant="bridge" onClick={() => void review()}>Review contract</Button>
          <Button variant="ghost" onClick={() => void compare()}>Compare with invoice</Button>
        </div>
        <div>
          {outcome?.kind === "review" && (
            <>
              <div className="mt-2">
                <Kpis>
                  <Kpi label="Review flags" tone={outcome.data.risk_signal_count ? "warn" : "pos"} value={outcome.data.risk_signal_count} />
                  <Kpi label="Payment terms sum" value={outcome.data.extracted.payment_percentage_sum == null ? "–" : outcome.data.extracted.payment_percentage_sum + "%"} />
                  <Kpi label="Amounts found" value={outcome.data.extracted.amounts_usd.map((a) => usd(a)).join(", ") || "–"} />
                </Kpis>
              </div>
              <FlagList flags={outcome.data.flags} />
              {(outcome.data.limitations || []).map((l, i) => <Note key={i}>{l}</Note>)}
            </>
          )}
          {outcome?.kind === "compare" && (
            <>
              <div className="mt-2">
                <Kpis>
                  <Kpi label="Contract" value={outcome.data.contract_amounts_usd.map((a) => usd(a)).join(", ")} />
                  <Kpi label="Invoice" value={outcome.data.invoice_amounts_usd.map((a) => usd(a)).join(", ")} />
                  <Kpi label="Mismatch" tone={outcome.data.amount_mismatch ? "neg" : "pos"} value={outcome.data.amount_mismatch ? "yes" : "no"} />
                </Kpis>
              </div>
              <FlagList flags={outcome.data.flags} />
              <Note>{outcome.data.limitations}</Note>
            </>
          )}
        </div>
      </Panel>
      <Panel title="2" sub="Unsigned draft">
        <form ref={draftForm} onSubmit={generate}>
          <div className="inputs">
            <label className="field">Type<select name="contract_type"><option>supply</option><option>services</option><option>construction</option></select></label>
            <label className="field">Supplier<input name="supplier" defaultValue="Binh Duong Timberworks (synthetic)" /></label>
            <label className="field">Customer<input name="customer" defaultValue="Northern Retail (synthetic)" /></label>
            <label className="field">Amount (USD)<input name="amount" type="number" defaultValue={200000} /></label>
            <label className="field">Scope<input name="scope" defaultValue="Supply verified goods under purchase order" /></label>
            <label className="field">Governing law<input name="governing_law" defaultValue="To be confirmed by counsel" /></label>
          </div>
          <div className="row">
            <Button variant="bridge" type="submit">Generate draft</Button>
            <Button variant="ghost" onClick={() => void act(() => downloadDraftDocx(draftData()))}>.docx</Button>
          </div>
        </form>
        <label className="field mt-2">Draft<textarea rows={14} readOnly value={draft} /></label>
        <Note>Not legally reviewed or signed. Have qualified counsel review before use.</Note>
      </Panel>
    </>
  );
}
