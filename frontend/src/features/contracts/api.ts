import { download, post, request } from "@/shared/api/client";

export interface Flag {
  code: string;
  severity: string;
  description: string;
  evidence?: string;
}

export interface ContractAnalysis {
  risk_signal_count: number;
  extracted: { payment_percentage_sum: number | null; amounts_usd: number[] };
  flags: Flag[];
  limitations?: string[];
}

export interface ReconcileResult {
  contract_amounts_usd: number[];
  invoice_amounts_usd: number[];
  amount_mismatch: boolean;
  flags: Flag[];
  limitations: string;
}

export type ContractKind = "supply" | "services" | "construction";
export type ContractLang = "en" | "vi" | "bilingual";

export interface PartyInput {
  name: string;
  address: string;
  tax_id: string;
  representative: string;
  title: string;
  email: string;
  phone: string;
}

export interface MilestoneInput {
  event: string;
  percentage: number;
}

/** Everything the clause library takes. Empty strings are left out so the server applies (and lists) its defaults. */
export interface DraftInput {
  contract_type: ContractKind;
  language: ContractLang;
  prevailing_language: "en" | "vi";
  contract_no: string;
  contract_date: string;
  place_of_signing: string;
  supplier: PartyInput;
  customer: PartyInput;
  scope: string;
  currency: string;
  amount: number;
  vat_pct: string;
  milestones: MilestoneInput[] | null;
  payment_days: string;
  late_interest_pct: string;
  incoterm: string;
  incoterm_place: string;
  delivery_date: string;
  start_date: string;
  end_date: string;
  site: string;
  completion_date: string;
  retention_pct: string;
  performance_security_pct: string;
  defects_months: string;
  acceptance_days: string;
  warranty_months: string;
  liability_cap_pct: string;
  governing_law: string;
  dispute: "arbitration" | "courts";
  arbitration_institution: string;
}

export type Bi = { en: string; vi: string };
export interface ContractDocument {
  title: Bi;
  meta: Bi;
  notice: Bi;
  parties: { role: Bi; name: string; rows: [Bi, string][] }[];
  recitals: Bi[];
  articles: { no: number; title: Bi; clauses: { no: string; text: Bi }[] }[];
  schedules: { no: number; title: Bi; items?: Bi[]; table?: { header: Bi[]; rows: (string | Bi)[][]; total: (string | Bi)[] } }[];
  signatures: { role: Bi; name: string; person: string; title: string }[];
  open_items_detail: { kind: "missing" | "default"; en: string; vi: string }[];
  checklist: Bi[];
}

export interface DraftResult {
  draft: string;
  language: ContractLang;
  contract_no: string;
  document: ContractDocument;
  open_items: string[];
  milestones: { event: string; percentage: number; amount: number }[];
  status: string;
}

/** Drop empty optional fields so the server's documented defaults apply (and are listed as "to confirm"). */
export function cleanDraft(input: DraftInput): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(input)) {
    if (v === "" || v === null) continue;
    if (k === "supplier" || k === "customer") {
      out[k] = Object.fromEntries(Object.entries(v as PartyInput).filter(([, x]) => x !== ""));
    } else out[k] = v;
  }
  return out;
}

/** Text is read locally (PDF / image OCR on the server); nothing is sent to a model. */
export const extractUpload = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<{ text: string; method: string }>("/api/contracts/extract-upload", { method: "POST", body: form });
};
export const analyzeContract = (text: string) => post<ContractAnalysis>("/api/contracts/analyze", { text });
export const reconcileInvoice = (contractText: string, invoiceText: string) =>
  post<ReconcileResult>("/api/contracts/reconcile", { data: { contract_text: contractText, invoice_text: invoiceText } });
export const draftContract = (data: DraftInput) => post<DraftResult>("/api/contracts/draft", { data: cleanDraft(data) });
export const downloadDraftDocx = (data: DraftInput, contractNo?: string) =>
  download("/api/contracts/draft-docx", `${contractNo || "CashBridge"}_UNSIGNED_DRAFT.docx`, { method: "POST", body: { data: cleanDraft(data) } });
