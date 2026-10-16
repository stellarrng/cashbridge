import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ScenarioKey, ScenarioParams, SimulateResult, Snapshot } from "../types";
import { AttributionBars } from "../components/AttributionBars";
import { CashChart } from "../components/CashChart";
import { Empty, Section } from "../components/common";
import { amount, dayMonth, usd } from "../format";

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
      <Section title="Thirteen weeks of cash" aside={<span className="micro">Closing balance, USD</span>}>
        <p className="lede">
          Expected inflows are invoice value times the probability of on-time payment, placed in the due week; the late remainder
          arrives four weeks later. Select a week to see its movements.
        </p>
        <CashChart weeks={snap.forecast.weeks} buffer={snap.forecast.buffer_usd} scenario={result ? result.forecast.weeks : null} />
      </Section>

      <div className="grid2">
        <Section title="Why the shortfall happens" aside={<span className="micro">{result ? "Scenario" : "Base case"}</span>}>
          <AttributionBars items={shown.attribution} shortfall={shownShortfall} />
        </Section>

        <Section title="What if" aside={changed && <button className="linkbtn" onClick={() => setParams(defaults)}>Reset sliders</button>}>
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
              value={question} placeholder="Or ask it in words"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && question.trim()) { onAsk(question.trim()); setQuestion(""); } }}
            />
            <button onClick={() => { if (question.trim()) { onAsk(question.trim()); setQuestion(""); } }}>Send</button>
          </div>
        </Section>
      </div>

      <Section title="Collections">
        {snap.collections.schedule.length === 0 && snap.collections.promises.length === 0 ? (
          <Empty>No reminders drafted yet. They appear here once the collections agent runs.</Empty>
        ) : (
          <div className="scroll">
            <table>
              <thead><tr><th>Invoice</th><th>Buyer</th><th>Stage</th><th>Scheduled</th><th>Status</th></tr></thead>
              <tbody>
                {snap.collections.schedule.map((r) => (
                  <tr key={r.invoice_id + r.stage}>
                    <td className="num">{r.invoice_id}</td><td>{r.buyer}</td><td>{r.stage}</td>
                    <td>{dayMonth(r.scheduled_date)}</td><td>{r.status.replace("_", " ")}</td>
                  </tr>
                ))}
                {snap.collections.promises.map((p) => (
                  <tr key={p.invoice_id + p.promised_date}>
                    <td className="num">{p.invoice_id}</td><td>{p.buyer}</td><td>Buyer promise</td>
                    <td>{dayMonth(p.promised_date)}</td><td className="muted">“{p.source_text}”</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Buyer risk">
        {snap.buyer_risk.length === 0 ? (
          <Empty>Concentration and on-time probability by buyer appear here once the buyer risk agent is enabled.</Empty>
        ) : (
          <table>
            <thead><tr><th>Buyer</th><th className="num">Share of receivables</th><th className="num">Avg days late</th><th className="num">P(on time)</th><th>Alert</th></tr></thead>
            <tbody>
              {snap.buyer_risk.map((b) => (
                <tr key={b.buyer}>
                  <td>{b.buyer}</td><td className="num">{amount(b.share_of_receivables_pct, true)}%</td>
                  <td className="num">{amount(b.avg_days_late, true)}</td><td className="num">{amount(b.p_on_time, true)}</td>
                  <td className={b.concentration_alert ? "neg" : ""}>{b.concentration_alert ? "Concentration" : "None"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </>
  );
}

