import { get, post } from "@/shared/api/client";
import type { AnalyticsSummary, ScenarioResult } from "./types";

export const fetchSummary = () => get<AnalyticsSummary>("/api/analytics/summary");
export const runScenario = (data: Record<string, number>) => post<ScenarioResult>("/api/analytics/scenario", { data });
