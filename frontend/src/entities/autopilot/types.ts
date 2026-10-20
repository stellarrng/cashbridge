import type { EvidenceStatus } from "../status";

export interface EvidenceEntry {
  id: string;
  claim: string;
  value: number | string;
  status: EvidenceStatus | string;
  source: string;
  note?: string;
}

export interface AutopilotStep {
  n: number;
  tool: string;
  why: string;
  result: string;
  status: string;
  evidence: string[];
}

export interface CoverageWeek {
  week: number;
  closing_before: number;
  closing_after: number;
}

export interface Recommendation {
  option_id: string;
  option_name: string;
  amount_usd: number;
  apr_pct: number;
  total_cost_usd: number;
  why: string[];
  conditions: string[];
  what_would_change: string[];
  coverage?: { weeks: CoverageWeek[]; assumptions: Array<string | null> };
  core_plan?: unknown;
}

export interface AutopilotRun {
  run_id: string;
  planner: string;
  mode: string;
  decision: string;
  goal: string;
  goal_injection_detected: boolean;
  steps: AutopilotStep[];
  evidence: EvidenceEntry[];
  evidence_counts: Partial<Record<string, number>>;
  refused_proposals: Array<{ proposed: string; reason: string }>;
  recommendation: Recommendation | null;
  human_handoff: { who: string; action: string; why: string };
  guardrails: string[];
}
