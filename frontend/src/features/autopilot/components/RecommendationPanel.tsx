import type { AutopilotRun, Recommendation } from "@/entities/autopilot";
import { WeeklyCashChart, type ForecastWeek } from "@/entities/forecast";
import { useI18n } from "@/shared/i18n";
import { pct, usd2 } from "@/shared/lib/format";
import { BulletList, Caution, Note, Panel } from "@/shared/ui";

export function RecommendationPanel({ run, rec, weeks }: { run: AutopilotRun; rec: Recommendation; weeks: ForecastWeek[] }) {
  const { t } = useI18n();
  return (
    <Panel title={t("ap.rec")} sub={`Run ${run.run_id} · ${run.mode} · ${run.planner}`}>
      <div className="rec-head">
        <b>{rec.option_name}</b>
        <span>{usd2(rec.amount_usd)} · {pct(rec.apr_pct, 2)}</span>
        <span className="muted">{t("col.total")} {usd2(rec.total_cost_usd)}</span>
      </div>
      <BulletList items={rec.why} />
      <Caution title={t("ap.notFix")} items={rec.what_would_change} />
      {rec.coverage && (
        <>
          <h3 className="mini">{t("ap.withWithout")}</h3>
          <WeeklyCashChart weeks={weeks} after={rec.coverage.weeks.map((w) => w.closing_after)} />
          <Note>{rec.coverage.assumptions.filter(Boolean).join(" ")}</Note>
        </>
      )}
      <h3 className="mini">{t("ap.conditions")}</h3>
      <BulletList items={rec.conditions} />
      {rec.core_plan ? (
        <div className="row" style={{ marginTop: 12 }}>
          <a className="btn ghost" href="#core">{t("core.open")}</a>
        </div>
      ) : null}
    </Panel>
  );
}
