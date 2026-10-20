import { post } from "@/shared/api/client";

export interface BidAssessment {
  initial_funding_gap_usd: number;
  stress_gap_if_advance_delayed_and_cost_overruns_usd: number;
  estimated_margin_pct: number;
  workforce_readiness: { uncovered_team_hours: number; indicative_outsourcing_cost_usd: number };
  limitations?: string[];
}

export const assessBid = (data: Record<string, number>) => post<BidAssessment>("/api/projects/assess", { data });
