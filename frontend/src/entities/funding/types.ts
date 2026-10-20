export interface CostBreakdown {
  fee_usd?: number | null;
  interest_usd?: number | null;
  total_usd: number | null;
}

export interface FundingOption {
  rank?: number;
  id: string;
  name: string;
  type: string;
  amount_usd: number | null;
  apr_pct: number | null;
  eligible: boolean;
  ineligible_reason: string | null;
  cost_breakdown: CostBreakdown;
  why_not_cheaper?: string;
}

export interface LockedMetric {
  /** Stable id of the figure (used to open its provenance). */
  key: string;
  label: string;
  value: number | string;
  unit: string;
}

export interface Pack {
  status: string;
  pack_id: string | null;
  locked_metrics: LockedMetric[];
  letter_text: string | null;
  action_hash: string | null;
  prepared_by: string | null;
  approved_by: string | null;
}

export interface LenderHistoryEntry {
  event: string;
  by?: string | null;
  note?: string | null;
}

export interface LenderReview {
  status: string;
  decision: string | null;
  note: string | null;
  reviewer: string | null;
  history: LenderHistoryEntry[];
  verification?: PackVerification | null;
}

export interface VerificationCheck {
  check: string;
  /** true = passed, false = failed, null = cannot be checked here. */
  ok: boolean | null;
  detail?: string;
}

export interface PackVerification {
  checks: VerificationCheck[];
}
