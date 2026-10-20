import { useI18n } from "@/shared/i18n";
import { human } from "@/shared/lib/format";

const TONE: Record<string, "ok" | "warn" | "bad"> = {
  ok: "ok", ELIGIBLE: "ok", BOOKED: "ok", READ: "ok", VERIFIED: "ok", SUBMITTED: "ok", FUNDED: "ok", FUNDED_MOCK: "ok", ALLOWED: "ok", APPROVED: "ok",
  at_risk: "warn", FLAGGED: "warn", NEEDS_HUMAN: "warn", AWAITING_APPROVAL: "warn", IN_REVIEW: "warn", INFO_REQUESTED: "warn",
  OPEN: "warn", PENDING: "warn", SUBMITTED_EVIDENCE: "warn", ACCEPTED: "ok", EXPIRED: "bad", REVOKED: "warn",
  WITHDRAWN_BY_SME: "warn", WITHDRAWN: "warn",
  shortfall: "bad", BLOCKED: "bad", REJECTED: "bad", DECLINED: "bad", REJECTED_BY_DIRECTOR: "bad",
};

/** A coloured status label. Unknown statuses fall back to a neutral pill with the raw text. */
export function StatusPill({ status }: { status: string }) {
  const { t, has } = useI18n();
  const label = has("st." + status) ? t("st." + status) : human(status);
  return <span className={("pill " + (TONE[status] ?? "")).trim()}>{label}</span>;
}
