import { useState } from "react";
import { api } from "../api";
import type { Snapshot } from "../types";
import { Button, Empty, Notice, Section, decisionTone } from "../components/common";
import { head } from "../format";

export function Evidence({ snap }: { snap: Snapshot }) {
  const [verify, setVerify] = useState<{ ok: boolean; broken_seq: number | null; lines_checked: number } | null>(null);
  const [tamper, setTamper] = useState<{ ok: boolean; broken_seq: number | null; lines_checked: number; note: string } | null>(null);
  const ev = snap.evidence;
  return (
    <>
      <Section id="audit" title="Audit log" aside={<span className="label">{ev.lines_checked} lines · tamper-evident</span>}>
        <p className="lede">
          Every gatekeeper decision is one line. Each line stores the hash of the line before it, so editing or removing any earlier
          line breaks every line after it.
        </p>
        <div className="scroll">
          <table>
            <thead><tr><th className="num">Seq</th><th>Time</th><th>Agent</th><th>Tool</th><th>Tier</th><th>Decision</th><th>Reason</th></tr></thead>
            <tbody>
              {[...ev.audit_tail].reverse().map((r) => (
                <tr key={r.seq}>
                  <td className="num">{r.seq}</td><td className="num">{r.time}</td><td>{r.agent}</td>
                  <td className="num" style={{ textAlign: "left" }}>{r.tool}</td><td className="num" style={{ textAlign: "left" }}>{r.tier.slice(0, 2)}</td>
                  <td className={`num ${decisionTone(r.decision)}`} style={{ textAlign: "left" }}>{r.decision.replace("_", " ")}</td>
                  <td className="muted">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="actions">
          <Button onClick={async () => setVerify(await api.verifyChain())}>Verify chain</Button>
          <Button onClick={async () => setTamper(await api.tamperDemo())}>Tamper demo (temporary copy)</Button>
        </div>
        {verify && (
          <Notice tone={verify.ok ? "good" : "bad"} title={verify.ok ? "Chain intact" : `Chain broken at line ${verify.broken_seq}`}>
            {verify.lines_checked} lines checked.
          </Notice>
        )}
        {tamper && (
          <Notice tone="bad" title={`One line edited: the chain breaks at line ${tamper.broken_seq}`}>
            Verification of the edited copy fails after {tamper.lines_checked} lines. {tamper.note}; the real log is untouched.
          </Notice>
        )}
        <p className="muted" style={{ marginTop: 12 }}>
          Honest limit: someone with write access could rewrite the whole file. Anchoring the head hash in git is the only protection.
        </p>
      </Section>

      <Section id="registry" title="Invoice registry" aside={<span className="label">Stops the same invoice being financed twice</span>}>
        {ev.registry_blocks.length === 0 ? (
          <Empty>No invoice has been financed yet. A block is written when a pack is submitted.</Empty>
        ) : (
          <div className="scroll">
            <table>
              <thead><tr><th className="num">Block</th><th>Invoice key</th><th>Bundle hash</th><th>Lender ref</th><th>Block hash</th></tr></thead>
              <tbody>
                {ev.registry_blocks.map((b) => (
                  <tr key={String(b.block_index)}>
                    <td className="num">{b.block_index}</td><td className="num">{head(String(b.invoice_key), 14)}</td>
                    <td className="num">{head(String(b.document_bundle_sha256), 14)}</td><td className="num">{b.lender_ref}</td>
                    <td className="num">{head(String(b.block_hash), 14)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section id="eval" title="Evaluation">
        {ev.eval === null ? (
          <Empty>Task-by-task results against an LLM-only baseline appear here once the evaluation harness has run.</Empty>
        ) : (
          <table>
            <thead><tr><th>Task</th><th>CashBridge</th><th>Baseline</th><th className="num">Invented numbers</th></tr></thead>
            <tbody>
              {ev.eval.rows.map((r) => (
                <tr key={r.task}>
                  <td>{r.task}</td><td className={r.cashbridge_pass ? "pos" : "neg"}>{r.cashbridge_pass ? "Pass" : "Fail"}</td>
                  <td>{r.baseline_pass === null ? "Skipped" : r.baseline_pass ? "Pass" : "Fail"}</td><td className="num">{r.invented_numbers}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </>
  );
}
