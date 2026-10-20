import { get, post } from "@/shared/api/client";
import type { Forecast, ScenarioDelta } from "@/entities/forecast";

export interface SimulationResult {
  forecast: Forecast;
  delta: ScenarioDelta;
}

export const simulate = (params: Record<string, number>) => post<SimulationResult>("/api/simulate", { params });

/** v9 receipts timing (censoring-aware Kaplan-Meier) next to the conservative base plan, with a split-conformal 80% band. */
export interface ReceiptsOutlook {
  weeks: number[];
  base_receipts: number[];
  v9_expected_receipts: number[];
  v9_band_80: Array<[number, number] | null>;
  after_horizon_usd: number;
  backtest: Record<string, { wape: number }> | null;
  interval_coverage: { split_conformal?: number; aci?: number } | null;
  note: string;
}

export const fetchReceiptsOutlook = () => get<ReceiptsOutlook>("/api/forecast/receipts-outlook");
