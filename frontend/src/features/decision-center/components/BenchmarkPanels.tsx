import { HBars } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { pp, usd } from "@/shared/lib/format";
import { Note, Panel, Scroll } from "@/shared/ui";
import type { Benchmark } from "../types";

const NAMES = ["fixed_workflow", "planner_memory", "planner_learning"] as const;
const dash = (v: number | null | undefined, fmt: (n: number) => string) => (v != null ? fmt(v) : "–");
const signed = (v: number) => (v > 0 ? "+" : "") + v + " pp";

/** Planner variants (fixed workflow vs planner + memory vs planner + learning) on the same hidden test quarters. */
export function PlannerBenchmark({ b }: { b: Benchmark }) {
  const { t } = useI18n();
  const S = b.summary;
  const learning = S.planner_learning;
  return (
    <Panel title={t("core.bench")} sub={`${t("core.benchSub")} · ${b.generated_at}`}>
      <h3 className="mini">{t("core.b.success")}</h3>
      <HBars
        items={NAMES.map((n, i) => ({
          label: S[n].label,
          value: S[n].goal_success_mean * 100,
          display: (S[n].goal_success_mean * 100).toFixed(1) + "%",
          cls: i === 2 ? "cb-accent" : "cb-muted",
          strong: i === 2,
        }))}
      />
      <Scroll>
        <table>
          <thead><tr><th></th>{NAMES.map((n) => <th key={n}>{S[n].label}</th>)}</tr></thead>
          <tbody>
            <tr><td>{t("core.k.cost")}</td>{NAMES.map((n) => <td key={n}>{usd(S[n].expected_cost_mean_usd)}</td>)}</tr>
            {S[NAMES[0]].shortfall_cvar95_mean_usd != null && (
              <tr><td>{t("core.b.cvar")}</td>{NAMES.map((n) => <td key={n}>{usd(S[n].shortfall_cvar95_mean_usd)}</td>)}</tr>
            )}
            <tr><td>{t("core.b.overconf")}</td>{NAMES.map((n) => <td key={n}>{signed(S[n].overconfidence_pp)}</td>)}</tr>
            <tr><td>{t("core.b.viol")}</td>{NAMES.map((n) => <td key={n}>{S[n].policy_violations}</td>)}</tr>
            <tr><td>{t("core.b.same")}</td>{NAMES.map((n) => <td key={n}>{dash(S[n].same_plan_pct, (v) => v + "%")}</td>)}</tr>
            <tr><td>{t("core.b.stable")}</td>{NAMES.map((n) => <td key={n}>{S[n].stability_pct}%</td>)}</tr>
            {learning.same_plan_without_incumbent_pct != null && (
              <>
                <tr><td>{t("abl.noIncumbent")}</td>{NAMES.map((n) => <td key={n}>{dash(S[n].same_plan_without_incumbent_pct, (v) => v + "%")}</td>)}</tr>
                <tr><td>{t("abl.ownWorld")}</td>{NAMES.map((n) => <td key={n}>{dash(S[n].overconfidence_own_world_pp, signed)}</td>)}</tr>
              </>
            )}
          </tbody>
        </table>
      </Scroll>
      {b.ceiling_within_cap && (
        <p className="small">{t("abl.ceiling", { m: pp(b.ceiling_within_cap.mean), k: b.ceiling_within_cap.cases_reaching_90pct, n: b.protocol.test_cases })}</p>
      )}
    </Panel>
  );
}

/** How often the Director is disturbed: CashBridge's routing vs forwarding everything or a flat amount threshold. */
export function OperationsBenchmark({ b }: { b: Benchmark }) {
  const { t } = useI18n();
  const o = b.ops;
  if (!o) return null;
  const cb = o.cashbridge, ev = o.baseline_every_event, th = o.baseline_amount_threshold;
  return (
    <Panel title={t("ops.title")} sub={t("ops.sub", { r: o.raw_events, c: o.cases })}>
      <HBars
        items={[
          { label: t("ops.every"), value: ev.director_alerts, display: String(ev.director_alerts), cls: "cb-muted" },
          { label: t("ops.threshold"), value: th.director_alerts, display: String(th.director_alerts), cls: "cb-muted" },
          { label: "CashBridge", value: cb.director_alerts, display: String(cb.director_alerts), cls: "cb-accent", strong: true },
        ]}
      />
      <Scroll>
        <table>
          <thead><tr><th></th><th>{t("ops.every")}</th><th>{t("ops.threshold")}</th><th>CashBridge</th></tr></thead>
          <tbody>
            <tr><td>{t("ops.false")}</td><td>{ev.false_alerts}</td><td>{th.false_alerts}</td><td>{cb.false_alerts}</td></tr>
            <tr><td>{t("ops.missed")}</td><td>{ev.missed}</td><td>{th.missed}</td><td>{cb.missed}</td></tr>
            <tr><td>{t("ops.precision")}</td><td>{ev.precision_pct}%</td><td>{th.precision_pct}%</td><td>{cb.precision_pct}%</td></tr>
          </tbody>
        </table>
      </Scroll>
      <p className="small">{t("ops.auto", { n: o.completed_without_a_person, c: o.cases, v: o.safety_violations })}</p>
      {o.ablation && (
        <>
          <h3 className="mini">{t("abl.title")}</h3>
          <Scroll>
            <table>
              <thead><tr><th></th><th>{t("ops.notif")}</th><th>{t("ops.false")}</th><th>{t("ops.missed")}</th></tr></thead>
              <tbody>
                <tr><td><b>CashBridge</b></td><td>{cb.director_alerts}</td><td>{cb.false_alerts}</td><td>{cb.missed}</td></tr>
                <tr><td>{t("abl.noPlanCheck")}</td><td>{o.ablation.without_plan_in_force_check.director_alerts}</td><td>{o.ablation.without_plan_in_force_check.false_alerts}</td><td>{o.ablation.without_plan_in_force_check.missed}</td></tr>
                <tr><td>{t("abl.noGroup")}</td><td>{o.ablation.without_grouping.director_alerts}</td><td>{o.ablation.without_grouping.false_alerts}</td><td>{o.ablation.without_grouping.missed}</td></tr>
              </tbody>
            </table>
          </Scroll>
        </>
      )}
      <Note>{t("ops.note")}</Note>
    </Panel>
  );
}
