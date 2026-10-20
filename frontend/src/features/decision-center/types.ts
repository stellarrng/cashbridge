/** Shapes of GET /api/intelligence and POST /api/intelligence/plan (the Intelligence Core). All figures are simulated. */

export interface PlanGoal {
  id: string;
  label?: string;
  floor?: string;
  min_probability: number;
}

export interface PlanAction {
  type: string;
  ref: string;
  week: number;
  amount_usd?: number;
  advance_usd?: number;
  new_pct?: number;
}

export interface RiskWithoutAction {
  p_no_negative_week: number;
  p_negative_by_week: number[];
  closing_p10_by_week: number[];
  shortfall_cvar95_usd?: number | null;
}

export interface ChosenPlan {
  plan_id: string;
  description: string;
  actions: PlanAction[];
  p_goal: number;
  cost_usd: number;
  packs: number;
  p_negative_by_week: number[];
  closing_p10_by_week: number[];
  closing_p50_by_week: number[];
  shortfall_cvar95_usd?: number | null;
  why: string[];
  incumbent?: { kept?: boolean; instead_of?: string; reason: string } | null;
}

export interface RankedPlan {
  plan_id: string;
  description: string;
  verdict?: string;
  p_goal: number;
  cost_usd: number;
  packs: number;
}

export interface Feasibility {
  verdict: string;
  goal_probability: number;
  best_allowed_p_goal: number;
  cash_needed_week1_usd: number;
  over_borrowing_cap_usd: number;
  eligible_sources_usd: number;
  binding: Array<{ limit: string; text: string }>;
  probes: Array<{ id: string; limit: string; change: string; p_goal: number }>;
  outside_financing: string[];
}

export interface SimilarCase {
  run_id: string;
  source: string;
  plan: string;
  predicted_p_goal: number;
  goal_met: boolean;
  primary_cause: string;
  lesson: string;
}

export interface PlanState {
  base_case: { first_negative_week: number | null; shortfall_usd: number; min_closing_usd: number };
  risk_without_action: RiskWithoutAction;
  receivables: { pledgeable: unknown[]; excluded: Record<string, string> };
  confirmed_orders: { count: number };
  constraints: { allowed_actions: string[]; max_packs_per_plan: number; over_borrowing_cap_usd: number; every_pack_needs: string };
  considered?: { plans_scored: number; plans_refused: number; plans_meeting_goal: number; draw_weeks: number[] };
}

export interface IntelligencePlan {
  status: string;
  goal: PlanGoal;
  state: PlanState;
  chosen: ChosenPlan;
  feasibility?: Feasibility;
  ranked: RankedPlan[];
  rejected: Array<{ description: string; violations: string[] }>;
  fixed_workflow_plan?: { description: string; p_goal: number; p_negative_by_week: number[] };
  world_model: { version: string; label: string; paths: number; seed: number };
  similar_cases: SimilarCase[];
  run_id: string;
}

export interface TwinAlert {
  id: string;
  label: string;
  status: string;
  source: string;
  priority?: { level: string; deadline?: string };
  base_case: { first_negative_week_before: number | null; first_negative_week_after: number | null };
  plan_in_force: { p_goal_before: number; p_goal_after: number };
  reasons: string[];
  new_plan: { description: string; p_goal: number; cost_usd: number };
  decided_by?: string | null;
}

export interface Twin {
  catalogue: Array<{ kind: string; label: string }>;
  applied: string[];
  inbox: TwinAlert[];
  digest: TwinAlert[];
  policy: string;
  counts: { events: number; director_alerts: number };
}

export interface PendingUpdate {
  version: string;
  proposed_by: string;
  metrics: { accepted: boolean; reason: string; loglik_current: number; loglik_candidate: number; held_out_wins: number; episodes: number };
  params: { buyer_logit_shift: Record<string, number>; ship_scale: number };
}

export interface Learning {
  registry: {
    active_version: string;
    active: { label: string; buyer_logit_shift: Record<string, number>; ship_scale: number; slowdown_prob: number };
    pending: PendingUpdate | null;
    history: Array<{ version: string; label: string; approved_by?: string; rejected_by?: string; ts?: string | null }>;
  };
  memory_chain_ok: boolean;
  episodes: number;
  episodes_with_miss: number;
  recent: Array<{ run_id: string; source: string; plan: string; predicted_p_goal: number; goal_met: boolean; cause: string }>;
}

export interface BenchSummary {
  label: string;
  goal_success_mean: number;
  expected_cost_mean_usd: number;
  shortfall_cvar95_mean_usd?: number | null;
  overconfidence_pp: number;
  policy_violations: number;
  same_plan_pct?: number | null;
  stability_pct: number;
  same_plan_without_incumbent_pct?: number | null;
  overconfidence_own_world_pp?: number | null;
}

export interface OpsMode {
  director_alerts: number;
  false_alerts: number;
  missed: number;
  precision_pct: number;
}

export interface Benchmark {
  generated_at: string;
  protocol: { test_cases: number };
  summary: Record<"fixed_workflow" | "planner_memory" | "planner_learning", BenchSummary>;
  ceiling_within_cap?: { mean: number; cases_reaching_90pct: number };
  ops?: {
    raw_events: number;
    cases: number;
    cashbridge: OpsMode;
    baseline_every_event: OpsMode;
    baseline_amount_threshold: OpsMode;
    ablation?: {
      without_plan_in_force_check: OpsMode;
      without_grouping: OpsMode;
    };
    completed_without_a_person: number;
    safety_violations: number;
  };
}

export interface IntelligenceData {
  plan: IntelligencePlan | null;
  learning: Learning;
  twin: Twin;
  benchmark?: Benchmark | null;
}

export interface EventResult {
  assessment: { route: string; id: string };
}

export interface SimulatedOutcome {
  run_id: string;
  outcome: {
    goal_met: boolean;
    attribution: { label: string; lesson: string };
    trough_usd: number;
    trough_week: number;
    contributions_usd: Record<string, number>;
  };
}
