import type { Meta } from "../types";
import { label } from "../format";

export function Header({ meta, onReset, busy }: { meta: Meta; onReset: () => void; busy: boolean }) {
  const live = meta.mode === "live-llm";
  return (
    <header className="topbar">
      <span className="wordmark">CashBridge</span>
      <span className="micro tag">SME finance copilot for export enterprises</span>
      <span className="badge">Synthetic demo data</span>
      <span className={`badge ${live ? "live" : ""}`} title="offline-demo uses deterministic templates; live-llm calls the configured model">
        <span className="dot" />
        {meta.mode}
      </span>
      <span className="badge">Case {label(meta.case_state)}</span>
      <button className="linkbtn" onClick={onReset} disabled={busy}>Reset demo</button>
    </header>
  );
}
