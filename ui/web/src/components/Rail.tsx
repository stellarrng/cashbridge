import { useState } from "react";
import type { ChatMessage, Snapshot, TierRow } from "../types";
import { decisionTone } from "./common";

export function TierMonitor({ rows }: { rows: TierRow[] }) {
  const latest = [...rows].reverse();
  return (
    <div>
      <h3>Permission monitor</h3>
      {latest.length === 0 && <div className="muted">No decisions yet.</div>}
      {latest.map((row) => (
        <div className="mon" key={row.seq}>
          <span className="tier">{row.tier.slice(0, 2)}</span>
          <span className="tool">{row.tool}</span>
          <span className={`dec ${decisionTone(row.decision)}`}>{row.decision.replace("_", " ")}</span>
          <span className="why">{row.agent} · {row.reason}</span>
        </div>
      ))}
    </div>
  );
}

export function Chat({ history, onAsk }: { history: ChatMessage[]; onAsk: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await onAsk(text.trim());
      setText("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div>
      <h3>CFO assistant</h3>
      <div className="chat">
        {history.map((message, index) => (
          <div className={`msg ${message.role}`} key={index}>
            <div className="micro who">{message.role === "user" ? "You" : "Assistant"} · {message.mode}</div>
            <div>{message.text}</div>
            {message.citations.length > 0 && (
              <details>
                <summary>Why?</summary>
                <ul>
                  {message.citations.map((c) => (
                    <li key={c.source_id}>{c.label} <span className="num">[{c.source_id}]</span></li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>
      <div className="ask">
        <input
          value={text}
          placeholder="Ask about cash, funding or a what-if"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button onClick={submit} disabled={busy}>Ask</button>
      </div>
    </div>
  );
}

export function PiiInspector({ data }: { data: Snapshot["pii_inspector"] }) {
  const empty = !data.before;
  return (
    <div className="pii">
      <h3>PII inspector</h3>
      {empty ? (
        <div className="muted">Nothing has been prepared for a model call yet.</div>
      ) : (
        <>
          <div className="micro">Before</div>
          <pre>{data.before}</pre>
          <div className="micro">After masking</div>
          <pre className="after">{data.after}</pre>
          {data.note && <div className="muted" style={{ fontSize: 12 }}>{data.note}</div>}
        </>
      )}
    </div>
  );
}
