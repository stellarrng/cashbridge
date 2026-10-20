import { useCase, type CaseSnapshot } from "@/entities/case";
import { StatusPill } from "@/entities/status";
import { DonutChart, HBars } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { human, sentence, usd, usd2 } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { EngineNote, Loadable, Meter, Note, PageHead, Panel, Scroll } from "@/shared/ui";

export default function ReceivablesScreen(_: ScreenProps) {
  const { snapshot, error } = useCase();
  return <Loadable data={snapshot} error={error}>{(s) => <Receivables s={s} />}</Loadable>;
}

function Receivables({ s }: { s: CaseSnapshot }) {
  const { t } = useI18n();
  const wire = s.reconciliation.featured_wire;
  const recon = s.reconciliation.rows;
  const reconCount = (status: string) => recon.filter((r) => r.status === status).length;
  const checkCount = (status: string) => s.verification.filter((v) => v.status === status).length;

  return (
    <>
      <PageHead title={t("evd.title")} lede={t("evd.lede")} />
      <EngineNote />
      <div className="grid3">
        <Panel title={t("evd.recon")}>
          <DonutChart
            center={`${reconCount("BOOKED")}/${recon.length}`}
            centerSub={t("st.BOOKED")}
            parts={[
              { label: t("st.BOOKED"), value: reconCount("BOOKED"), color: "var(--good)" },
              { label: t("st.NEEDS_HUMAN"), value: reconCount("NEEDS_HUMAN"), color: "var(--risk)" },
            ]}
          />
        </Panel>
        <Panel title={t("ov.checks")}>
          <DonutChart
            center={String(s.verification.length)}
            centerSub="Invoices"
            parts={[
              { label: t("st.ELIGIBLE"), value: checkCount("ELIGIBLE"), color: "var(--good)" },
              { label: t("st.FLAGGED"), value: checkCount("FLAGGED"), color: "var(--risk)" },
              { label: t("st.BLOCKED"), value: checkCount("BLOCKED"), color: "var(--deficit)" },
            ]}
          />
        </Panel>
        {wire && (
          <Panel title={t("evd.wire")}>
            <p>{wire.txn_id}: <b>{usd2(wire.received)}</b></p>
            <HBars
              items={[
                ...wire.invoices.map((i) => ({ label: i.id, value: i.amount, display: usd(i.amount), cls: "cb-accent" })),
                { label: "Gap", value: wire.gap, display: usd2(wire.gap), cls: "cb-muted" },
              ]}
            />
            <Note>{wire.explanation}</Note>
          </Panel>
        )}
      </div>
      <Panel title={t("evd.recon")}>
        <Scroll>
          <table>
            <thead>
              <tr><th>Txn</th><th className="num">{t("col.amount")}</th><th>Invoices</th><th>{t("col.status")}</th><th></th></tr>
            </thead>
            <tbody>
              {recon.map((r) => (
                <tr key={r.txn_id}>
                  <td>{r.txn_id}<div className="muted small">{r.reference}</div></td>
                  <td className="num">{r.currency} {Number(r.amount).toLocaleString()}</td>
                  <td>{r.matched_invoices.join(", ") || "–"}</td>
                  <td><StatusPill status={r.status} /></td>
                  <td className="small">{r.reason || r.gap_reason || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
      </Panel>
      <Panel title={t("evd.match")}>
        <Scroll>
          <table>
            <thead>
              <tr><th>Invoice</th><th>{t("cash.col.buyer")}</th><th className="num">{t("col.amount")}</th><th>Due</th><th>3-way</th><th>Registry</th><th></th></tr>
            </thead>
            <tbody>
              {s.verification.map((v) => (
                <tr key={v.invoice_id}>
                  <td>{v.invoice_id}</td>
                  <td>{v.buyer}</td>
                  <td className="num">{v.currency} {Number(v.amount).toLocaleString()}</td>
                  <td>{v.due_date}</td>
                  <td><StatusPill status={v.status} /></td>
                  <td className="small">{sentence(human(v.registry_status))}</td>
                  <td className="small">{v.differences.join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
      </Panel>
      <div className="grid2">
        <Panel title={t("evd.scans")} sub={t("evd.scansSub")}>
          <table>
            <tbody>
              {s.scans.map((d) => (
                <tr key={d.doc_id}>
                  <td>{d.doc_id}<div className="muted small">{sentence(human(d.doc_type))}</div></td>
                  <td><StatusPill status={d.status} /></td>
                  <td><Meter ratio={d.min_confidence} low={d.min_confidence < 0.85} tip={Number(d.min_confidence).toFixed(2)} /></td>
                  <td className="small">{d.reason || (d.matches_record ? "matches the record" : d.differences.join("; "))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title={t("evd.held")} sub={t("evd.heldSub")}>
          {s.alerts.length ? (
            s.alerts.map((a) => (
              <div key={a.id} className={"flag" + (a.severity === "critical" || a.severity === "high" ? " high" : "")}>
                <b>{a.type}: {a.subject}</b>
                <div className="small mono">{a.sender}</div>
                <ul className="list small">{(a.reasons || []).map((x, i) => <li key={i}>{x}</li>)}</ul>
                <p className="small">{a.action_hint || ""}</p>
              </div>
            ))
          ) : (
            <p className="muted">–</p>
          )}
        </Panel>
      </div>
    </>
  );
}
