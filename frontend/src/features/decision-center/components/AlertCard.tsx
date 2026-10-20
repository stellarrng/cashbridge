import { StatusPill } from "@/entities/status";
import { useI18n } from "@/shared/i18n";
import { pp, usd } from "@/shared/lib/format";
import { Button } from "@/shared/ui";
import type { TwinAlert } from "../types";

const STATUS_PILL: Record<string, string> = { OPEN: "AWAITING_APPROVAL", ACCEPTED: "APPROVED", HANDLED: "ok" };

interface Props {
  alert: TwinAlert;
  open: boolean;
  canDecide: boolean;
  onDecide: (id: string, accept: boolean) => void;
}

/** One item in the Director's inbox: why it matters, the replacement plan, and accept / keep buttons. */
export function AlertCard({ alert: a, open, canDecide, onDecide }: Props) {
  const { t } = useI18n();
  const level = a.priority?.level;
  return (
    <div className={"alert-card" + (open ? " open" : "")}>
      <div className="row-between">
        <b>
          {level && <><span className={"pill " + (level === "HIGH" ? "bad" : level === "MEDIUM" ? "warn" : "")}>{level}</span>{" "}</>}
          {a.label}
        </b>
        <StatusPill status={STATUS_PILL[a.status] ?? "ALLOWED"} />
      </div>
      <p className="small muted">
        {a.id} · {a.source} · {t("lbl.week", { w: a.base_case.first_negative_week_before || "–" })} → {t("lbl.week", { w: a.base_case.first_negative_week_after || "–" })} ·{" "}
        {t("core.inForce")}: {pp(a.plan_in_force.p_goal_before)} → {pp(a.plan_in_force.p_goal_after)}
        {a.priority?.deadline && a.status === "OPEN" ? ` · ${t("core.deadline")} ${a.priority.deadline}` : ""}
      </p>
      {open && a.reasons.length > 0 && <ul className="list small">{a.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
      {open && <p className="small"><b>{a.new_plan.description}</b> · {pp(a.new_plan.p_goal)} · {usd(a.new_plan.cost_usd)}</p>}
      {open && canDecide && (
        <div className="row">
          <Button small variant="bridge" onClick={() => onDecide(a.id, true)}>{t("core.accept")}</Button>
          <Button small variant="ghost" onClick={() => onDecide(a.id, false)}>{t("core.keep")}</Button>
        </div>
      )}
      {a.decided_by && <p className="small muted">{a.decided_by}</p>}
    </div>
  );
}
