import type { AutopilotRun } from "@/entities/autopilot";
import { EVIDENCE_ORDER, EvidenceTag } from "@/entities/status";
import { StackBar } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { usd2 } from "@/shared/lib/format";
import { Panel, Scroll } from "@/shared/ui";

export const evidenceRowId = (id: string) => "ev-row-" + id;

export function EvidenceRegister({ run, filter, onFilter }: { run: AutopilotRun; filter: string; onFilter: (f: string) => void }) {
  const { t } = useI18n();
  const counts = run.evidence_counts;

  return (
    <Panel title={t("ap.register")} sub={t("ap.registerSub", { n: run.evidence.length })} className="adv">
      <StackBar parts={EVIDENCE_ORDER.map((s) => ({ label: t("ev." + s), value: counts[s] || 0, cls: "evc-" + s }))} />
      <div className="filters">
        {["ALL", ...EVIDENCE_ORDER].map((key) => (
          <button key={key} type="button" aria-pressed={filter === key} onClick={() => onFilter(key)}>
            {key === "ALL" ? t("ap.all") : t("ev." + key)} {key === "ALL" ? run.evidence.length : counts[key] || 0}
          </button>
        ))}
      </div>
      <Scroll>
        <table id="evTable">
          <thead>
            <tr><th>ID</th><th>{t("ap.claim")}</th><th>{t("ap.value")}</th><th>{t("ap.status")}</th></tr>
          </thead>
          <tbody>
            {run.evidence.map((e) => (
              <tr key={e.id} id={evidenceRowId(e.id)} hidden={filter !== "ALL" && e.status !== filter}>
                <td>{e.id}</td>
                <td>
                  {e.claim}
                  {e.note && <div className="muted small">{e.note}</div>}
                  <div className="muted small mono">{e.source}</div>
                </td>
                <td>
                  {typeof e.value === "number" ? (Math.abs(e.value) >= 1000 ? usd2(e.value) : e.value) : <span className={String(e.value).length > 40 ? "mono" : ""}>{e.value}</span>}
                </td>
                <td><EvidenceTag status={e.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Scroll>
    </Panel>
  );
}
