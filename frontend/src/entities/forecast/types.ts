export type WeekStatus = "ok" | "at_risk" | "shortfall";

export interface ForecastWeek {
  week: number;
  start_date?: string;
  opening?: number;
  inflows: number;
  outflows: number;
  closing: number;
  status: WeekStatus;
}

export interface Attribution {
  driver: string;
  amount_usd: number;
  source_ref: string;
}

export interface ScenarioControl {
  min: number;
  max: number;
  step: number;
  default: number;
}

export interface Forecast {
  buffer_usd: number;
  weeks: ForecastWeek[];
  attribution: Attribution[];
}

export interface ScenarioDelta {
  first_shortfall_week_before: number | null;
  first_shortfall_week_after: number | null;
  min_closing_before_usd: number;
  min_closing_after_usd: number;
}
