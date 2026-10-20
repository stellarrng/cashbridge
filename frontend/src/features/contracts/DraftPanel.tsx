import { useState, type FormEvent, type ReactNode } from "react";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { Button, Note, Panel } from "@/shared/ui";
import { ContractPreview } from "./ContractPreview";
import { downloadDraftDocx, draftContract, type ContractKind, type DraftInput, type DraftResult, type MilestoneInput, type PartyInput } from "./api";

const INCOTERMS = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF"];
const INSTITUTIONS = ["VIAC", "SIAC", "HKIAC", "CIETAC"];
const CURRENCIES = ["USD", "EUR", "CNY", "JPY", "VND"];
const STANDARD: Record<ContractKind, MilestoneInput[]> = {
  supply: [{ event: "Advance payment after signing", percentage: 30 }, { event: "Payment against shipping documents", percentage: 70 }],
  services: [{ event: "Advance payment after signing", percentage: 30 }, { event: "Payment on delivery of the deliverables", percentage: 40 },
    { event: "Payment after written acceptance", percentage: 30 }],
  construction: [{ event: "Advance payment against an advance-payment guarantee", percentage: 15 }, { event: "Progress payments on certified work", percentage: 70 },
    { event: "Payment on taking-over of the works", percentage: 10 }, { event: "Release of retention after the defects-liability period", percentage: 5 }],
};

const party = (p: Partial<PartyInput>): PartyInput => ({ name: "", address: "", tax_id: "", representative: "", title: "", email: "", phone: "", ...p });

// Synthetic sample parties (no real company); kept between visits like the review panel.
const initial = (lang: string): DraftInput => ({
  contract_type: "supply", language: lang === "vi" ? "bilingual" : "en", prevailing_language: "en",
  contract_no: "", contract_date: new Date().toISOString().slice(0, 10), place_of_signing: "Ho Chi Minh City",
  supplier: party({ name: "Binh Duong Timberworks Co., Ltd (synthetic)", address: "Lot C3, VSIP II, Binh Duong, Vietnam", tax_id: "3700000000",
    representative: "Nguyen Van An", title: "Director", email: "sales@timberworks.example", phone: "+84 274 000 0000" }),
  customer: party({ name: "Northern Retail LLC (synthetic)", address: "100 Harbor Street, Seattle, WA, USA", representative: "Emma Clark",
    title: "Purchasing Director", email: "purchasing@northern.example" }),
  scope: "400 solid-oak dining tables, model BD-T180\n1,600 matching chairs, model BD-C45", currency: "USD", amount: 200000, vat_pct: "",
  milestones: null, payment_days: "30", late_interest_pct: "", incoterm: "FOB", incoterm_place: "Cat Lai Port, Ho Chi Minh City",
  delivery_date: "", start_date: "", end_date: "", site: "", completion_date: "", retention_pct: "", performance_security_pct: "",
  defects_months: "", acceptance_days: "", warranty_months: "", liability_cap_pct: "", governing_law: "", dispute: "arbitration",
  arbitration_institution: "VIAC",
});
let kept: DraftInput | null = null;

function Group({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className="cform">
      <legend>{legend}</legend>
      <div className="inputs">{children}</div>
    </fieldset>
  );
}

