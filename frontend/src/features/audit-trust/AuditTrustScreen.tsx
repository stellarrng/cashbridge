import { resetDemo, useCase, type CaseSnapshot } from "@/entities/case";
import { StatusPill } from "@/entities/status";
import { StackBar } from "@/shared/charts";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { human } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Kpi, Kpis, PageHead, Panel, Scroll } from "@/shared/ui";
import { useAuth } from "../auth";
import { fetchScorecard, tamperDemo, verifyChain, type Scorecard } from "./api";

export default function AuditTrustScreen(_: ScreenProps) {
  const { user } = useAuth();
  return user.portal === "sme" ? <SmeAudit /> : <Audit snapshot={null} refresh={async () => undefined} />;
}

/** The SME side adds the live audit chain, registry and privacy preview from the case snapshot. */
function SmeAudit() {
  const { snapshot, refresh } = useCase();
  return <Audit snapshot={snapshot} refresh={refresh} />;
}

function Audit({ snapshot, refresh }: { snapshot: CaseSnapshot | null; refresh: () => Promise<unknown> }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const act = useAct();
  // A missing scorecard is not an error: the rest of the page still works.
  const score = useAsync(() => fetchScorecard().catch(() => null), []);
  const sme = snapshot !== null;
  const ev = snapshot?.evidence;

  const decisions: Record<string, number> = {};
  ev?.audit_tail.forEach((a) => { decisions[a.decision] = (decisions[a.decision] || 0) + 1; });

  const actions = sme ? (
    <>
      <Button variant="ghost" onClick={() => void act(verifyChain, (r) => (r.ok ? `OK: ${r.lines_checked}` : `Broken at ${r.broken_seq}`))}>{t("tr.verify")}</Button>
      <Button variant="ghost" onClick={() => void act(tamperDemo, (r) => (r.ok ? "Unexpected: not detected" : `Edit detected at line ${r.broken_seq} (temporary copy)`))}>{t("tr.tamper")}</Button>
      {can("demo:reset") && (
        <Button variant="danger" onClick={async () => { if (window.confirm(t("tr.reset") + "?") && (await act(resetDemo, "OK"))) await refresh(); }}>{t("tr.reset")}</Button>
      )}
    </>
  ) : undefined;

  return (
    <>
      <PageHead title={t("tr.title")} lede={t("tr.lede")} actions={actions} />
      {score.data && <ScorecardView sc={score.data} />}
      {sme && snapshot && ev && (
        <div className="grid2">
          <Panel title="Audit log" sub={`${ev.chain_ok ? "hash chain intact" : "broken at " + ev.broken_seq} · ${ev.lines_checked}`}>
            <StackBar
              parts={Object.entries(decisions).map(([k, v]) => ({
                label: human(k),
                value: v,
                cls: k === "ALLOWED" || k === "APPROVED" ? "cb-good" : k === "AWAITING_APPROVAL" ? "cb-risk" : "cb-neg",
              }))}
            />
            <Scroll>
              <table>
                <tbody>
                  {ev.audit_tail.slice().reverse().map((a) => (
                    <tr key={a.seq}>
                      <td>{a.seq}</td><td>{a.agent}</td><td className="small">{a.tool}</td><td className="small">{a.tier}</td><td><StatusPill status={a.decision} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Scroll>
          </Panel>
          <Panel title="Invoice registry" sub="this installation only">
            {ev.registry_blocks.length ? (
              <table>
                <tbody>
                  {ev.registry_blocks.map((b) => (
                    <tr key={b.block_index}><td>#{b.block_index}</td><td className="mono">{String(b.block_hash).slice(0, 24)}…</td><td>{b.lender_ref || ""}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">–</p>
            )}
            <h2 style={{ marginTop: 18 }}>Privacy</h2>
            <p className="sub">{snapshot.pii_inspector.note}</p>
            <p className="small mono">{snapshot.pii_inspector.before}</p>
            <p className="small mono" style={{ marginTop: 6 }}>{snapshot.pii_inspector.after}</p>
          </Panel>
        </div>
      )}
    </>
  );
}

function ScorecardView({ sc }: { sc: Scorecard }) {
  const s = sc.summary;
  return (
    <>
      <Kpis>
        <Kpi highlight label="Security cases" value={`${s.security.passed}/${s.security.total}`} />
        <Kpi tone="pos" label="Agent scenarios" value={`${s.agent.passed}/${s.agent.total}`} />
        <Kpi label="Brier: model" value={s.model.brier_model} />
        <Kpi label="Brier: baseline" value={s.model.brier_baseline} />
      </Kpis>
      <div className="grid2">
        <Panel title="Security & compliance" sub={`make trust · ${sc.generated_at}`}>
          <table>
            <tbody>
              {sc.security.map((c) => (
                <tr key={c.id}><td className="mono">{c.id}</td><td>{c.title}</td><td>{c.passed ? <span className="pill ok">pass</span> : <span className="pill bad">fail</span>}</td></tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Agent scenarios" sub={sc.model.caveat}>
          <table>
            <tbody>
              {sc.agent.map((c) => (
                <tr key={c.id}>
                  <td className="mono">{c.id}</td>
                  <td>{c.title}<div className="muted small">{c.got || ""}</div></td>
                  <td>{c.passed ? <span className="pill ok">pass</span> : <span className="pill bad">fail</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </>
  );
}
