import type { Meta } from "../types";
import type { Guide, TabKey } from "../journey";
import { TABS } from "../journey";

interface Props {
  meta: Meta;
  guide: Guide;
  tab: TabKey;
  go: (tab: TabKey) => void;
  onReset: () => void;
  busy: boolean;
  railOpen: boolean;
  toggleRail: () => void;
  role: "sme" | "bank";
  onRoleChange: (role: "sme" | "bank") => void;
}

export function Header({ meta, guide, tab, go, onReset, busy, railOpen, toggleRail, role, onRoleChange }: Props) {
  const live = meta.mode === "live-llm";
  const current = guide.steps.find((s) => s.state === "current");
  return (
    <header className="topbar">
      <div className="bar">
        <span className="wordmark">CashBridge</span>
        <nav className="nav" aria-label="Sections">
          {TABS.filter(t => role === "sme" ? t.key !== "bank" : ["bank","analytics","contracts","green","evidence"].includes(t.key)).map((t) => (
            <span key={t.key} style={{ display: "contents" }}>
              {t.key === "evidence" && <span className="sep" />}
              <button aria-current={tab === t.key ? "page" : undefined} onClick={() => go(t.key)}>{t.title}</button>
            </span>
          ))}
        </nav>
        <span className="spacer" />
        <div className="role-toggle" aria-label="Workspace preview, not authentication">
          <button aria-pressed={role === "sme"} onClick={() => onRoleChange("sme")}>SME</button>
          <button aria-pressed={role === "bank"} onClick={() => onRoleChange("bank")}>Bank preview</button>
        </div>
        <span className="tag" title="All companies, people and data are invented for this demo">Synthetic data</span>
        <span className={`tag ${live ? "live" : ""}`} title="Local workflow engines; LLM never orchestrates actions or reads financial documents">
          <span className="dot" />{meta.mode}
        </span>
        <button className="textbtn" onClick={toggleRail}>{railOpen ? "Close panel" : "Assistant"}</button>
        <button className="textbtn" onClick={onReset} disabled={busy}>Reset demo</button>
      </div>
      <div className="journeywrap"><div className="journey">
        {role === "bank" ? <span className="where">Token-gated synthetic reviewer preview · no production IAM, KYC or credit approval</span> : <ol aria-label="Progress">
          {guide.steps.map((s) => (
            <li key={s.key} className={s.state}>
              <span className="mark">{s.state === "done" ? "✓" : ""}</span>
              {s.title}
            </li>
          ))}
        </ol>}
        <span className="spacer" />
        {role === "bank" ? null : guide.next ? (
          <>
            <span className="where">{current ? `Up next: ${current.title}.` : "All steps complete."}</span>
            <button className="go" onClick={() => go(guide.next!.tab)}>{guide.next.label} →</button>
          </>
        ) : (
          <span className="where">All steps complete.</span>
        )}
      </div></div>
    </header>
  );
}
