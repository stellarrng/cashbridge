export interface CapitalPlanInput {
  available_cash_usd: number;
  minimum_reserve_usd: number;
  working_capital_usd: number;
  marketing_usd: number;
  green_investment_usd: number;
}
export interface CapitalPlanResult {
  synthetic: boolean;
  deployable_cash_usd: number;
  planned_spend_usd: number;
  funding_gap_usd: number;
  remaining_headroom_usd: number;
  gap_if_marketing_deferred_usd: number;
  potential_gap_reduction_usd: number;
  breakdown_usd: { working_capital: number; marketing: number; green_investment: number };
  notes: string[];
}

export interface GreenFinanceResponse {
  synthetic: boolean;
  notice: string;
  projects: Array<{
    project_id: string; name: string; activity_name: string;
    requested_loan_usd: number; documentation_completeness_pct: number;
    illustrative_annual_impact_tco2e: number | null; impact_basis: string;
    review_status: string; issues: string[];
    evidence: Array<{id: string; label: string; status: string}>;
  }>;
}

import type { ApproveResult, ChatMessage, OtpChallenge, ScenarioParams, SimulateResult, Snapshot } from "./types";

// One function per method in the UI contract (docs/UI_CONTRACT.md, C.1). No logic lives here.
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const isGet = ["/api/snapshot", "/api/green-finance", "/api/analytics/summary", "/api/bank/review"].includes(path);
  const response = await fetch(path, {
    method: isGet ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: isGet ? undefined : JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      /* keep the status text */
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  evaluateCapitalPlan: (plan: CapitalPlanInput) => request<CapitalPlanResult>("/api/capital-plan", plan),
  getSnapshot: () => request<Snapshot>("/api/snapshot"),
  getGreenFinance: () => request<GreenFinanceResponse>("/api/green-finance"),
  requestGreenReview: (project_id: string) => request<GreenFinanceResponse>("/api/green-finance/request-review", {project_id}),
  simulate: (params: ScenarioParams) => request<SimulateResult>("/api/simulate", { params }),
  askCfo: (text: string) => request<ChatMessage>("/api/ask_cfo", { text }),
  chooseOption: (option_id: string) => request<Snapshot>("/api/choose_option", { option_id }),
  preparePack: () => request<Snapshot>("/api/prepare_pack"),
  requestOtp: () => request<OtpChallenge>("/api/request_otp"),
  approve: (code: string) => request<ApproveResult>("/api/approve", { code }),
  retryDoubleFinancing: () => request<{ blocked: boolean; error: string | null; message: string }>("/api/retry_double_financing"),
  tamperDraft: () => request<{ ok: boolean; offending: string[]; message: string }>("/api/tamper_draft"),
  verifyChain: () => request<{ ok: boolean; broken_seq: number | null; lines_checked: number }>("/api/verify_chain"),
  tamperDemo: () => request<{ ok: boolean; broken_seq: number | null; lines_checked: number; note: string }>("/api/tamper_demo"),
  resetDemo: () => request<Snapshot>("/api/reset_demo"),
};

export interface FinancialOverview {
  synthetic: boolean; source_id: string; currency: string;
  ratios: Record<string, number | null>;
  highlights: Record<string, number | null>;
  eda: {
    monthly: Array<{month: string; revenue: number; expenses: number; marketing: number; payroll: number; supplier: number}>;
    median_monthly_expenses_usd: number | null;
    min_monthly_revenue_usd: number | null;
    max_monthly_revenue_usd: number | null;
    expense_outliers: Array<{month: string; type: string; z_score: number}>;
  };
  definitions: Record<string,string>;
}
export interface FundingScenario {
  synthetic: boolean; source_id: string; scenario: Record<string,number>;
  baseline_ending_cash_usd: number; scenario_ending_cash_usd: number;
  change_vs_baseline_usd: number; minimum_cash_usd: number; reserve_breach: boolean;
  additional_marketing_monthly_usd: number;
  schedule: Array<{month:number; inflows_usd:number; outflows_usd:number; closing_cash_usd:number}>;
  limitations: string[];
}
export interface ProjectReview {
  initial_funding_gap_usd: number; stress_gap_if_advance_delayed_and_cost_overruns_usd: number;
  estimated_profit_after_simple_financing_cost_usd: number; estimated_margin_pct: number;
  limitations: string[]; human_review_required: boolean;
  workforce_readiness: {uncovered_team_hours:number; indicative_outsourcing_cost_usd:number};
}
export interface ContractFlag { code: string; severity: string; description: string; evidence: string }
export interface ContractReview {
  status: string; risk_signal_count: number;
  extracted: { amounts_usd: number[]; payment_percentage_sum: number | null; invoice_ids: string[];
    payment_milestones: Array<{line: number; percentage: number; evidence: string}>; tax_ids: string[]; };
  flags: ContractFlag[]; limitations: string[];
}
export interface DraftContract {
  draft: string; status: string; review_checklist: string[];
  milestones: Array<{event:string; percentage:number; amount:number}>;
}
export interface ReconcileContract {
  contract_amounts_usd: number[]; invoice_amounts_usd: number[];
  invoice_ids: string[]; amount_mismatch: boolean; flags: ContractFlag[];
  status: string; limitations: string;
}
export interface BankReview {
  synthetic: boolean; bank_access: string; notice: string; case_id: string; case_state: string;
  financial_ratios: Record<string,number|null>;
  evidence: {audit_chain_ok: boolean; invoice_registry_blocks: number; document_review: ContractReview | null; source_id: string};
  funding_options: Snapshot["funding_options"];
  green_projects: GreenFinanceResponse["projects"];
  review_checklist: string[];
}
export const intelligence = {
  summary: () => request<FinancialOverview>("/api/analytics/summary"),
  scenario: (data: Record<string,number>) => request<FundingScenario>("/api/analytics/scenario",{data}),
  project: (data: Record<string,number>) => request<ProjectReview>("/api/projects/assess",{data}),
  review: (text: string, invoice_amount_usd?: number) => request<ContractReview>("/api/contracts/analyze",{text,invoice_amount_usd}),
  draft: (data: Record<string,unknown>) => request<DraftContract>("/api/contracts/draft",{data}),
  reconcile: (contract_text: string, invoice_text: string) => request<ReconcileContract>("/api/contracts/reconcile",{data:{contract_text,invoice_text}}),
  bank: async (token: string): Promise<BankReview> => {
    const response = await fetch('/api/bank/review', {
      headers: { Authorization: `Bearer ${token}` }, cache: 'no-store',
    });
    if (!response.ok) throw new ApiError(`Bank reviewer access denied (${response.status})`, response.status);
    return await response.json() as BankReview;
  },
  greenEconomics: (project_id:string, electricity_price_usd_per_kwh:number, annual_opex_usd:number) =>
    request<{annual_energy_savings_kwh:number; estimated_net_savings_usd_per_year:number; simple_payback_years:number|null; limitation:string}>
    ("/api/green-finance/economics",{project_id,electricity_price_usd_per_kwh,annual_opex_usd}),
  upload: async (file: File): Promise<{text:string;method:string; pages:number; notice:string}> => {
    const form = new FormData(); form.append("file",file);
    const res = await fetch("/api/contracts/extract-upload",{method:"POST",body:form});
    if (!res.ok) {const problem = await res.json(); throw new Error(typeof problem.detail === "string" ? problem.detail : `Upload failed (${res.status})`);}
    return await res.json();
  },
};
