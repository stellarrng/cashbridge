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
}

export function Header({ meta, guide, tab, go, onReset, busy, railOpen, toggleRail }: Props) {
  const live = meta.mode === "live-llm";
  const current = guide.steps.find((s) => s.state === "current");
  return (
    <header className="topbar">
      <div className="bar">
        <span className="wordmark">CashBridge</span>
        <nav className="nav" aria-label="Sections">
          {TABS.map((t) => (
            <span key={t.key} style={{ display: "contents" }}>
              {t.key === "evidence" && <span className="sep" />}
              <button aria-current={tab === t.key ? "page" : undefined} onClick={() => go(t.key)}>{t.title}</button>
            </span>
          ))}
        </nav>
        <span className="spacer" />
        <span className="tag" title="All companies, people and data are invented for this demo">Synthetic data</span>
        <span className={`tag ${live ? "live" : ""}`} title="offline-demo uses fixed templates; live-llm calls the configured model">
          <span className="dot" />{meta.mode}
        </span>
        <button className="textbtn" onClick={toggleRail}>{railOpen ? "Close panel" : "Assistant"}</button>
        <button className="textbtn" onClick={onReset} disabled={busy}>Reset demo</button>
      </div>
      <div className="journeywrap"><div className="journey">
        <ol aria-label="Progress">
          {guide.steps.map((s) => (
            <li key={s.key} className={s.state}>
              <span className="mark">{s.state === "done" ? "✓" : ""}</span>
              {s.title}
            </li>
          ))}
        </ol>
        <span className="spacer" />
        {guide.next ? (
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
