import { useState } from "react";
import { useCase, type CaseSnapshot } from "@/entities/case";
import { metricText } from "@/entities/funding";
import { StatusPill } from "@/entities/status";
import { HBars } from "@/shared/charts";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { human, pct, usd2 } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Empty, EngineNote, Loadable, PageHead, Panel, Scroll, useToast } from "@/shared/ui";
import { useAuth } from "../auth";
import { chooseOption, downloadPackPdf, preparePack, rejectPack, reopenPack, requestOtp, retryDoubleFinancing, tamperDraft } from "./api";
import { OtpDialog } from "./components/OtpDialog";
import { RejectDialog } from "./components/RejectDialog";
import type { OtpChallenge } from "./types";

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
  const [rejecting, setRejecting] = useState(false);

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
  const reject = async (reason: string) => {
    if (await act(() => rejectPack(reason))) {
      setRejecting(false);
      await refresh();
    }
  };

  let actions = null;
  if (preparer && state === "INVOICE_VERIFIED") actions = <Button variant="bridge" disabled={!chosenId} onClick={() => void prepare()}>{t("fund.prepare")}</Button>;
  if (preparer && state === "NEEDS_HUMAN" && pack.status === "REJECTED_BY_DIRECTOR") actions = <Button variant="bridge" onClick={() => void reopen()}>{t("fund.rework")}</Button>;
  if (approver && state === "AWAITING_APPROVAL") {
    actions = (
      <>
        <Button variant="bridge" onClick={() => void openOtp()}>{t("fund.approve")}</Button>
        <Button variant="danger" onClick={() => setRejecting(true)}>{t("fund.reject")}</Button>
      </>
    );
  }

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
        <Panel title={t("col.total")}>
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
      {pack.pack_id ? (
        <div className="grid2">
          <Panel title={`Pack ${pack.pack_id}`} sub={<><StatusPill status={pack.status} /> {pack.prepared_by || ""}{pack.approved_by ? " → " + pack.approved_by : ""}</>}>
            <table>
              <tbody>
                {pack.locked_metrics.map((m) => (
                  <tr key={m.label}><td>{m.label}</td><td className="num">{metricText(m, t)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="hashline" style={{ marginTop: 10 }}>action <span className="mono">{pack.action_hash}</span></p>
            <div className="row" style={{ marginTop: 10 }}>
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
      {["SUBMITTED", "FUNDED", "REJECTED"].includes(state) && (
        <Panel title={t("fund.lender")} sub={<><StatusPill status={lender.status} /> {lender.reviewer || ""}</>}>
          {lender.note && <p>{lender.note}</p>}
          <ul className="list small">
            {lender.history.map((h, i) => (
              <li key={i}>{human(h.event)}{h.by ? " · " + h.by : ""}{h.note ? ": " + h.note : ""}</li>
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
      <RejectDialog open={rejecting} onClose={() => setRejecting(false)} onSubmit={(reason) => void reject(reason)} />
    </>
  );
}
