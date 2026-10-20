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

export interface DraftInput {
  contract_type: string;
  supplier: string;
  customer: string;
  amount: number;
  scope: string;
  governing_law: string;
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
export const draftContract = (data: DraftInput) => post<{ draft: string }>("/api/contracts/draft", { data });
export const downloadDraftDocx = (data: DraftInput) => download("/api/contracts/draft-docx", "CashBridge_UNSIGNED_DRAFT.docx", { method: "POST", body: { data } });
