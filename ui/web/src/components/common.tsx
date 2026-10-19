import type { ReactNode } from "react";
import type { Kpis } from "../types";
import { usd } from "../format";
import type { Guide, TabKey } from "../journey";

export function Section({ id, title, aside, children }: { id?: string; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="section" id={id}>
      <header>
        <h2>{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** In-page navigation: jumps to a section on a long tab. */
export function PageNav({ items }: { items: { id: string; label: string }[] }) {
  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <div className="chips">
      <span>On this page</span>
      {items.map((i) => (
        <button key={i.id} onClick={() => go(i.id)}>{i.label}</button>
      ))}
    </div>
  );
}

export function PageHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="pagehead">
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </div>
  );
}

/** One quiet line of the headline numbers, shown on every tab except the first. */
export function Summary({ kpis }: { kpis: Kpis }) {
  const short = kpis.first_shortfall_week !== null;
  return (
    <div className="summary">
      <span>Cash <b>{usd(kpis.cash_today_usd)}</b></span>
      <span>Cash cycle <b>{kpis.ccc.ccc} days</b></span>
      <span>{short ? <>Short in <b className="neg">week {kpis.first_shortfall_week}</b> by <b className="neg">{usd(kpis.shortfall_usd)}</b></> : <b className="pos">No shortfall</b>}</span>
      <span><b>{kpis.blocked_fraud_count}</b> fraud attempt{kpis.blocked_fraud_count === 1 ? "" : "s"} blocked</span>
    </div>
  );
}

/** Bottom-of-page pointer to the next step in the loop. Hidden when the page itself holds the next action. */
export function NextStep({ guide, current, go }: { guide: Guide; current: TabKey; go: (tab: TabKey) => void }) {
  if (!guide.next || guide.next.tab === current) return null;
  const { label, tab } = guide.next;
  return (
    <div className="next">
      <div>
        <div className="label">Next step</div>
        <div className="title">{label}</div>
      </div>
      <Button primary onClick={() => go(tab)}>Continue</Button>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Notice({ tone, title, children }: { tone?: "bad" | "good"; title?: string; children?: ReactNode }) {
  return (
    <div className={`notice ${tone ?? ""}`}>
      {title && <div className="title">{title}</div>}
      {children}
    </div>
  );
}

// Colour is a state signal only: green = success, red = deficit or block, ink = everything else.
export function decisionTone(decision: string): string {
  if (decision === "BLOCKED" || decision === "REJECTED") return "neg";
  if (decision === "APPROVED") return "pos";
  if (decision === "AWAITING_APPROVAL") return "muted";
  return "";
}

export function decisionWord(decision: string): string {
  return decision === "AWAITING_APPROVAL" ? "Waiting" : decision.charAt(0) + decision.slice(1).toLowerCase();
}

export function Status({ text, tone, solid }: { text: string; tone?: "pos" | "neg" | "muted" | ""; solid?: boolean }) {
  return <span className={`status ${tone ?? ""} ${solid ? "solid" : ""}`}>{text}</span>;
}

export function Button({
  children, onClick, primary, quiet, disabled,
}: { children: ReactNode; onClick?: () => void; primary?: boolean; quiet?: boolean; disabled?: boolean }) {
  return (
    <button className={`btn ${primary ? "primary" : ""} ${quiet ? "quiet" : ""}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}
