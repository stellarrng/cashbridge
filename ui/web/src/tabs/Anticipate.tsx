import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ScenarioKey, ScenarioParams, SimulateResult, Snapshot } from "../types";
import { AttributionBars } from "../components/AttributionBars";
import { CashChart } from "../components/CashChart";
import { Empty, Section, Status } from "../components/common";
import { amount, dayMonth, days, label, pct, usd } from "../format";

const CONTROLS: { key: ScenarioKey; title: string; unit: string; hint: string }[] = [
  { key: "dso_change_days", title: "Collection time (DSO)", unit: "days", hint: "Positive means buyers pay later" },
  { key: "deposit_pct", title: "Raw-timber deposit", unit: "%", hint: "Share of the new PO paid to the supplier up front" },
  { key: "tariff_shared_pct", title: "Tariff share conceded to US buyers", unit: "%", hint: "Applied to a hypothetical scenario tariff, not a current rate" },
  { key: "fx_change_pct", title: "FX move on JPY and CNY receivables", unit: "%", hint: "Warning only, not a hedging recommendation" },
];

export function Anticipate({ snap, onAsk }: { snap: Snapshot; onAsk: (text: string) => Promise<void> }) {
  const defaults = Object.fromEntries(
    Object.entries(snap.scenario_controls).map(([k, c]) => [k, c.default]),
  ) as ScenarioParams;
  const [params, setParams] = useState<ScenarioParams>(defaults);
  const [result, setResult] = useState<SimulateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const changed = (Object.keys(defaults) as ScenarioKey[]).some((k) => params[k] !== defaults[k]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!changed) {
      setResult(null);
      return;
    }
    timer.current = window.setTimeout(() => {
      api.simulate(params).then((r) => { setResult(r); setError(null); }).catch((e) => setError(e.message));
    }, 250);
    return () => window.clearTimeout(timer.current);
  }, [params, changed]);

  const shown = result?.forecast ?? snap.forecast;
  const shownShortfall = result ? result.kpis.shortfall_usd : snap.kpis.shortfall_usd;
  const delta = result?.delta;
  const weekText = (w: number | null | undefined) => (w === null || w === undefined ? "none" : `week ${w}`);

  return (
    <>
      <Section id="forecast" title="Thirteen weeks of cash" aside={<span className="label">Cash left at the end of each week, USD</span>}>
        <p className="lede">
          Each bar is the cash left at the end of a week. Expected payments are the invoice value times the chance it is paid on time,
          counted in the due week; the late share arrives four weeks later. Click a week to see its movements.
        </p>
        <CashChart weeks={snap.forecast.weeks} buffer={snap.forecast.buffer_usd} scenario={result ? result.forecast.weeks : null} />
      </Section>

      <div className="grid2">
        <Section id="causes" title="What causes the gap" aside={<span className="label">{result ? "Scenario" : "Base case"}</span>}>
          <AttributionBars items={shown.attribution} shortfall={shownShortfall} />
        </Section>

        <Section id="whatif" title="Try a scenario" aside={changed && <button className="linkbtn" onClick={() => setParams(defaults)}>Reset sliders</button>}>
          {CONTROLS.map(({ key, title, unit, hint }) => {
            const c = snap.scenario_controls[key];
            return (
              <div className="control" key={key}>
                <div className="row">
                  <span>{title}</span>
                  <span className="num">{params[key] > 0 && unit !== "days" ? "+" : ""}{params[key]} {unit}</span>
                </div>
                <input
                  type="range" min={c.min} max={c.max} step={c.step} value={params[key]}
                  onChange={(e) => setParams({ ...params, [key]: Number(e.target.value) })}
                />
                <div className="muted" style={{ fontSize: 12 }}>{hint}</div>
              </div>
            );
          })}
          {error && <div className="notice bad">{error}</div>}
          {delta && (
            <table style={{ marginTop: 16 }}>
              <thead><tr><th /><th className="num">Base</th><th className="num">Scenario</th></tr></thead>
              <tbody>
                <tr>
                  <td>First shortfall</td>
                  <td className="num">{weekText(delta.first_shortfall_week_before)}</td>
                  <td className={`num ${delta.first_shortfall_week_after === null ? "pos" : "neg"}`}>{weekText(delta.first_shortfall_week_after)}</td>
                </tr>
                <tr>
                  <td>Lowest closing balance</td>
                  <td className="num">{usd(delta.min_closing_before_usd)}</td>
                  <td className={`num ${delta.min_closing_after_usd < 0 ? "neg" : ""}`}>{usd(delta.min_closing_after_usd)}</td>
                </tr>
              </tbody>
            </table>
          )}
          <div className="ask" style={{ marginTop: 18 }}>
            <input
              value={question} placeholder="Or describe a scenario in words"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && question.trim()) { onAsk(question.trim()); setQuestion(""); } }}
            />
            <button onClick={() => { if (question.trim()) { onAsk(question.trim()); setQuestion(""); } }}>Send</button>
          </div>
        </Section>
      </div>

      <Section id="collections" title="Collections">
        {snap.collections.schedule.length === 0 && snap.collections.promises.length === 0 ? (
          <Empty>No reminders drafted yet. They appear here once the collections agent runs.</Empty>
        ) : (
          <div className="scroll">
            <table>
              <thead><tr><th>Invoice</th><th>Buyer</th><th>Stage</th><th>Scheduled</th><th>Status</th></tr></thead>
              <tbody>
                {snap.collections.schedule.map((r) => (
                  <tr key={r.invoice_id + r.stage}>
                    <td className="num" style={{ textAlign: "left" }}>{r.invoice_id}</td><td>{r.buyer}</td><td>{label(r.stage)}</td>
                    <td>{dayMonth(r.scheduled_date)}</td><td>{label(r.status)}</td>
                  </tr>
                ))}
                {snap.collections.promises.map((p) => (
                  <tr key={p.invoice_id + p.promised_date}>
                    <td className="num" style={{ textAlign: "left" }}>{p.invoice_id}</td><td>{p.buyer}</td><td>Buyer promise</td>
                    <td>{dayMonth(p.promised_date)}</td><td className="muted">“{p.source_text}”</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section id="buyerrisk" title="Buyer risk" aside={<span className="label">Who is most likely to pay late</span>}>
        {snap.buyer_risk.length === 0 ? (
          <Empty>There are no open invoices to assess.</Empty>
        ) : (
          <>
            <p className="lede">
              The chance each buyer pays on time is estimated from this company's own payment history. A buyer holding more than 40% of
              open invoices is a concentration risk, because one late payer can open a cash gap.
            </p>
            <div className="scroll">
              <table>
                <thead>
                  <tr><th>Buyer</th><th className="num">Share of open invoices</th><th className="num">Average days late</th><th className="num">Chance of on-time payment</th><th>Flag</th></tr>
                </thead>
                <tbody>
                  {snap.buyer_risk.map((b) => (
                    <tr key={b.buyer_id}>
                      <td>{b.buyer}{!b.has_history && <div className="muted" style={{ fontSize: 12.5 }}>No payment history yet: scored as the portfolio average</div>}</td>
                      <td className="num">{pct(b.share_of_receivables_pct)}</td>
                      <td className="num">{b.has_history ? days(b.avg_days_late) : "n/a"}</td>
                      <td className="num">{amount(b.p_on_time * 100)}%</td>
                      <td>{b.concentration_alert ? <Status text="Over 40% of open invoices" tone="neg" solid /> : <span className="muted">None</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <details style={{ marginTop: 18 }}>
              <summary className="textbtn" style={{ cursor: "pointer", display: "inline-block" }}>How is this estimated?</summary>
              <p className="lede">
                {snap.risk_model.method}, fitted on {snap.risk_model.training_rows} invoices ({amount(snap.risk_model.on_time_rate_pct, true)}% were paid on time).
                {" "}{snap.risk_model.on_time_definition}. A negative number lowers the chance of paying on time; "size vs usual" is how big the
                invoice is compared with that buyer's usual invoice.
              </p>
              <table>
                <thead><tr><th>Input</th><th className="num">Weight</th></tr></thead>
                <tbody>
                  <tr><td className="muted">Baseline</td><td className="num">{amount(snap.risk_model.intercept, true)}</td></tr>
                  {snap.risk_model.coefficients.map((c) => (
                    <tr key={c.name}><td>{c.name.replace("size_vs_usual", "size vs usual").replace("terms_30_days", "payment terms (per 30 days)")}</td><td className="num">{amount(c.coefficient, true)}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        )}
      </Section>
    </>
  );
}

