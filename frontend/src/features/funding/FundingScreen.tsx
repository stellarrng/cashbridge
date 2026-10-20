import { useState } from "react";
import { useCase, type CaseSnapshot } from "@/entities/case";
import { metricText } from "@/entities/funding";
import { MetricLink, ProvenanceDialog, lineageUrl } from "@/entities/provenance";
import { StatusPill } from "@/entities/status";
import { HBars } from "@/shared/charts";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { human, pct, sentence, usd2 } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Empty, EngineNote, Kpi, Kpis, Loadable, PageHead, Panel, Scroll, useToast } from "@/shared/ui";
import { useAuth } from "../auth";
import { chooseOption, downloadPackPdf, fetchQuotes, fetchSchedules, preparePack, rejectPack, reopenPack, requestOtp, retryDoubleFinancing, tamperDraft, withdrawRelease } from "./api";
import { OtpDialog } from "./components/OtpDialog";
import { RejectDialog } from "./components/RejectDialog";
import type { FundingScheduleView, LenderQuotes, OtpChallenge } from "./types";

export default function FundingScreen(_: ScreenProps) {
  const { snapshot, error, refresh } = useCase();
  return <Loadable data={snapshot} error={error}>{(s) => <Funding s={s} refresh={refresh} />}</Loadable>;
}

