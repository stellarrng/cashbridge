import { get, post } from "@/shared/api/client";

export interface Scorecard {
  generated_at: string;
  summary: {
    security: { passed: number; total: number };
    agent: { passed: number; total: number };
    model: { brier_model: number; brier_baseline: number };
  };
  security: Array<{ id: string; title: string; passed: boolean }>;
  agent: Array<{ id: string; title: string; passed: boolean; got?: string }>;
  model: { caveat: string };
}

export interface ChainCheck {
  ok: boolean;
  lines_checked: number;
  broken_seq: number | null;
}

/** Public: the scorecard is the same for the SME and the lender, and is shown before sign-in on the landing page. */
export const fetchScorecard = () => get<Scorecard>("/api/trust/scorecard", { anonymous: true });
export const verifyChain = () => post<ChainCheck>("/api/verify_chain");
export const tamperDemo = () => post<ChainCheck>("/api/tamper_demo");
