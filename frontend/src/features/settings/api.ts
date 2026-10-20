import { get } from "@/shared/api/client";

export interface OrganisationPolicy {
  mode: string;
  you: { role: string; permissions: string[]; tenant: string };
  cash: { buffer_usd: number; concentration_alert_pct: number };
  approvals: { otp_validity_seconds: number; session_hours: number; segregation_of_duties: string; lender_decision: string };
  planner: { goals: Record<string, { label: string; min_probability: number }>; max_packs_per_plan: number; over_borrowing_factor: number };
  alerts: string;
  change_process: string;
}

/** Read-only: the rules the server enforces. Not every deployment exposes it, so a failure is tolerated. */
export const fetchPolicy = () => get<OrganisationPolicy>("/api/settings/policy").catch(() => null);
export const fetchHealth = () => get<{ ok: boolean }>("/api/health", { anonymous: true }).catch(() => null);
