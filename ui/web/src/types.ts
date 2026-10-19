// Mirrors docs/UI_CONTRACT.md (section C.2). Extra keys are allowed by the contract; these are the ones the UI reads.

export type WeekStatus = "ok" | "at_risk" | "shortfall";

export interface Meta {
  mode: "offline-demo" | "live-llm";
  synthetic: boolean;
  company: string;
  case_id: string;
  case_state: string;
  as_of: string;
  fx_note: string;
  last_error: string | null;
}

export interface Kpis {
  cash_today_usd: number;
  cash_today_vnd: number;
  ccc: { dio: number; dso: number; dpo: number; ccc: number };
  first_shortfall_week: number | null;
  shortfall_usd: number | null;
  blocked_fraud_count: number;
}

export interface WeekRow {
  week: number;
  start_date: string;
  opening: number;
  inflows: number;
  outflows: number;
  closing: number;
  status: WeekStatus;
}

export interface Attribution {
  driver: string;
  amount_usd: number;
  source_ref: string;
}

export interface ForecastBlock {
  buffer_usd: number;
  weeks: WeekRow[];
  attribution: Attribution[];
}

export interface Control {
  min: number;
  max: number;
  step: number;
  default: number;
}

export type ScenarioKey = "dso_change_days" | "deposit_pct" | "tariff_shared_pct" | "fx_change_pct";
export type ScenarioParams = Record<ScenarioKey, number>;

export interface ReconRow {
  txn_id: string;
  date: string;
  amount: number;
  currency: string;
  reference: string;
  tier: number | null;
  matched_invoices: string[];
  gap: number | null;
  gap_reason: string | null;
  confidence: number;
  status: string;
  reason?: string;
}

export interface FeaturedWire {
  txn_id: string;
  received: number;
  invoices: { id: string; amount: number }[];
  invoice_total: number;
  gap: number;
  gap_reason: string;
  explanation: string;
}

export interface VerificationRow {
  invoice_id: string;
  buyer: string;
  amount: number;
  currency: string;
  due_date: string;
  status: "ELIGIBLE" | "FLAGGED" | "BLOCKED";
  differences: string[];
  registry_status: string;
  tax_id_valid: boolean;
}

export interface Alert {
  id: string;
  type: string;
  severity: string;
  sender: string;
  subject: string;
  reasons: string[];
  action_hint: string;
}

export interface FundingOption {
  rank: number | null;
  id: string;
  name: string;
  type: string;
  amount_usd: number | null;
  apr_pct: number | null;
  eligible: boolean;
  ineligible_reason: string | null;
  cost_breakdown: Record<string, number>;
  assumptions: Record<string, number | string>;
  formula: string | null;
  why_not_cheaper: string | null;
}

export interface LockedMetric {
  key: string;
  label: string;
  value: number;
  unit: string;
}

export interface Pack {
  status: "NOT_STARTED" | "AWAITING_APPROVAL" | "SUBMITTED" | string;
  pack_id: string | null;
  locked_metrics: LockedMetric[];
  letter_text: string | null;
  number_check: { ok: boolean; offending: string[] } | null;
  action_hash: string | null;
  pdf_path: string | null;
  lender_ref: string | null;
  registry_block: Record<string, string | number> | null;
}

export interface TierRow {
  seq: number;
  time: string;
  agent: string;
  tool: string;
  tier: string;
  decision: string;
  reason: string;
}

export interface ChatMessage {
  role: "assistant" | "user";
  text: string;
  citations: { label: string; source_id: string }[];
  mode: string;
}

export interface Collections {
  schedule: { invoice_id: string; buyer: string; stage: string; due_offset_days: number; scheduled_date: string; status: string }[];
  promises: { invoice_id: string; buyer: string; promised_date: string; source_text: string }[];
}

export interface Evidence {
  chain_ok: boolean;
  broken_seq: number | null;
  lines_checked: number;
  audit_tail: TierRow[];
  registry_blocks: Record<string, string | number>[];
  eval: null | { passed: number; total: number; baseline?: string; rows: { task: string; cashbridge_pass: boolean; baseline_pass: boolean | null; invented_numbers: number }[] };
}

export interface ScanRow {
  doc_id: string;
  doc_type: string;
  invoice_no: string;
  status: "READ" | "NEEDS_HUMAN";
  min_confidence: number;
  reason: string | null;
  matches_record: boolean | null;
  differences: string[];
  low_fields: { name: string; value: string | null; confidence: number; page: number | null }[];
  fields_read: number;
  three_way?: string;
}

export interface Snapshot {
  meta: Meta;
  kpis: Kpis;
  forecast: ForecastBlock;
  scenario_controls: Record<ScenarioKey, Control>;
  reconciliation: { rows: ReconRow[]; featured_wire: FeaturedWire | null };
  verification: VerificationRow[];
  scans: ScanRow[];
  alerts: Alert[];
  funding_options: FundingOption[];
  selected_option_id: string | null;
  pack: Pack;
  tier_monitor: TierRow[];
  pii_inspector: { before: string; after: string; note?: string };
  chat: { history: ChatMessage[] };
  collections: Collections;
  buyer_risk: {
    buyer: string; buyer_id: string; share_of_receivables_pct: number; avg_days_late: number; p_on_time: number;
    concentration_alert: boolean; has_history: boolean;
  }[];
  risk_model: {
    method: string; on_time_definition: string; training_rows: number; on_time_rate_pct: number; intercept: number;
    coefficients: { name: string; coefficient: number }[];
  };
  evidence: Evidence;
}

export interface SimulateResult {
  forecast: ForecastBlock;
  kpis: Kpis;
  delta: {
    first_shortfall_week_before: number | null;
    first_shortfall_week_after: number | null;
    min_closing_before_usd: number;
    min_closing_after_usd: number;
  };
}

export type OtpError = "invalid_code" | "expired" | "replayed" | "payload_mismatch" | "DoubleFinancingBlocked" | string;

export interface ApproveResult {
  ok: boolean;
  error: OtpError | null;
  snapshot: Snapshot;
}

export interface OtpChallenge {
  action_hash: string;
  expires_at: string;
  instructions: string;
}
