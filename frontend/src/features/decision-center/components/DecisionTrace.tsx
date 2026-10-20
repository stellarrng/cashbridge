import type { ReactNode } from "react";
import type { CaseSnapshot } from "@/entities/case";
import { useI18n } from "@/shared/i18n";
import { pp, usd } from "@/shared/lib/format";
import { Note, Panel } from "@/shared/ui";
import { useAuth } from "../../auth";
import type { IntelligencePlan, Twin, TwinAlert } from "../types";
import { FeasibilityBlock } from "./FeasibilityBlock";

type StepState = "done" | "attention" | "wait";

function Step({ n, title, state, summary, children }: { n: number; title: string; state: StepState; summary: ReactNode; children: ReactNode }) {
  const { t } = useI18n();
  const tone = state === "done" ? "ok" : state === "wait" ? "warn" : "bad";
  return (
    <li className={"ts " + state}>
      <details>
        <summary>
          <span className="ts-n">{n}</span>
          <span className="ts-t"><b>{title}</b><span>{summary}</span></span>
          <span className={"pill " + tone}>{t("tr2.st." + state)}</span>
        </summary>
        <div className="ts-b">{children}</div>
      </details>
    </li>
  );
}

/** The five steps behind the plan on screen, rebuilt from the run that produced it (not an illustration). */
export function DecisionTrace({ plan, twin, snapshot, open }: { plan: IntelligencePlan; twin: Twin; snapshot: CaseSnapshot | null; open: TwinAlert[] }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const st = plan.state;
  const ch = plan.chosen;
  const risk = st.risk_without_action;
  const base = st.base_case;
  const cons = st.considered;
  const ver = snapshot ? snapshot.verification : [];
  const ok = ver.filter((v) => v.status === "ELIGIBLE").length;
  const excluded = Object.entries(st.receivables.excluded || {});
  const alts = plan.ranked.filter((r) => r.plan_id !== ch.plan_id).slice(0, 2);
  const caseState = snapshot ? snapshot.meta.case_state : "";
  const awaiting = caseState === "AWAITING_APPROVAL";

  return (
    <Panel title={t("tr2.title")} sub={t("tr2.sub")}>
      <ol className="trace2">
        <Step
          n={1}
          title={t("tr2.risk")}
          state={base.first_negative_week ? "attention" : "done"}
          summary={base.first_negative_week ? t("tr2.risk.s", { w: base.first_negative_week, a: usd(base.shortfall_usd), p: pp(risk.p_no_negative_week) }) : t("tr2.risk.none")}
        >
          <ul className="list small">
            <li>{t("tr2.risk.b1", { a: usd(base.min_closing_usd) })}</li>
            <li>{t("tr2.risk.b2", { p: pp(risk.p_no_negative_week), n: plan.world_model.paths })}</li>
            {twin.applied.length > 0 && <li>{t("tr2.events")}: {twin.applied.map((k) => t("core.ev." + k)).join(", ")}</li>}
          </ul>
        </Step>
        <Step
          n={2}
          title={t("tr2.evidence")}
          state={excluded.length ? "attention" : "done"}
          summary={t("tr2.ev.s", { ok, n: ver.length || ok, x: excluded.length })}
        >
          <ul className="list small">
            <li>{t("tr2.ev.b1", { n: st.receivables.pledgeable.length })}</li>
            {excluded.slice(0, 4).map(([k, v]) => <li key={k}><span className="mono">{k}</span>: {v}</li>)}
            <li>{t("tr2.ev.b2", { n: st.confirmed_orders.count })}</li>
          </ul>
          <a className="btn ghost small" href="#evidence">{t("tr2.open")}</a>
        </Step>
        <Step
          n={3}
          title={t("tr2.scenarios")}
          state="done"
          summary={t("tr2.sc.s", { n: cons?.plans_scored || plan.ranked.length, r: cons?.plans_refused || 0, p: plan.world_model.paths })}
        >
          <ul className="list small">
            <li>{t("tr2.sc.b1", { m: cons?.plans_meeting_goal || 0, g: pp(plan.goal.min_probability) })}</li>
            <li>{t("tr2.sc.b2", { w: (cons?.draw_weeks || []).join(", ") })}</li>
            <li>{t("tr2.sc.b3")} <span className="mono">{plan.world_model.version}</span></li>
          </ul>
        </Step>
        <Step n={4} title={t("tr2.rec")} state={plan.status === "GOAL_MET" ? "done" : "attention"} summary={`${ch.description} · ${pp(ch.p_goal)} · ${usd(ch.cost_usd)}`}>
          <ul className="list small">
            {ch.why.slice(0, 2).map((w, i) => <li key={i}>{w}</li>)}
            {ch.shortfall_cvar95_usd != null && risk.shortfall_cvar95_usd != null && (
              <li>{t("tr2.cvar", { a: usd(ch.shortfall_cvar95_usd), b: usd(risk.shortfall_cvar95_usd) })}</li>
            )}
          </ul>
          <FeasibilityBlock plan={plan} />
          <h4 className="mini">{t("tr2.alts")}</h4>
          <ul className="list small">{alts.map((r) => <li key={r.plan_id}>{r.description}: {r.verdict || ""}</li>)}</ul>
          <Note>{t("core.dc.notCredit")}</Note>
        </Step>
        <Step
          n={5}
          title={t("tr2.approval")}
          state={open.length || awaiting ? "wait" : "done"}
          summary={open.length ? t("tr2.ap.inbox", { n: open.length }) : awaiting ? t("tr2.ap.pack") : t("tr2.ap.none")}
        >
          <ul className="list small">
            <li>{t("tr2.ap.b1")}</li>
            <li>{t("tr2.ap.b2")}</li>
          </ul>
          {awaiting && can("sme:approve") && <a className="btn bridge small" href="#funding">{t("btn.openFunding")}</a>}
        </Step>
      </ol>
    </Panel>
  );
}
