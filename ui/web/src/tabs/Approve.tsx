import { useState } from "react";
import { api } from "../api";
import type { Snapshot } from "../types";
import { OtpDialog } from "../components/OtpDialog";
import { Button, Empty, Notice, Section, Status } from "../components/common";
import { amount, head, pct, usd } from "../format";

function formatMetric(unit: string, value: number): string {
  if (unit === "USD") return usd(value, true);
  if (unit === "%") return pct(value);
  if (unit === "week") return `Week ${amount(value)}`;
  return `${amount(value, !Number.isInteger(value))} ${unit}`;
}

interface Props {
  snap: Snapshot;
  onSnapshot: (snap: Snapshot) => void;
  onPrepare: () => Promise<void>;
}

export function Approve({ snap, onSnapshot, onPrepare }: Props) {
  const [dialog, setDialog] = useState(false);
  const [retry, setRetry] = useState<{ blocked: boolean; message: string } | null>(null);
  const [tamper, setTamper] = useState<{ ok: boolean; offending: string[]; message: string } | null>(null);
  const pack = snap.pack;
  const chosen = snap.selected_option_id !== null;
  const stage = pack.status === "SUBMITTED" ? 4 : pack.status === "AWAITING_APPROVAL" ? 3 : chosen ? 2 : 1;
  const steps = ["Option chosen", "Pack drafted", "Awaiting approval", "Submitted"];

  return (
    <>
      <div className="stepper">
        {steps.map((title, i) => {
          const n = i + 1;
          const cls = pack.status === "SUBMITTED" || n < stage ? "done" : n === stage ? "now" : "";
          return (
            <div className={`step ${cls}`} key={title}>
              <div className="n">Step {n}</div>
              <div className="t">{title}</div>
            </div>
          );
        })}
      </div>

      {snap.meta.last_error && <Notice tone="bad" title="Not possible">{snap.meta.last_error}</Notice>}

      {pack.status === "NOT_STARTED" ? (
        <Section title="Funding pack">
          <p className="lede">
            Preparing the pack freezes the figures, fingerprints every source document, drafts the cover letter and checks that every number in it is one of the frozen figures.
          </p>
          {!chosen && <Empty>Choose an option on the Compare and Choose tab first.</Empty>}
          <div className="actions">
            <Button primary disabled={!chosen} onClick={onPrepare}>Prepare pack</Button>
          </div>
        </Section>
      ) : (
        <>
          <div className="grid2" style={{ marginTop: 32 }}>
            <Section id="metrics" title="Numbers locked into the pack" aside={<span className="mono muted">{pack.pack_id}</span>}>
              <table>
                <tbody>
                  {pack.locked_metrics.map((m) => (
                    <tr key={m.key}><td>{m.label}</td><td className="num right">{formatMetric(m.unit, m.value)}</td></tr>
                  ))}
                </tbody>
              </table>
            </Section>
            <Section id="letter" title="Cover letter" aside={
              pack.number_check && (
                <Status text={pack.number_check.ok ? "Number check passed" : "Number check failed"} tone={pack.number_check.ok ? "pos" : "neg"} solid />
              )
            }>
              <div className="letter">{pack.letter_text}</div>
            </Section>
          </div>

          <Section id="approval" title="Approval">
            <table>
              <tbody>
                <tr><td className="muted">Action hash</td><td className="num right">{pack.action_hash ? head(pack.action_hash, 24) : "n/a"}</td></tr>
                <tr><td className="muted">PDF funding pack</td><td className="right">{pack.pdf_path ? <a className="textbtn" href="/api/pack/pdf" target="_blank" rel="noreferrer">Download the PDF</a> : <span className="muted">Created when the pack is prepared</span>}</td></tr>
                {pack.lender_ref && <tr><td className="muted">Lender reference (MOCK)</td><td className="num right">{pack.lender_ref}</td></tr>}
              </tbody>
            </table>
            {pack.registry_block && (
              <Notice tone="good" title="Registered">
                Block {pack.registry_block.block_index} written to the invoice registry
                <div className="num muted" style={{ fontSize: 12, marginTop: 4 }}>
                  key {head(String(pack.registry_block.invoice_key), 16)} · block hash {head(String(pack.registry_block.block_hash), 16)}
                </div>
              </Notice>
            )}
            {pack.status === "AWAITING_APPROVAL" && (
              <div className="actions">
                <Button primary onClick={() => setDialog(true)}>Approve and submit</Button>
              </div>
            )}
          </Section>

          <Section id="safeguards" title="Try to break it" aside={<span className="label">Both attempts are refused and logged</span>}>
            <p className="lede">
              These buttons try to do the wrong thing on purpose, to show the controls working. Neither can succeed, and each leaves a line in the audit log.
            </p>
            <div className="actions" style={{ marginTop: 0 }}>
              <Button onClick={async () => { setRetry(await api.retryDoubleFinancing()); onSnapshot(await api.getSnapshot()); }}>Try to finance INV-1030 again</Button>
              <Button onClick={async () => { setTamper(await api.tamperDraft()); onSnapshot(await api.getSnapshot()); }}>Tamper with the draft</Button>
            </div>
            {retry && (
              <Notice tone={retry.blocked ? "bad" : undefined} title={retry.blocked ? "DoubleFinancingBlocked" : "Nothing to retry"}>{retry.message}</Notice>
            )}
            {tamper && (
              <Notice tone={tamper.ok ? "good" : "bad"} title={tamper.ok ? "Draft accepted" : `Draft rejected: ${tamper.offending.join(", ")}`}>
                {tamper.message}
              </Notice>
            )}
          </Section>
        </>
      )}

      {dialog && (
        <OtpDialog
          onClose={() => setDialog(false)}
          onApproved={(s) => { onSnapshot(s); setDialog(false); }}
          onFailed={onSnapshot}
        />
      )}
    </>
  );
}
