import type { FormEvent } from "react";
import { HBars, LineChart } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { pp, usd } from "@/shared/lib/format";
import { Note, Panel, Scroll } from "@/shared/ui";
import type { IntelligencePlan, RankedPlan, Twin } from "../types";

const GOALS = ["keep_cash_positive", "keep_above_buffer"];
const PROBABILITIES = [0.8, 0.85, 0.9, 0.95];

interface Props {
  plan: IntelligencePlan;
  twin: Twin;
  /** Goal and probability floor chosen in the form; the page's "Run" button uses the same values. */
  goalId: string;
  probability: number;
  onGoalChange: (goalId: string, probability: number) => void;
  /** Re-run the planner with the chosen goal. */
  onRun: () => void;
}

function RankedTable({ rows, chosenId, floor }: { rows: RankedPlan[]; chosenId: string; floor: number }) {
  const { t } = useI18n();
  return (
    <Scroll>
      <table>
        <thead>
          <tr><th>{t("col.plan")}</th><th>{t("col.pgoal")}</th><th>{t("col.ecost")}</th><th>{t("col.packs")}</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.plan_id} className={r.plan_id === chosenId ? "chosen" : ""}>
              <td>{r.description}{r.verdict && <div className="muted small">{r.verdict}</div>}</td>
              <td><HBars items={[{ label: "", value: r.p_goal * 100, display: pp(r.p_goal), cls: r.p_goal >= floor ? "cb-good" : "cb-muted" }]} /></td>
              <td>{usd(r.cost_usd)}</td>
              <td>{r.packs}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Scroll>
  );
}

export function AnalysisTab({ plan, twin, goalId, probability, onGoalChange, onRun }: Props) {
  const { t } = useI18n();
  const ch = plan.chosen;
  const risk = plan.state.risk_without_action;
  const goal = plan.goal;
  const cons = plan.state.considered;
  const weeks = risk.p_negative_by_week.map((_, i) => "W" + (i + 1));
  const c = plan.state.constraints;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onRun();
  };

  return (
    <>
      <form className="panel goal-bar" onSubmit={submit}>
        <label className="field inline">
          {t("core.goal")}
          <select value={goalId} onChange={(e) => onGoalChange(e.target.value, probability)}>
            {GOALS.map((g) => <option key={g} value={g}>{t("core.goal." + g)}</option>)}
          </select>
        </label>
        <label className="field inline">
          {t("core.prob")}
          <select value={probability} onChange={(e) => onGoalChange(goalId, Number(e.target.value))}>
            {PROBABILITIES.map((p) => <option key={p} value={p}>{pp(p)} {t("core.ofPaths")}</option>)}
          </select>
        </label>
        <a className="btn ghost small" href="#cash">{t("core.whatif")}</a>
      </form>
      <Panel
        title={t("core.ranked")}
        sub={
          <>
            {t("core.rankedSub")}
            {cons && <> · <b>{t("core.considered", { n: cons.plans_scored, r: cons.plans_refused, m: cons.plans_meeting_goal })}</b></>}
          </>
        }
      >
        <RankedTable rows={plan.ranked.slice(0, 3)} chosenId={ch.plan_id} floor={goal.min_probability} />
        {plan.ranked.length > 3 && (
          <details className="more">
            <summary>{t("core.allPlans", { n: plan.ranked.length })}</summary>
            <RankedTable rows={plan.ranked.slice(3)} chosenId={ch.plan_id} floor={goal.min_probability} />
          </details>
        )}
      </Panel>
      <div className="dash">
        <div className="span2">
          <Panel title={t("core.band")} sub={t("core.bandSub")}>
            <LineChart
              labels={weeks}
              label={t("core.band")}
              fmt={(v) => usd(v)}
              endLabels
              dots="ends"
              series={[
                { name: t("core.s.noneP10"), values: risk.closing_p10_by_week, color: "var(--ink-3)", dash: "5 4", muted: true },
                { name: t("core.s.planP10"), values: ch.closing_p10_by_week, color: "var(--s1)", width: 3 },
                { name: t("core.s.planP50"), values: ch.closing_p50_by_week, color: "var(--s2)", muted: true },
              ]}
            />
          </Panel>
        </div>
        <Panel title={t("core.chosen")} sub={ch.description}>
          <ul className="list small">
            {ch.why.map((w, i) => <li key={i}>{w}</li>)}
            {ch.incumbent?.kept && ch.incumbent.instead_of && <li>{ch.incumbent.reason}</li>}
          </ul>
          <Note>{t("core.packNote")}</Note>
        </Panel>
        <div className="span3">
          <Panel title={t("core.constraints")}>
            <ul className="list small">
              <li>{c.allowed_actions.join(", ")}</li>
              <li>max {c.max_packs_per_plan} {t("col.packs").toLowerCase()}</li>
              <li>cap {usd(c.over_borrowing_cap_usd)}</li>
              <li>{c.every_pack_needs}</li>
            </ul>
            {plan.rejected.length > 0 && (
              <>
                <h3 className="mini">{t("core.rejected")}</h3>
                <ul className="list small">{plan.rejected.slice(0, 5).map((r, i) => <li key={i}>{r.description}: {r.violations.join("; ")}</li>)}</ul>
              </>
            )}
            <Note>{twin.policy}</Note>
          </Panel>
        </div>
      </div>
    </>
  );
}
