import { post } from "@/shared/api/client";
import type { Forecast, ScenarioDelta } from "@/entities/forecast";

export interface SimulationResult {
  forecast: Forecast;
  delta: ScenarioDelta;
}

export const simulate = (params: Record<string, number>) => post<SimulationResult>("/api/simulate", { params });