function Funding({ s, refresh }: { s: CaseSnapshot; refresh: () => Promise<unknown> }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const act = useAct();
  const toast = useToast();
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null);
  const [reasonMode, setReasonMode] = useState<"reject" | "withdraw" | null>(null);
  const [provKey, setProvKey] = useState<string | null>(null);
  // Loaded after the case: they depend on the ranked options and the chosen product (null when unavailable).
  const schedules = useAsync(() => fetchSchedules().catch(() => ({}) as Record<string, FundingScheduleView>), [s.selected_option_id, s.meta.case_state]);
  const quotes = useAsync(() => fetchQuotes().catch(() => null as LenderQuotes | null), [s.selected_option_id, s.meta.case_state]);

  const pack = s.pack;
  const state = s.meta.case_state;
  const preparer = can("sme:prepare");
  const approver = can("sme:approve");
  const lender = s.lender_review;
  const opts = s.funding_options;
  const chosenId = s.selected_option_id;

  const openOtp = async () => {
    const ch = await act(requestOtp);
    if (ch) setChallenge(ch);
  };
  const choose = async (id: string) => {
    if (await act(() => chooseOption(id))) await refresh();
  };
  const prepare = async () => {
    const r = await act(preparePack);
    if (r) {
      if (r.meta.last_error) toast(r.meta.last_error, true);
      await refresh();
    }
  };
  const reopen = async () => {
    if (await act(reopenPack)) await refresh();
  };
  const sendReason = async (reason: string) => {
    const withdraw = reasonMode === "withdraw";
    if (await act(() => (withdraw ? withdrawRelease(reason) : rejectPack(reason)), t(withdraw ? "fund.withdrawn" : "fund.rejected"))) {
      setReasonMode(null);
      await refresh();
    }
  };

  let actions = null;
  if (preparer && state === "INVOICE_VERIFIED") actions = <Button variant="bridge" id="prep" disabled={!chosenId} onClick={() => void prepare()}>{t("fund.prepare")}</Button>;
  if (preparer && state === "NEEDS_HUMAN" && ["REJECTED_BY_DIRECTOR", "WITHDRAWN_BY_SME"].includes(pack.status)) {
    actions = <Button variant="bridge" id="reopen" onClick={() => void reopen()}>{t("fund.rework")}</Button>;
  }
  if (approver && state === "SUBMITTED") actions = <Button variant="ghost" id="withdrawBtn" onClick={() => setReasonMode("withdraw")}>{t("fund.withdraw")}</Button>;
  if (approver && state === "AWAITING_APPROVAL") {
    actions = (
      <>
        <Button variant="bridge" id="approveBtn" onClick={() => void openOtp()}>{t("fund.approve")}</Button>
        <Button variant="danger" id="rejectBtn" onClick={() => setReasonMode("reject")}>{t("fund.reject")}</Button>
      </>
    );
  }
  // The timeline of the chosen product, or of the best eligible lender product before one is chosen.
  const scheduleId = chosenId || opts.find((o) => o.eligible && ["factoring", "loan"].includes(o.type))?.id;
  const fs = scheduleId ? schedules.data?.[scheduleId] : undefined;
  const lq = quotes.data;

  return (
    <>
      <PageHead title={t("fund.title")} lede={t(preparer ? "fund.lede.prep" : "fund.lede.dir")} actions={actions} />
      <EngineNote />
      {s.meta.last_error && (
        <div className="decision warn">
          <div><h2>{t("fund.notDone")}</h2><p>{s.meta.last_error}</p></div>
        </div>
      )}
      <div className="grid2">
        <Panel title={t("ov.options")} sub={t("ov.optionsSub")}>
          <HBars
            items={opts.filter((o) => o.apr_pct != null).map((o) => ({
              label: t("opt." + o.type),
              value: o.apr_pct as number,
              display: pct(o.apr_pct, 2),
              cls: o.id === chosenId ? "cb-accent" : "cb-muted",
              strong: o.id === chosenId,
            }))}
          />
        </Panel>
        <Panel title={t("col.total")} sub={t("fund.totalSub")}>
          <HBars
            items={opts.filter((o) => o.cost_breakdown && o.cost_breakdown.total_usd != null).map((o) => ({
              label: t("opt." + o.type),
              value: o.cost_breakdown.total_usd as number,
              display: usd2(o.cost_breakdown.total_usd),
              cls: o.id === chosenId ? "cb-accent" : "cb-muted",
            }))}
          />
        </Panel>
      </div>
      <Panel title={t("fund.ways")}>
        <Scroll>
          <table>
            <thead>
              <tr>
                <th>{t("col.option")}</th>
                <th className="num">{t("col.amount")}</th>
                <th className="num">{t("col.apr")}</th>
                <th className="num">{t("col.total")}</th>
                <th>{t("col.status")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {opts.map((o) => (
                <tr key={o.id} className={o.id === chosenId ? "sel" : ""}>
                  <td>{o.name}<div className="muted small">{o.why_not_cheaper || ""}</div></td>
                  <td className="num">{o.amount_usd == null ? "–" : usd2(o.amount_usd)}</td>
                  <td className="num">{o.apr_pct == null ? "–" : pct(o.apr_pct, 2)}</td>
                  <td className="num">{o.cost_breakdown && o.cost_breakdown.total_usd != null ? usd2(o.cost_breakdown.total_usd) : "–"}</td>
                  <td>{o.eligible ? <StatusPill status="ELIGIBLE" /> : <span className="small muted">{o.ineligible_reason || ""}</span>}</td>
                  <td>
                    {preparer && o.eligible && state === "INVOICE_VERIFIED" && (
                      <Button small variant={o.id === chosenId ? "bridge" : "ghost"} onClick={() => void choose(o.id)}>
                        {t(o.id === chosenId ? "fund.chosen" : "fund.choose")}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
      </Panel>
      {lq && lq.quotes.length > 0 && (
        <Panel title={t("lq.title")} sub={lq.notice}>
          <Scroll>
            <table id="quoteTable">
              <thead>
                <tr><th>{t("lq.quote")}</th><th className="num">{t("col.amount")}</th><th className="num">{t("col.total")}</th><th>{t("lq.expires")}</th><th>{t("col.status")}</th></tr>
              </thead>
              <tbody>
                {lq.quotes.map((q) => (
                  <tr key={q.quote_id}>
                    <td>
                      <span className="mono">{q.quote_id}</span> · {q.provider_id}
                      <div className="small">
                        <span className={"pill " + (q.source_type === "simulated" ? "sim" : "warn")}>{q.source_type === "simulated" ? t("lq.simulated") : t("lq.issued", { e: q.environment })}</span> {q.label}
                      </div>
                    </td>
                    <td className="num">{usd2(Number(q.principal_usd))}</td>
                    <td className="num">{usd2(Number(q.total_cost_usd))}</td>
                    <td className="small">{q.expires_at.slice(0, 16).replace("T", " ")} UTC</td>
                    <td><StatusPill status={q.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </Panel>
      )}
      {pack.pack_id ? (
        <div className="grid2">
          <Panel title={`Pack ${pack.pack_id}`} sub={<><StatusPill status={pack.status} /> {pack.prepared_by || ""}{pack.approved_by ? " → " + pack.approved_by : ""}</>}>
            <table>
              <tbody>
                {pack.locked_metrics.map((m) => (
                  <tr key={m.label}><td>{m.label}</td><td className="num">{m.key ? <MetricLink label={metricText(m, t)} metricKey={m.key} onOpen={setProvKey} /> : metricText(m, t)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="hashline mt-2">action <span className="mono">{pack.action_hash}</span></p>
            <div className="row mt-2">
              <Button small variant="ghost" onClick={() => void act(() => downloadPackPdf(pack.pack_id as string))}>{t("fund.pdf")}</Button>
              {preparer && (
                <Button small variant="ghost" onClick={() => void act(tamperDraft, (r) => (r.ok ? "Unexpected: accepted" : `Rejected: ${r.offending.join(", ")} is not a locked figure`))}>
                  {t("fund.tamper")}
                </Button>
              )}
              {state === "SUBMITTED" && preparer && (
                <Button small variant="ghost" onClick={() => void act(retryDoubleFinancing, (r) => (r.blocked ? "Blocked: this invoice is already in the registry" : r.message ?? ""))}>
                  {t("fund.dupe")}
                </Button>
              )}
            </div>
          </Panel>
          <Panel title={t("fund.letter")} sub={t("fund.letterSub")}>
            <div className="letter">{pack.letter_text || ""}</div>
          </Panel>
        </div>
      ) : (
        <Empty title={t("fund.noPack")}>{t(preparer ? "next.run" : "next.prepare")}</Empty>
      )}
      {fs && (
        <Panel title={t("sched.title")} sub={<><span className="pill sim">{t("lbl.sim")}</span> {fs.label}</>}>
          <Kpis>
            <Kpi label={t("sched.drawdown")} value={fs.schedule.drawdown_date} />
            <Kpi label={t("sched.settle")} value={fs.schedule.expected_settlement_date} />
            <Kpi label={t("sched.days")} value={String(fs.schedule.days_financed)} />
            <Kpi label={t("sched.expected")} value={usd2(fs.expected_cost_usd)} />
          </Kpis>
          <Scroll>
            <table>
              <thead>
                <tr><th>{t("sched.scenario")}</th><th className="num">{t("col.total")}</th><th className="num">{t("sched.rebate")}</th><th className="num">{t("sched.repay")}</th><th>{t("sched.loss")}</th></tr>
              </thead>
              <tbody>
                {fs.scenarios.map((x) => (
                  <tr key={x.scenario}>
                    <td>{t("sched." + x.scenario)}</td>
                    <td className="num">{usd2(x.total_cost_usd)}</td>
                    <td className="num">{x.rebate_to_sme_usd != null ? usd2(x.rebate_to_sme_usd) : "–"}</td>
                    <td className="num">{x.sme_pays_factor_usd ? usd2(x.sme_pays_factor_usd) : "–"}</td>
                    <td className="small">{x.credit_loss_borne_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
          <ul className="list small">{fs.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        </Panel>
      )}
      {["SUBMITTED", "FUNDED", "REJECTED"].includes(state) && (
        <Panel title={t("fund.lender")} sub={<><StatusPill status={lender.status} /> {lender.reviewer || ""}</>}>
          {lender.note && <p>{lender.note}</p>}
          <ul className="list small">
            {lender.history.map((h, i) => (
              <li key={i}>{sentence(human(h.event))}{h.by ? " · " + h.by : ""}{h.note ? ": " + h.note : ""}</li>
            ))}
          </ul>
        </Panel>
      )}
      <OtpDialog
        challenge={challenge}
        onClose={() => setChallenge(null)}
        onApproved={async () => {
          setChallenge(null);
          toast(t("dec.SUBMITTED_TO_LENDER"));
          await refresh();
        }}
      />
      <RejectDialog open={reasonMode !== null} mode={reasonMode ?? "reject"} onClose={() => setReasonMode(null)} onSubmit={(reason) => void sendReason(reason)} />
      <ProvenanceDialog url={lineageUrl()} metricKey={provKey} onClose={() => setProvKey(null)} canPropose={preparer} canDecide={approver} />
    </>
  );
}
