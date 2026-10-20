import { useState } from "react";
import { DonutChart } from "@/shared/charts";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { human, sentence, usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, EngineNote, Kpi, Kpis, Loadable, Note, PageHead } from "@/shared/ui";
import { fetchCashImpact, fetchEconomics, fetchGreenProjects, requestReview, type CashImpactScenario, type GreenCashImpact, type GreenEconomics, type GreenProject } from "./api";

export default function GreenFinanceScreen(_: ScreenProps) {
  const { t } = useI18n();
  const projects = useAsync(fetchGreenProjects, []);
  return (
    <Loadable data={projects.data} error={projects.error}>
      {(d) => (
        <>
          <PageHead title={t("grn.title")} lede={t("grn.lede")} />
          <EngineNote />
          {d.projects.map((p) => <ProjectCard key={p.project_id} project={p} onReviewed={() => void projects.reload()} />)}
        </>
      )}
    </Loadable>
  );
}

function ProjectCard({ project: p, onReviewed }: { project: GreenProject; onReviewed: () => void }) {
  const act = useAct();
  const { t } = useI18n();
  const [eco, setEco] = useState<GreenEconomics | null>(null);
  const [cash, setCash] = useState<GreenCashImpact | null>(null);
  const provided = p.evidence.filter((x) => x.status !== "missing").length;
  const pending = p.review_status === "PENDING_HUMAN_REVIEW";

  return (
    <section className="panel">
      <h2>{p.name}</h2>
      <p className="sub">{p.activity_name}</p>
      <div className="grid2">
        <div>
          <Kpis>
            <Kpi label="Project cost" value={usd(p.project_cost_usd)} />
            <Kpi label="Loan requested" value={usd(p.requested_loan_usd)} />
            <Kpi label="tCO2e / yr (illustrative)" value={p.illustrative_annual_impact_tco2e == null ? "–" : p.illustrative_annual_impact_tco2e} />
          </Kpis>
          <table>
            <tbody>
              {p.evidence.map((x, i) => (
                <tr key={i}>
                  <td>{x.label}</td>
                  <td>{x.status === "missing" ? <span className="pill bad">Missing</span> : <span className="pill warn">{sentence(human(x.status))}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DonutChart
          center={p.documentation_completeness_pct + "%"}
          centerSub="Evidence"
          parts={[
            { label: "Provided", value: provided, color: "var(--good)" },
            { label: "Missing", value: p.evidence.length - provided, color: "var(--deficit)" },
          ]}
        />
      </div>
      <div className="row mt-2">
        <Button small variant="ghost" onClick={async () => { const x = await act(() => fetchEconomics(p.project_id)); if (x) setEco(x); }}>Payback @ $0.12/kWh</Button>
        <Button small variant="ghost" data-cash={p.project_id} onClick={async () => { const x = await act(() => fetchCashImpact(p.project_id)); if (x) setCash(x); }}>{t("grn.cash")}</Button>
        <Button small variant={pending ? "ghost" : "bridge"} disabled={pending} onClick={async () => { if (await act(() => requestReview(p.project_id))) onReviewed(); }}>
          {pending ? "Review requested" : "Request internal review"}
        </Button>
      </div>
      <div>
        {eco && (
          <>
            <div className="kpis cards mt-2">
              <Kpi label="Net savings / yr" value={usd(eco.estimated_net_savings_usd_per_year)} />
              <Kpi label="Simple payback" value={eco.simple_payback_years == null ? "–" : eco.simple_payback_years + " y"} />
            </div>
            <Note>{eco.limitation}</Note>
          </>
        )}
        {cash && <CashImpact x={cash} />}
      </div>
    </section>
  );
}

/** Green investment against the 13-week cash buffer: no project, paid in cash, or with the case's loan quote. */
function CashImpact({ x }: { x: GreenCashImpact }) {
  const { t } = useI18n();
  const row = (label: string, s: CashImpactScenario) => (
    <tr key={label}>
      <td>{label}</td>
      <td className={"num" + (s.min_closing_usd < 0 ? " neg" : "")}>{usd(s.min_closing_usd)}</td>
      <td className="num">{s.weeks_below_buffer.length}</td>
      <td className="num">{s.extra_funding_to_hold_buffer_usd == null ? "–" : usd(s.extra_funding_to_hold_buffer_usd)}</td>
      <td className="num">{s.monthly_instalment_usd ? usd(s.monthly_instalment_usd) : "–"}</td>
    </tr>
  );
  return (
    <>
      <h3 className="mini">{t("grn.cash")}</h3>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>{t("grn.scenario")}</th><th className="num">{t("grn.lowest")}</th><th className="num">{t("grn.weeksBelow")}</th>
              <th className="num">{t("grn.extra")}</th><th className="num">{t("grn.instalment")}</th>
            </tr>
          </thead>
          <tbody>
            {row(t("grn.noProject"), x.without_project)}
            {row(t("grn.cashFunded"), x.cash_funded)}
            {row(t("grn.loanFunded", { p: x.loan_funded.financed_pct, apr: x.loan_apr_pct.toFixed(2) }), x.loan_funded)}
          </tbody>
        </table>
      </div>
      <p className="note">{t("grn.cashNote", { w: x.capex_week, b: usd(x.buffer_usd), s: usd(x.weekly_net_saving_usd) })} {x.limitation}</p>
    </>
  );
}
