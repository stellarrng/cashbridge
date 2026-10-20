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