export function DraftPanel() {
  const { t, lang } = useI18n();
  const act = useAct();
  const [v, setV] = useState<DraftInput>(() => kept ?? initial(lang));
  const [result, setResult] = useState<DraftResult | null>(null);
  const set = (patch: Partial<DraftInput>) => setV((cur) => (kept = { ...cur, ...patch }));
  const setParty = (who: "supplier" | "customer", patch: Partial<PartyInput>) => setV((cur) => (kept = { ...cur, [who]: { ...cur[who], ...patch } }));
  const ms = v.milestones;
  const msTotal = (ms || []).reduce((s, m) => s + (Number(m.percentage) || 0), 0);

  const text = (label: string, key: keyof DraftInput, type = "text", extra: Record<string, unknown> = {}) => (
    <label className="field">{label}
      <input type={type} value={String(v[key] ?? "")} onChange={(e) => set({ [key]: type === "number" && key === "amount" ? Number(e.target.value) : e.target.value } as Partial<DraftInput>)} {...extra} />
    </label>
  );
  const partyFields = (who: "supplier" | "customer") => (
    <>
      {(["name", "address", "tax_id", "representative", "title", "email", "phone"] as const).map((k) => (
        <label key={k} className="field">{t(`ctr.d.p.${k}`)}
          <input type={k === "email" ? "email" : "text"} value={v[who][k]} required={k === "name"} onChange={(e) => setParty(who, { [k]: e.target.value })} />
        </label>
      ))}
    </>
  );

  async function generate(e: FormEvent) {
    e.preventDefault();
    const r = await act(() => draftContract(v), (out) => t("ctr.d.done", { n: out.document.articles.length, open: out.open_items.length }));
    if (r) setResult(r);
  }

  return (
    <Panel title="2" sub={t("ctr.d.sub")}>
      <form onSubmit={generate} id="draftForm">
        <Group legend={t("ctr.d.g.basics")}>
          <label className="field">{t("ctr.d.type")}
            <select id="draftType" value={v.contract_type} onChange={(e) => set({ contract_type: e.target.value as ContractKind, milestones: null })}>
              {(["supply", "services", "construction"] as const).map((k) => <option key={k} value={k}>{t(`ctr.d.kind.${k}`)}</option>)}
            </select>
          </label>
          <label className="field">{t("ctr.d.lang")}
            <select id="draftLang" value={v.language} onChange={(e) => set({ language: e.target.value as DraftInput["language"] })}>
              <option value="en">English</option><option value="vi">Tiếng Việt</option><option value="bilingual">{t("ctr.d.bilingual")}</option>
            </select>
          </label>
          {v.language === "bilingual" && (
            <label className="field">{t("ctr.d.prevailing")}
              <select value={v.prevailing_language} onChange={(e) => set({ prevailing_language: e.target.value as "en" | "vi" })}>
                <option value="en">English</option><option value="vi">Tiếng Việt</option>
              </select>
            </label>
          )}
          {text(t("ctr.d.no"), "contract_no", "text", { placeholder: t("ctr.d.auto") })}
          {text(t("ctr.d.date"), "contract_date", "date")}
          {text(t("ctr.d.place"), "place_of_signing")}
        </Group>

        <div className="cform-cols">
          <Group legend={t("ctr.d.g.partyA")}>{partyFields("supplier")}</Group>
          <Group legend={t("ctr.d.g.partyB")}>{partyFields("customer")}</Group>
        </div>

        <Group legend={t("ctr.d.g.scope")}>
          <label className="field span-all">{t("ctr.d.scope")}
            <textarea rows={3} value={v.scope} required onChange={(e) => set({ scope: e.target.value })} />
          </label>
          {v.contract_type === "supply" && (
            <>
              <label className="field">Incoterms® 2020
                <select value={v.incoterm} onChange={(e) => set({ incoterm: e.target.value })}>{INCOTERMS.map((x) => <option key={x}>{x}</option>)}</select>
              </label>
              {text(t("ctr.d.namedPlace"), "incoterm_place")}
              {text(t("ctr.d.delivery"), "delivery_date", "date")}
            </>
          )}
          {v.contract_type === "services" && (<>{text(t("ctr.d.start"), "start_date", "date")}{text(t("ctr.d.end"), "end_date", "date")}</>)}
          {v.contract_type === "construction" && (
            <>
              {text(t("ctr.d.site"), "site")}
              {text(t("ctr.d.completion"), "completion_date", "date")}
              {text(t("ctr.d.retention"), "retention_pct", "number", { min: 0, max: 10, step: "0.5", placeholder: "5" })}
              {text(t("ctr.d.perfSec"), "performance_security_pct", "number", { min: 0, max: 30, placeholder: "10" })}
              {text(t("ctr.d.defects"), "defects_months", "number", { min: 0, max: 60, placeholder: "12" })}
            </>
          )}
        </Group>

        <Group legend={t("ctr.d.g.price")}>
          <label className="field">{t("ctr.d.currency")}
            <select value={v.currency} onChange={(e) => set({ currency: e.target.value })}>{CURRENCIES.map((x) => <option key={x}>{x}</option>)}</select>
          </label>
          {text(t("ctr.d.amount"), "amount", "number", { min: 0.01, step: "0.01", required: true })}
          {text(t("ctr.d.vat"), "vat_pct", "number", { min: 0, max: 30, placeholder: t("ctr.d.byLaw") })}
          {text(t("ctr.d.payDays"), "payment_days", "number", { min: 0, max: 180, placeholder: "30" })}
          {text(t("ctr.d.interest"), "late_interest_pct", "number", { min: 0, max: 30, step: "0.5", placeholder: "10" })}
          <div className="span-all">
            <label className="check">
              <input type="checkbox" checked={ms === null} onChange={(e) => set({ milestones: e.target.checked ? null : STANDARD[v.contract_type].map((m) => ({ ...m })) })} />
              {t("ctr.d.standardSchedule")}
            </label>
            {ms === null ? (
              <p className="muted small">{STANDARD[v.contract_type].map((m) => `${m.percentage}% ${m.event}`).join(" · ")}</p>
            ) : (
              <div className="ms-edit">
                {ms.map((m, i) => (
                  <div className="row" key={i}>
                    <input aria-label={t("ctr.d.msEvent", { n: i + 1 })} value={m.event} onChange={(e) => set({ milestones: ms.map((x, j) => (j === i ? { ...x, event: e.target.value } : x)) })} />
                    <input aria-label={t("ctr.d.msPct", { n: i + 1 })} type="number" min={0.01} max={100} step="0.01" value={m.percentage}
                      onChange={(e) => set({ milestones: ms.map((x, j) => (j === i ? { ...x, percentage: Number(e.target.value) } : x)) })} />
                    <Button small variant="ghost" aria-label={t("ctr.d.msRemove", { n: i + 1 })} disabled={ms.length < 2} onClick={() => set({ milestones: ms.filter((_, j) => j !== i) })}>×</Button>
                  </div>
                ))}
                <div className="row">
                  <Button small variant="ghost" disabled={ms.length >= 8} onClick={() => set({ milestones: [...ms, { event: "", percentage: Math.max(0, 100 - msTotal) }] })}>{t("ctr.d.msAdd")}</Button>
                  <span className={Math.abs(msTotal - 100) < 0.001 ? "pill pos" : "pill neg"} role="status">{t("ctr.d.msTotal", { n: Math.round(msTotal * 100) / 100 })}</span>
                </div>
              </div>
            )}
          </div>
        </Group>

        <Group legend={t("ctr.d.g.legal")}>
          {text(t("ctr.d.acceptance"), "acceptance_days", "number", { min: 1, max: 90, placeholder: "10" })}
          {v.contract_type !== "construction" && text(t("ctr.d.warranty"), "warranty_months", "number", { min: 0, max: 120, placeholder: "12" })}
          {text(t("ctr.d.cap"), "liability_cap_pct", "number", { min: 10, max: 500, placeholder: "100" })}
          {text(t("ctr.d.law"), "governing_law", "text", { placeholder: "the laws of the Socialist Republic of Vietnam" })}
          <label className="field">{t("ctr.d.dispute")}
            <select value={v.dispute} onChange={(e) => set({ dispute: e.target.value as DraftInput["dispute"] })}>
              <option value="arbitration">{t("ctr.d.arbitration")}</option><option value="courts">{t("ctr.d.courts")}</option>
            </select>
          </label>
          {v.dispute === "arbitration" && (
            <label className="field">{t("ctr.d.institution")}
              <select value={v.arbitration_institution} onChange={(e) => set({ arbitration_institution: e.target.value })}>{INSTITUTIONS.map((x) => <option key={x}>{x}</option>)}</select>
            </label>
          )}
        </Group>
        <Note>{t("ctr.d.defaultsNote")}</Note>
        <div className="row mt-2">
          <Button variant="bridge" type="submit" id="draftGenerate">{t("ctr.d.generate")}</Button>
          <Button variant="ghost" id="draftDocx" onClick={() => void act(() => downloadDraftDocx(v, result?.contract_no), t("ctr.d.downloaded"))}>{t("ctr.d.word")}</Button>
        </div>
      </form>

      {result && (
        <div className="mt-3" id="draftResult">
          {result.open_items.length > 0 && (
            <div className="cp-open" role="note">
              <b>{t("ctr.d.openTitle", { n: result.open_items.length })}</b>
              <ul>
                {result.document.open_items_detail.map((o, i) => (
                  <li key={i} className={o.kind}>{t(o.kind === "missing" ? "ctr.d.openMissing" : "ctr.d.openDefault")}: {lang === "vi" ? o.vi : o.en}</li>
                ))}
              </ul>
            </div>
          )}
          <ContractPreview doc={result.document} lang={result.language} />
        </div>
      )}
      <Note>{t("ctr.d.legalNote")}</Note>
    </Panel>
  );
}
