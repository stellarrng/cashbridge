import { get } from "@/shared/api/client";

export interface PublicOverview {
  company: string;
  kpis: { first_shortfall_week: number | null; shortfall_usd: number };
  weeks: Array<{ closing: number }>;
  bridge: BridgeView | null;
  robustness?: Robustness;
}

export interface BridgeView {
  amount_usd: number;
  apr_pct: number;
  funding_week: number;
  trough_week: number;
  residual_gap_usd: number;
  closing_after: number[];
}

export interface Robustness {
  single_pack_p: number;
  core_p: number;
  core_packs?: number;
}

export interface TrustSummary {
  summary: {
    security: { passed: number; total: number };
    agent: { passed: number; total: number };
    model: { brier_model: number; brier_baseline: number };
  };
}

export const fetchPublicOverview = () => get<PublicOverview>("/api/public/overview", { anonymous: true });
export const fetchTrustSummary = () => get<TrustSummary>("/api/trust/scorecard", { anonymous: true });
