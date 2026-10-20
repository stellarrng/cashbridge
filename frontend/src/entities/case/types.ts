import type { AutopilotRun } from "../autopilot";
import type { Forecast, ScenarioControl } from "../forecast";
import type { FundingOption, LenderReview, Pack } from "../funding";

/** The read model behind every SME screen: GET /api/snapshot. The browser renders it and never recomputes it. */
export interface CaseMeta {
  mode: string;
  synthetic: boolean;
  company: string;
  case_id: string;
  case_state: string;
  as_of: string;
  fx_note: string;
  last_error: string | null;
  director_alerts_open?: number;
  model_update_pending?: boolean;
}

export interface Kpis {
  cash_today_usd: number;
  cash_today_vnd: number;
  ccc: { dio: number; dso: number; dpo: number; ccc: number };
  first_shortfall_week: number | null;
  shortfall_usd: number;
  blocked_fraud_count: number;
}

export interface ReconciliationRow {
  txn_id: string;
  date: string;
  amount: number;
  currency: string;
  reference: string;
  matched_invoices: string[];
  gap: number;
  gap_reason?: string;
  confidence: number;
  status: string;
  reason?: string;
}

export interface FeaturedWire {
  txn_id: string;
  received: number;
  invoices: Array<{ id: string; amount: number }>;
  invoice_total: number;
  gap: number;
  gap_reason: string;
  explanation: string;
}

export interface InvoiceVerification {
  invoice_id: string;
  buyer: string;
  amount: number;
  currency: string;
  due_date: string;
  status: string;
  differences: string[];
  registry_status: string;
  tax_id_valid: boolean;
}

export interface HeldEmail {
  id: string;
  type: string;
  severity: string;
  sender: string;
  subject: string;
  reasons: string[];
  action_hint?: string;
}

export interface ScannedDocument {
  doc_id: string;
  doc_type: string;
  invoice_no: string;
  status: string;
  min_confidence: number;
  reason: string | null;
  matches_record: boolean;
  differences: string[];
}

export interface BuyerRisk {
  buyer: string;
  buyer_id: string;
  share_of_receivables_pct: number;
  avg_days_late: number;
  p_on_time: number;
  concentration_alert: boolean;
  has_history: boolean;
}

export interface AuditLine {
  seq: number;
  time: string;
  agent: string;
  tool: string;
  tier: string;
  decision: string;
  reason: string;
}

export interface RegistryBlock {
  block_index: number;
  block_hash: string;
  lender_ref?: string;
}

export interface ChatCitation {
  label?: string;
  source_id?: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | string;
  text: string;
  citations?: ChatCitation[];
}

export interface CaseSnapshot {
  meta: CaseMeta;
  kpis: Kpis;
  forecast: Forecast;
  scenario_controls: Record<string, ScenarioControl>;
  reconciliation: { rows: ReconciliationRow[]; featured_wire: FeaturedWire | null };
  verification: InvoiceVerification[];
  alerts: HeldEmail[];
  funding_options: FundingOption[];
  selected_option_id: string | null;
  pack: Pack;
  scans: ScannedDocument[];
  buyer_risk: BuyerRisk[];
  risk_model: { method: string; on_time_definition: string; training_rows: number };
  evidence: { chain_ok: boolean; broken_seq: number | null; lines_checked: number; audit_tail: AuditLine[]; registry_blocks: RegistryBlock[] };
  pii_inspector: { before: string; after: string; note: string };
  chat: { history: ChatMessage[] };
  autopilot: AutopilotRun | null;
  lender_review: LenderReview;
}
