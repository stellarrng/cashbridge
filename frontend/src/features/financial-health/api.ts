import { get, post } from "@/shared/api/client";
import type { AnalyticsSummary, ScenarioResult } from "./types";

export const fetchSummary = () => get<AnalyticsSummary>("/api/analytics/summary");
export const runScenario = (data: Record<string, number>) => post<ScenarioResult>("/api/analytics/scenario", { data });

/** Screening hint from DSO, DIO and gross margin, validated on public Polish company data. Not a credit decision. */
export interface DistressSignal {
  p_distress_1y: number;
  features: Record<string, number>;
  feature_labels: Record<string, string>;
  contributions_log_odds: Record<string, number>;
  outside_training_range: string[];
  trained_on: string;
  source: string;
  limitations: string[];
}

export const fetchDistress = () => get<DistressSignal>("/api/analytics/distress-signal");
