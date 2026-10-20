import { EVIDENCE_ORDER, EvidenceTag } from "@/entities/status";
import { StackBar } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { Caution, Panel } from "@/shared/ui";
import type { BankCase } from "../../types";

// What the lender cannot check for itself is listed first.
const UNVERIFIED_FIRST = ["NOT_VERIFIABLE_HERE", "NEEDS_HUMAN", "ASSUMPTION"];
const rank = (status: string) => (UNVERIFIED_FIRST.includes(status) ? 1 : 0);

export function AgentEvidence({ autopilot }: { autopilot: NonNullable<BankCase["autopilot"]> }) {
  const { t } = useI18n();
  const counts = autopilot.evidence_counts;
  return (
    <Panel title={t("bk.agent")} sub={`Run ${autopilot.run_id}`}>
      {counts && <StackBar parts={EVIDENCE_ORDER.map((s) => ({ label: t("ev." + s), value: counts[s] || 0, cls: "evc-" + s }))} />}
      <table>
        <tbody>
          {autopilot.evidence
            .slice()
            .sort((a, b) => rank(b.status) - rank(a.status))
            .map((e) => (
              <tr key={e.id}>
                <td>{e.claim}<div className="muted small">{e.note || ""}</div></td>
                <td><EvidenceTag status={e.status} /></td>
              </tr>
            ))}
        </tbody>
      </table>
      {autopilot.recommendation && <Caution title={t("ap.notFix")} items={autopilot.recommendation.what_would_change} />}
    </Panel>
  );
}
