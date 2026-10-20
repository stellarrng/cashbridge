import type { AutopilotRun } from "@/entities/autopilot";
import { useI18n } from "@/shared/i18n";
import { useAuth } from "../../auth";

export function DecisionBanner({ run }: { run: AutopilotRun }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const d = run.decision;
  const link =
    d === "AWAITING_DIRECTOR_APPROVAL" ? (can("sme:approve") ? { href: "#funding", label: "btn.review" } : null)
    : d === "HUMAN_REVIEW_REQUIRED" ? { href: "#evidence", label: "btn.exceptions" }
    : d === "SUBMITTED_TO_LENDER" || d === "DECLINED_BY_LENDER" ? { href: "#funding", label: "btn.lenderStatus" }
    : null;
  const warn = d === "HUMAN_REVIEW_REQUIRED" || d === "DECLINED_BY_LENDER";
  return (
    <div className={"decision" + (warn ? " warn" : "")}>
      <div>
        <h2>{t("dec." + d)}</h2>
        <p>{run.human_handoff.action}. {run.human_handoff.why}.</p>
      </div>
      {link && <a className="btn" href={link.href}>{t(link.label)}</a>}
    </div>
  );
}
