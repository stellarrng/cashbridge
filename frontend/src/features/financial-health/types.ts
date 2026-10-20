export interface AnalyticsSummary {
  ratios: Record<string, number | null>;
  definitions: Record<string, string>;
  eda: {
    monthly: Array<{ month: string; revenue: number; expenses: number; marketing: number; payroll: number; supplier?: number }>;
    expense_outliers: Array<{ month: string }>;
  };
}

export interface ScenarioResult {
  baseline_ending_cash_usd: number;
  scenario_ending_cash_usd: number;
  minimum_cash_usd: number;
  reserve_breach: boolean;
  schedule?: Array<{ month: number; closing_cash_usd: number }>;
  limitations?: string[];
}
