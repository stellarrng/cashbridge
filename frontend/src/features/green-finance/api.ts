import { get, post } from "@/shared/api/client";

export interface GreenProject {
  project_id: string;
  name: string;
  activity_name: string;
  project_cost_usd: number;
  requested_loan_usd: number;
  illustrative_annual_impact_tco2e: number | null;
  documentation_completeness_pct: number;
  review_status: string;
  evidence: Array<{ label: string; status: string }>;
}

export interface GreenEconomics {
  estimated_net_savings_usd_per_year: number;
  simple_payback_years: number | null;
  limitation: string;
}

export const fetchGreenProjects = () => get<{ projects: GreenProject[] }>("/api/green-finance");
export const fetchEconomics = (projectId: string) =>
  post<GreenEconomics>("/api/green-finance/economics", { project_id: projectId, electricity_price_usd_per_kwh: 0.12, annual_opex_usd: 1500 });
export const requestReview = (projectId: string) => post<unknown>("/api/green-finance/request-review", { project_id: projectId });

/** One way of paying for the project, against the 13-week cash buffer. */
export interface CashImpactScenario {
  min_closing_usd: number;
  weeks_below_buffer: number[];
  extra_funding_to_hold_buffer_usd: number | null;
  monthly_instalment_usd?: number | null;
  financed_pct?: number;
}

export interface GreenCashImpact {
  capex_week: number;
  buffer_usd: number;
  weekly_net_saving_usd: number;
  loan_apr_pct: number;
  without_project: CashImpactScenario;
  cash_funded: CashImpactScenario;
  loan_funded: CashImpactScenario & { financed_pct: number };
  limitation: string;
}

/** Estimate only: not a certification or a lending decision. */
export const fetchCashImpact = (projectId: string) =>
  post<GreenCashImpact>("/api/green-finance/cash-impact", { project_id: projectId, capex_week: 3, financed_pct: 80, tenor_months: 36 });
