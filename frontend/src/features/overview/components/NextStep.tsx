import type { CaseSnapshot } from "@/entities/case";
import { StatusPill } from "@/entities/status";
import { useI18n } from "@/shared/i18n";
import { useAuth } from "../../auth";

/** What should happen next for this role, plus the latest audited activity. */
export function NextStep({ s }: { s: CaseSnapshot }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const state = s.meta.case_state;
  const nextKey =
    state === "AWAITING_APPROVAL" ? (can("sme:approve") ? "next.approve" : "next.wait")
    : state === "SUBMITTED" ? "next.lender"
    : ["FUNDED", "REJECTED"].includes(state) ? "next.done"
    : s.pack.status === "REJECTED_BY_DIRECTOR" ? "next.rework"
    : can("sme:prepare") ? "next.run"
    : "next.prepare";
  const toFunding = ["next.approve", "next.wait", "next.lender", "next.done", "next.rework"].includes(nextKey);
  const activity = s.evidence.audit_tail.slice(-6).reverse();

  return (
    <>
      <p className="next">{t(nextKey)}</p>
      <div className="row" style={{ marginTop: 12 }}>
        <a className="btn bridge" href={toFunding ? "#funding" : "#autopilot"}>{t(toFunding ? "btn.openFunding" : "btn.openAutopilot")}</a>
      </div>
      <h3 className="mini">{t("ov.activity")}</h3>
      <ul className="activity">
        {activity.map((a) => (
          <li key={a.seq}>
            <span className="mono small">#{a.seq}</span>
            <span>{a.agent} · {a.tool}</span>
            <StatusPill status={a.decision} />
          </li>
        ))}
      </ul>
    </>
  );
}
