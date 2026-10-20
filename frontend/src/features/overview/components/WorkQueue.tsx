import type { CaseSnapshot } from "@/entities/case";
import { useI18n } from "@/shared/i18n";

const ICON = { inbox: "▤", bank: "⌂", check: "✓", alert: "!", model: "◇", pack: "▣" };

function Tile({ label, n, href, icon, foot }: { label: string; n: number; href: string; icon: string; foot?: string }) {
  return (
    <a className={"work-tile" + (n ? " due" : "")} href={href}>
      <span className="wt-l">{label}</span>
      <b>{n}</b>
      <span className="wt-i" aria-hidden="true">{icon}</span>
      {foot ? <small>{foot}</small> : null}
    </a>
  );
}

/** One tile per action the signed-in person can actually take. */
export function WorkQueue({ s, director }: { s: CaseSnapshot; director: boolean }) {
  const { t } = useI18n();
  const state = s.meta.case_state;
  const exceptions = s.verification.filter((v) => v.status !== "ELIGIBLE").length + s.scans.filter((x) => x.status !== "READ").length;
  const unmatched = s.reconciliation.rows.filter((r) => r.status === "NEEDS_HUMAN").length;
  const readyToPrepare = ["INVOICE_VERIFIED", "OPTIONS_RANKED"].includes(state) || s.pack.status === "REJECTED_BY_DIRECTOR" ? 1 : 0;

  return (
    <div className="work-queue">
      {director ? (
        <>
          <Tile label={t("wq.approve")} n={state === "AWAITING_APPROVAL" ? 1 : 0} href="#funding" icon={ICON.pack} foot={t("wq.approveF")} />
          <Tile label={t("wq.alerts")} n={s.meta.director_alerts_open || 0} href="#core/decide" icon={ICON.alert} foot={t("wq.alertsF")} />
          <Tile label={t("wq.model")} n={s.meta.model_update_pending ? 1 : 0} href="#core/evidence" icon={ICON.model} foot={t("wq.modelF")} />
          <Tile label={t("wq.lender")} n={["FUNDED", "REJECTED"].includes(state) ? 1 : 0} href="#funding" icon={ICON.bank} foot={t("wq.lenderF")} />
        </>
      ) : (
        <>
          <Tile label={t("wq.exceptions")} n={exceptions} href="#evidence" icon={ICON.check} foot={t("wq.exceptionsF")} />
          <Tile label={t("wq.unmatched")} n={unmatched} href="#evidence" icon={ICON.bank} foot={t("wq.unmatchedF")} />
          <Tile label={t("wq.held")} n={s.alerts.length} href="#evidence" icon={ICON.inbox} foot={t("wq.heldF")} />
          <Tile label={t("wq.prepare")} n={readyToPrepare} href="#autopilot" icon={ICON.pack} foot={t("wq.prepareF")} />
        </>
      )}
    </div>
  );
}
