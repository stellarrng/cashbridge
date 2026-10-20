import type { ButtonHTMLAttributes, ReactNode } from "react";

/** Page heading with an optional lede and a row of actions. */
export function PageHead({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="head">
      <div>
        <h1>{title}</h1>
        {lede ? <p>{lede}</p> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}

/** Headline figure. `tone` colours the value; `highlight` draws the accent card. */
export function Kpi({ label, value, tone = "", highlight = false, foot }: { label: string; value: ReactNode; tone?: "" | "neg" | "pos" | "warn"; highlight?: boolean; foot?: ReactNode }) {
  return (
    <div className={"kpi" + (highlight ? " hl" : "")}>
      <span>{label}</span>
      <b className={tone}>{value}</b>
      {foot ? <small>{foot}</small> : null}
    </div>
  );
}

export function Kpis({ children }: { children: ReactNode }) {
  return <div className="kpis cards">{children}</div>;
}

export function Panel({ title, sub, children, className = "" }: { title: string; sub?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <section className={("panel " + className).trim()}>
      <h2>{title}</h2>
      {sub ? <p className="sub">{sub}</p> : null}
      {children}
    </section>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

/** Orange-bordered note ("what this does not fix"). */
export function Caution({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="caution">
      <b>{title}</b>
      <ul className="list">
        {items.map((x, i) => <li key={i}>{x}</li>)}
      </ul>
    </div>
  );
}

export function Note({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={("note " + className).trim()}>{children}</p>;
}

/** Bulleted list of plain strings. */
export function BulletList({ items, small }: { items: string[]; small?: boolean }) {
  return (
    <ul className={"list" + (small ? " small" : "")}>
      {items.map((x, i) => <li key={i}>{x}</li>)}
    </ul>
  );
}

export function Meter({ ratio, tip, low }: { ratio: number; tip: string; low?: boolean }) {
  return (
    <span className={"meter" + (low ? " low" : "")} data-tip={tip}>
      <i style={{ width: Math.round(ratio * 100) + "%" }} />
    </span>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "bridge" | "bank" | "ghost" | "danger" | ""; small?: boolean };

export function Button({ variant = "", small, className = "", type = "button", ...rest }: BtnProps) {
  return <button type={type} className={["btn", variant, small ? "small" : "", className].filter(Boolean).join(" ")} {...rest} />;
}

export function Scroll({ children }: { children: ReactNode }) {
  return <div className="scroll">{children}</div>;
}
