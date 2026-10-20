import type { CaseSnapshot } from "@/entities/case";
import { LineChart, type LineSeries } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { pp, usd, usd2 } from "@/shared/lib/format";
import { usePreferences } from "@/shared/preferences";
import { EngineNote, Kpi, Kpis, Note, Panel } from "@/shared/ui";
import { useAuth } from "../../auth";
import { AlertCard } from "../components/AlertCard";
import { DecisionTrace } from "../components/DecisionTrace";
import { EventSimulator } from "../components/EventSimulator";
import type { IntelligencePlan, Twin } from "../types";

interface Props {
  plan: IntelligencePlan;
  twin: Twin;
  snapshot: CaseSnapshot | null;
  onDecide: (id: string, accept: boolean) => void;
  onApplyEvent: (kind: string) => void;
  onResetEvents: () => void;
}

function actionLabel(a: IntelligencePlan["chosen"]["actions"][number]): string {
  return a.type === "factor" ? "Factoring " + a.ref : a.type === "loan" ? "Bridge loan" : "Deposit " + a.ref;
}

export function DecideTab({ plan, twin, snapshot, onDecide, onApplyEvent, onResetEvents }: Props) {
  const { t } = useI18n();
  const { can } = useAuth();
  const { view } = usePreferences();
  const ch = plan.chosen;
  const fx = plan.fixed_workflow_plan;
  const risk = plan.state.risk_without_action;
  const open = twin.inbox.filter((a) => a.status === "OPEN");
  const decided = twin.inbox.filter((a) => a.status !== "OPEN");
  const simple = view === "simple";

  // Focus on the recommended plan; "no action" is a grey dashed reference; the single advance is a muted comparison.
  const noneV = risk.p_negative_by_week.map((x) => x * 100);
  const planV = ch.p_negative_by_week.map((x) => x * 100);
  const series: LineSeries[] = [{ name: t("core.s.none"), values: noneV, color: "var(--ink-3)", dash: "5 4", muted: true }];
  if (fx && !simple) series.push({ name: t("core.s.fixed"), values: fx.p_negative_by_week.map((x) => x * 100), color: "var(--s2)", muted: true });
  series.push({ name: t("core.s.plan"), values: planV, color: "var(--s1)", width: 3 });
  const ref = fx && !simple ? fx.p_negative_by_week.map((x) => x * 100) : noneV;
  const peak = ref.indexOf(Math.max(...ref));
  const weeks = risk.p_negative_by_week.map((_, i) => "W" + (i + 1));

  const sim = <><span className="pill sim">{t("lbl.sim")}</span>{" "}</>;
  const canDecide = can("sme:approve");

  return (
    <>
      <div className={"decision" + (open.length ? " warn" : "")}>
        <div>
          <h2>{open.length ? t("core.dc.need", { n: open.length }) : t("core.dc.none")}</h2>
          <p>{t("core.dc.sub")}</p>
        </div>
      </div>
      <EngineNote />
      <Kpis>
        <Kpi label={t("core.k.none")} tone="neg" value={pp(risk.p_no_negative_week)} foot={<>{sim}{t("core.k.foot")}</>} />
        <Kpi label={t("core.k.fixed")} tone="warn" value={fx ? pp(fx.p_goal) : "–"} foot={<>{sim}{fx ? fx.description : ""}</>} />
        <Kpi highlight label={t("core.k.plan")} value={pp(ch.p_goal)} foot={<>{sim}{t("core.status." + plan.status)}</>} />
        <Kpi label={t("core.k.cost")} value={usd(ch.cost_usd)} foot={`${ch.packs} ${t("col.packs").toLowerCase()}`} />
      </Kpis>
      <DecisionTrace plan={plan} twin={twin} snapshot={snapshot} open={open} />
      <div className="dash">
        <div className="span2">
          <Panel title={t("core.inbox")} sub={t("core.dc.inboxSub")}>
            {open.length ? open.map((a) => <AlertCard key={a.id} alert={a} open canDecide={canDecide} onDecide={onDecide} />) : <p className="muted">{t("core.dc.empty")}</p>}
            {decided.length > 0 && (
              <details className="more">
                <summary>{t("core.dc.decided", { n: decided.length })}</summary>
                {decided.map((a) => <AlertCard key={a.id} alert={a} open={false} canDecide={false} onDecide={onDecide} />)}
              </details>
            )}
            {twin.digest.length > 0 && (
              <details className="more">
                <summary>{t("core.dc.digest", { n: twin.digest.length })}</summary>
                {twin.digest.map((a) => <AlertCard key={a.id} alert={a} open={false} canDecide={false} onDecide={onDecide} />)}
              </details>
            )}
            <EventSimulator twin={twin} onApply={onApplyEvent} onReset={onResetEvents} />
          </Panel>
        </div>
        <Panel title={t("core.chosen")} sub={t("core.status." + plan.status)}>
          <ul className="plan-actions">
            {ch.actions.map((a, i) => (
              <li key={i}>
                <b>{actionLabel(a)}</b>
                <span>{a.type === "deposit_cut" ? a.new_pct + "%" : usd2(a.advance_usd != null ? a.advance_usd : a.amount_usd)}</span>
                <span className="muted">{t("lbl.week", { w: a.week })}</span>
                {a.type === "deposit_cut" ? <span className="pill warn">Supplier</span> : <span className="pill">OTP</span>}
              </li>
            ))}
          </ul>
          <ul className="list small">{ch.why.slice(0, 2).map((w, i) => <li key={i}>{w}</li>)}</ul>
          <div className="row">
            <a className="btn ghost small" href="#core/analysis">{t("core.dc.compare")}</a>
            <a className="btn ghost small" href="#core/evidence">{t("core.dc.evidence")}</a>
          </div>
          <Note>{t("core.dc.notCredit")}</Note>
        </Panel>
        <div className="span3">
          <Panel title={t("core.risk")} sub={t("core.riskSub")}>
            <LineChart
              labels={weeks}
              series={series}
              label={t("core.risk")}
              fmt={(v) => v.toFixed(0) + "%"}
              yfmt={(v) => Math.round(v) + "%"}
              endLabels
              dots="ends"
              annotate={{ index: peak, text: t("core.peak", { w: peak + 1, a: Math.round(ref[peak]) + "%", b: Math.round(planV[peak]) + "%" }) }}
              tipExtra={(i) => t("core.delta", { d: (planV[i] - noneV[i]).toFixed(0) })}
            />
          </Panel>
        </div>
      </div>
    </>
  );
}
