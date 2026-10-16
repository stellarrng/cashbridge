import type { ReactNode } from "react";

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="section">
      <header>
        <h2>{title}</h2>
        {aside}
      </header>
      {children}
    </section>
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
