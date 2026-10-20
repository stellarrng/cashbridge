import { useI18n } from "@/shared/i18n";
import { pp } from "@/shared/lib/format";
import { Panel, Scroll } from "@/shared/ui";
import { OperationsBenchmark, PlannerBenchmark } from "../components/BenchmarkPanels";
import { LearningPanel } from "../components/LearningPanel";
import type { IntelligenceData, IntelligencePlan } from "../types";

export function EvidenceTab({ data, plan, onChanged }: { data: IntelligenceData; plan: IntelligencePlan; onChanged: () => void }) {
  const { t } = useI18n();
  const wm = plan.world_model;
  const b = data.benchmark;
  return (
    <>
      <Panel title={t("core.wm")} sub={`${wm.paths} paths · seed ${wm.seed}`}>
        <p>
          <b className="mono">{wm.version}</b> <span className="pill">{wm.label}</span> · {t("core.memory")}: {data.learning.memory_chain_ok ? "hash chain intact" : "BROKEN"}
        </p>
      </Panel>
      {plan.similar_cases.length > 0 && (
        <Panel title={t("core.memory")} sub={t("core.memorySub")}>
          <Scroll>
            <table>
              <tbody>
                {plan.similar_cases.map((m) => (
                  <tr key={m.run_id}>
                    <td className="mono small">{m.run_id}<div><span className="pill">{m.source}</span></div></td>
                    <td>{m.plan}<div className="muted small">{m.lesson}</div></td>
                    <td>{pp(m.predicted_p_goal)}</td>
                    <td>
                      {m.goal_met ? (
                        <span className="pill ok">{t("core.met")}</span>
                      ) : (
                        <>
                          <span className="pill bad">{t("core.missed")}</span>
                          <div className="muted small">{m.primary_cause.replaceAll("_", " ")}</div>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </Panel>
      )}
      <LearningPanel data={data} hasPlan onChanged={onChanged} />
      {b && (
        <>
          <PlannerBenchmark b={b} />
          <OperationsBenchmark b={b} />
        </>
      )}
    </>
  );
}
