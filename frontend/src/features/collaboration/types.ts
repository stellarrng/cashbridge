/** Shapes of the workspace endpoints: planning requests, appeals, case messages, lender evidence requests, notifications. */

export interface Activity {
  actor: string;
  action: string;
  detail: string;
  time?: string;
}

export interface PlanningRequest {
  id: string;
  kind: "planning_change" | "evidence_appeal";
  field: string | null;
  proposed: string | null;
  old_value: string | null;
  reason: string;
  status: string;
  actor: string;
  created: string;
  activities: Activity[];
}

export interface RequestsView {
  requests: PlanningRequest[];
  approved_scenario_assumptions: Record<string, { value: number; version: number }>;
  note: string;
}

export interface CaseMessage {
  id: string;
  actor_role: string;
  kind: string;
  message: string;
  created: string;
}

export interface EvidenceRequest {
  id: string;
  item: string;
  detail: string;
  status: "open" | "submitted" | "accepted" | "rejected" | "revoked" | "expired";
  due: string;
  version: number;
  evidence_ref: string | null;
  evidence_sha256: string | null;
  /** Set when the document itself was uploaded into the encrypted vault (v9). */
  evidence_file_id: string | null;
  /** Version the lender opened through CashBridge; acceptance requires it to equal `version`. */
  viewed_version: number | null;
  decision_reason: string | null;
  timeline: Required<Activity>[];
}

export interface EvidenceView {
  items: EvidenceRequest[];
  counts: Record<string, number>;
  blocking_funding: string[];
  ready_for_decision: boolean;
}

export interface Notification {
  case_id: string;
  request_id: string | null;
  text: string;
  time: string;
}

export interface QualityResult {
  gate: string;
  quality_index: number;
  notice: string;
  issues: Array<{ detail: string }>;
}

export interface ScenarioResult {
  funding_gap_usd: number;
  notes: string[];
}
