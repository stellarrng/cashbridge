import { WeeklyCashChart } from "@/entities/forecast";
import { metricText } from "@/entities/funding";
import { StatusPill } from "@/entities/status";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { human, pct, usd, usd2 } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Empty, EngineNote, Kpi, Kpis, Loadable, Meter, PageHead, Panel, Scroll } from "@/shared/ui";
import { downloadCasePdf, fetchCase, recordDecision, verifyCase } from "../api";
import { AgentEvidence } from "./components/AgentEvidence";
import { DecisionPanel } from "./components/DecisionPanel";
import { VerificationPanel } from "./components/VerificationPanel";

const DECIDED = ["FUNDED_MOCK", "DECLINED"];

export default function CaseScreen({ arg }: ScreenProps) {
  const { t } = useI18n();
  if (!arg) return <Empty title={t("bk.empty")} />;
  return <CaseView packId={arg} />;
}

function CaseView({ packId }: { packId: string }) {
  const { t, has } = useI18n();
  const act = useAct();
  const kase = useAsync(() => fetchCase(packId), [packId]);

  return (
    <Loadable data={kase.data} error={kase.error}>
      {(c) => {
        const product = c.product;
        const inv = c.invoice;
        const review = c.review;
        const decided = DECIDED.includes(review.status);
        return (
          <>
            <PageHead
              title={c.company}
              lede={`${c.pack_id} · ${product.name || ""} · ${c.prepared_by} → ${c.approved_by} · ${c.lender_ref}`}
              actions={<Button variant="ghost" onClick={() => void act(() => downloadCasePdf(c.pack_id))}>{t("fund.pdf")}</Button>}
            />
            <EngineNote />
            <Kpis>
              <Kpi highlight label={t("bk.requested")} value={usd2(product.amount_usd)} />
              <Kpi label={t("col.apr")} value={pct(product.apr_pct, 2)} />
              <Kpi label={t("bk.pledged")} value={inv.invoice_no} />
              <Kpi label={t("bk.invValue")} value={usd(inv.amount_usd)} />
              <Kpi label={t("bk.ontime")} value={c.buyer_risk ? Math.round(c.buyer_risk.p_on_time * 100) + "%" : "–"} />
              <Kpi label={t("bk.reviewStatus")} tone={decided ? "pos" : "warn"} value={has("st." + review.status) ? t("st." + review.status) : human(review.status)} />
            </Kpis>
            <div className="grid2">
              <VerificationPanel
                verification={review.verification}
                onVerify={async () => { if (await act(() => verifyCase(c.pack_id))) await kase.reload(); }}
              />
              <DecisionPanel
                review={review}
                decided={decided}
                checklist={c.review_checklist}
                onDecide={async (decision, note) => {
                  if (await act(() => recordDecision(c.pack_id, decision, note), t("bk.record"))) await kase.reload();
                }}
              />
            </div>
            <div className="grid2">
              <Panel title={t("bk.metrics")}>
                <table>
                  <tbody>
                    {c.locked_metrics.map((m) => <tr key={m.label}><td>{m.label}</td><td className="num">{metricText(m, t)}</td></tr>)}
                  </tbody>
                </table>
                <p className="hashline" style={{ marginTop: 10 }}>bundle <span className="mono">{c.bundle_sha256}</span></p>
              </Panel>
              <Panel title={t("fund.letter")}><div className="letter">{c.letter_text}</div></Panel>
            </div>
            <Panel title={t("bk.invoice")} sub={<>{inv.buyer} · {inv.issue_date} → {inv.due_date} · 3-way {inv.three_way ? <StatusPill status={inv.three_way.status} /> : null}</>}>
              <Scroll>
                <table>
                  <tbody>
                    {inv.scans.map((sd) => (
                      <tr key={sd.doc_id}>
                        <td>{sd.doc_id}</td>
                        <td><StatusPill status={sd.status} /></td>
                        <td><Meter ratio={sd.min_confidence} tip={Number(sd.min_confidence).toFixed(2)} /></td>
                        <td className="small">{sd.matches_record ? "matches the record" : sd.differences.join("; ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
              <h3 className="mini">{t("bk.forecast")}</h3>
              <WeeklyCashChart weeks={c.forecast.weeks} />
            </Panel>
            {c.autopilot && <AgentEvidence autopilot={c.autopilot} />}
            <Panel title={t("bk.notShared")} className="flat">
              <ul className="list">{c.not_shared.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </Panel>
          </>
        );
      }}
    </Loadable>
  );
}


