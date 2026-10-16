import type { Snapshot } from "../types";
import { Empty, Notice, Section, Status } from "../components/common";
import { amount, dayMonth, label, usd } from "../format";

export function Prove({ snap }: { snap: Snapshot }) {
  const wire = snap.reconciliation.featured_wire;
  return (
    <>
      <Section id="money" title="Money received" aside={<span className="label">Bank credits matched to invoices</span>}>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Transaction</th><th>Date</th><th className="num">Amount</th><th>Reference</th><th>Tier</th><th>Matched</th><th className="num">Gap USD</th><th className="num">Confidence</th><th>Status</th></tr>
            </thead>
            <tbody>
              {snap.reconciliation.rows.map((r) => (
                <tr key={r.txn_id}>
                  <td className="num">{r.txn_id}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{dayMonth(r.date)}</td>
                  <td className="num">{r.currency} {amount(r.amount)}</td>
                  <td className="num">{r.reference}</td>
                  <td className="num">{r.tier ?? "none"}</td>
                  <td className="num">{r.matched_invoices.join(", ") || "none"}</td>
                  <td className="num">{r.gap === null ? "n/a" : amount(r.gap)}</td>
                  <td className="num">{amount(r.confidence, true)}</td>
                  <td>
                    <Status text={r.status === "BOOKED" ? "Booked" : "Needs human"} tone={r.status === "BOOKED" ? "pos" : ""} solid={r.status === "BOOKED"} />
                    {r.status !== "BOOKED" && r.reason && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>{r.reason}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="grid2 even">
        <Section id="wire" title="How the big wire was matched">
          {wire ? (
            <>
              <p className="lede">
                The bank reference named one invoice, but its amount did not match, so the exact match failed. The subset-sum search then
                tried every combination of this buyer's open invoices and found exactly one that fits.
              </p>
              <table>
                <tbody>
                  {wire.invoices.map((i) => (
                    <tr key={i.id}><td className="num" style={{ textAlign: "left" }}>{i.id}</td><td className="num right">{usd(i.amount)}</td></tr>
                  ))}
                  <tr><td><strong>Invoices total</strong></td><td className="num right"><strong>{usd(wire.invoice_total)}</strong></td></tr>
                  <tr><td>Received on {wire.txn_id}</td><td className="num right">{usd(wire.received)}</td></tr>
                  <tr><td className="pos">Difference, booked as {label(wire.gap_reason).toLowerCase()}</td><td className="num right pos">{usd(wire.gap)}</td></tr>
                </tbody>
              </table>
              <p className="muted" style={{ marginTop: 12 }}>{wire.explanation}</p>
            </>
          ) : (
            <Empty>No multi-invoice wire needed matching in this run.</Empty>
          )}
        </Section>

        <Section id="emails" title="Suspicious emails" aside={<span className="label">Read as data, never as instructions</span>}>
          {snap.alerts.length === 0 && <Empty>No alerts. Inbox messages are scanned as data and never as instructions.</Empty>}
          {snap.alerts.map((a) => (
            <Notice key={a.id} tone={a.severity === "critical" ? "bad" : undefined} title={`${a.type === "BEC" ? "Blocked" : "Flagged"}: ${a.subject}`}>
              <div className="num" style={{ fontSize: 12 }}>{a.sender}</div>
              <ul style={{ margin: "8px 0", paddingLeft: 18 }}>
                {a.reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
              <div className="muted">{a.action_hint}</div>
            </Notice>
          ))}
        </Section>
      </div>

      <Section id="invoices" title="Which invoices are safe to finance" aside={<span className="label">Purchase order, invoice and bill of lading must agree</span>}>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Invoice</th><th>Buyer</th><th className="num">Amount</th><th>Due</th><th>Result</th><th>Registry</th><th>Tax ID</th></tr>
            </thead>
            <tbody>
              {snap.verification.map((v) => (
                <tr key={v.invoice_id}>
                  <td className="num">{v.invoice_id}</td>
                  <td>{v.buyer}</td>
                  <td className="num">{v.currency} {amount(v.amount)}</td>
                  <td>{dayMonth(v.due_date)}</td>
                  <td>
                    <Status text={label(v.status)} tone={v.status === "ELIGIBLE" ? "pos" : "neg"} solid={v.status === "ELIGIBLE"} />
                    {v.differences.map((d) => <div key={d} className="neg" style={{ fontSize: 12, marginTop: 2 }}>{d}</div>)}
                  </td>
                  <td>{v.registry_status === "REGISTERED" ? "Registered" : "No entry"}</td>
                  <td className={v.tax_id_valid ? "" : "neg"}>{v.tax_id_valid ? "Valid" : "Invalid"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}
