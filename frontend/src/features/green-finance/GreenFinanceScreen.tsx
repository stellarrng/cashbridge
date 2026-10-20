import { useState } from "react";
import { DonutChart } from "@/shared/charts";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { human, usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, EngineNote, Kpi, Kpis, Loadable, Note, PageHead } from "@/shared/ui";
import { fetchEconomics, fetchGreenProjects, requestReview, type GreenEconomics, type GreenProject } from "./api";

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
  const [eco, setEco] = useState<GreenEconomics | null>(null);
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
                  <td>{x.status === "missing" ? <span className="pill bad">missing</span> : <span className="pill warn">{human(x.status)}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DonutChart
          center={p.documentation_completeness_pct + "%"}
          centerSub="evidence"
          parts={[
            { label: "provided", value: provided, color: "var(--good)" },
            { label: "missing", value: p.evidence.length - provided, color: "var(--deficit)" },
          ]}
        />
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <Button small variant="ghost" onClick={async () => { const x = await act(() => fetchEconomics(p.project_id)); if (x) setEco(x); }}>Payback @ $0.12/kWh</Button>
        <Button small variant={pending ? "ghost" : "bridge"} disabled={pending} onClick={async () => { if (await act(() => requestReview(p.project_id))) onReviewed(); }}>
          {pending ? "Review requested" : "Request internal review"}
        </Button>
      </div>
      <div>
        {eco && (
          <>
            <div className="kpis cards" style={{ marginTop: 12 }}>
              <Kpi label="Net savings / yr" value={usd(eco.estimated_net_savings_usd_per_year)} />
              <Kpi label="Simple payback" value={eco.simple_payback_years == null ? "–" : eco.simple_payback_years + " y"} />
            </div>
            <Note>{eco.limitation}</Note>
          </>
        )}
      </div>
    </section>
  );
}
