import type { FundingOption, Snapshot } from "../types";
import { Button, Notice, Section, Status } from "../components/common";
import { label, pct, usd } from "../format";

function assumptionText(key: string, value: number | string): string {
  if (typeof value === "number" && key.includes("_pct")) return `${value}%`;
  if (key === "days" || key.endsWith("_days")) return `${value} days`;
  return String(value);
}

function Option({ option, chosen, canChoose, onChoose }: { option: FundingOption; chosen: boolean; canChoose: boolean; onChoose: () => void }) {
  return (
    <div className={`option ${option.eligible ? "" : "off"} ${chosen ? "chosen" : ""}`}>
      <div className="rank">{option.rank ?? "–"}</div>
      <div>
        <div className="micro">{label(option.type)}</div>
        <h3 style={{ fontFamily: "var(--display)", fontWeight: 700, fontStretch: "85%", fontSize: 21, margin: "4px 0 10px" }}>{option.name}</h3>
        {option.eligible ? (
          <>
            <div className="apr">{pct(option.apr_pct)} <span className="micro">a year</span></div>
            <p className="muted" style={{ marginTop: 10 }}>{option.why_not_cheaper}</p>
            <p className="num muted" style={{ marginTop: 8, fontSize: 11.5 }}>{option.formula}</p>
          </>
        ) : (
          <p><Status text="Not eligible" tone="neg" /> <span className="muted">{option.ineligible_reason}</span></p>
        )}
      </div>
      <div>
        {option.eligible && (
          <>
            <div className="micro" style={{ marginBottom: 6 }}>Funds</div>
            <div className="num" style={{ marginBottom: 14 }}>{usd(option.amount_usd)}</div>
            <div className="micro" style={{ marginBottom: 6 }}>Cost</div>
            <dl>
              {Object.entries(option.cost_breakdown).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}><dt>{label(k.replace("_usd", ""))}</dt><dd>{usd(v, true)}</dd></div>
              ))}
            </dl>
            <div className="micro" style={{ margin: "14px 0 6px" }}>Assumptions</div>
            <dl>
              {Object.entries(option.assumptions).map(([k, v]) => (
                <div key={k} style={{ display: "contents" }}><dt>{label(k.replace("_pct", "").replace("_pa", " per year"))}</dt><dd>{assumptionText(k, v)}</dd></div>
              ))}
            </dl>
          </>
        )}
      </div>
      <div style={{ textAlign: "right" }}>
        {option.eligible && (
          chosen ? <Status text="Chosen" tone="pos" solid /> : <Button primary={option.rank === 1} onClick={onChoose} disabled={!canChoose}>Choose</Button>
        )}
      </div>
    </div>
  );
}

export function Compare({ snap, onChoose }: { snap: Snapshot; onChoose: (id: string) => void }) {
  const canChoose = snap.meta.case_state === "INVOICE_VERIFIED";
  return (
    <Section title="Liquidity menu" aside={<span className="micro">Ranked by annualised cost</span>}>
      <p className="lede">
        Cost is total cost over net funds received, scaled to a year: <span className="num">APR = total cost / net funds × 365 / days</span>.
        The same two percent costs very different amounts depending on the terms behind it.
      </p>
      {snap.meta.last_error && <Notice tone="bad" title="Not possible">{snap.meta.last_error}</Notice>}
      {!canChoose && snap.selected_option_id === null && (
        <Notice title="Choosing is closed">An option can only be chosen while the case is waiting for the Director's decision.</Notice>
      )}
      {snap.funding_options.map((o) => (
        <Option key={o.id} option={o} chosen={snap.selected_option_id === o.id} canChoose={canChoose} onChoose={() => onChoose(o.id)} />
      ))}
    </Section>
  );
}
