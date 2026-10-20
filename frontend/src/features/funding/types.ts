export interface OtpChallenge {
  instructions: string;
  expires_at: string | number;
  action_hash: string;
}

export interface ApproveResult {
  ok: boolean;
  error?: string;
}

export interface TamperResult {
  ok: boolean;
  offending: string[];
}

export interface DoubleFinancingResult {
  blocked: boolean;
  message?: string;
}

export interface ScheduleScenario {
  scenario: "on_time" | "late_30" | "default";
  total_cost_usd: number;
  rebate_to_sme_usd: number | null;
  sme_pays_factor_usd: number | null;
  credit_loss_borne_by: string;
}

export interface FundingScheduleView {
  label: string;
  schedule: { drawdown_date: string; expected_settlement_date: string; days_financed: number };
  expected_cost_usd: number;
  scenarios: ScheduleScenario[];
  assumptions: string[];
}

export interface LenderQuote {
  provider_id: string;
  quote_id: string;
  principal_usd: string;
  total_cost_usd: string;
  expires_at: string;
  status: string;
  source_type: "simulated" | "provider_issued";
  environment: string;
  label: string;
}

export interface LenderQuotes {
  adapter: { provider_id: string; environment: string } | null;
  quotes: LenderQuote[];
  notice: string;
}
