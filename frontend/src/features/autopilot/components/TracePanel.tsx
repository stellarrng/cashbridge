import type { AutopilotRun } from "@/entities/autopilot";
import { useI18n } from "@/shared/i18n";
import { BulletList, Note, Panel } from "@/shared/ui";

/** What the agent did, step by step, with links to the evidence behind each step. */
export function TracePanel({ run, onJump }: { run: AutopilotRun; onJump: (evidenceId: string) => void }) {
  const { t } = useI18n();
  return (
    <Panel title={t("ap.did")} sub={t("ap.didSub")}>
      <ol className="trace">
        {run.steps.map((s) => (
          <li key={s.n} className={s.status}>
            <span className="n">{s.n}</span>
            <div>
              <span className="tool">{s.tool}</span>
              <h3>{s.result}</h3>
              <p className="why">{s.why}</p>
              {s.evidence.length > 0 && (
                <div className="evs">
                  {s.evidence.map((id) => (
                    <button key={id} type="button" className="ev-link" onClick={() => onJump(id)}>{id}</button>
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
      {run.refused_proposals.length > 0 && (
        <div className="caution">
          <b>{t("ap.refused")}</b>
          <ul className="list">
            {run.refused_proposals.map((x, i) => <li key={i}>{x.proposed}: {x.reason}</li>)}
          </ul>
        </div>
      )}
      {run.goal_injection_detected && <Note>{t("ap.injected")}</Note>}
      <h3 className="mini">{t("ap.guardrails")}</h3>
      <BulletList small items={run.guardrails} />
    </Panel>
  );
}
