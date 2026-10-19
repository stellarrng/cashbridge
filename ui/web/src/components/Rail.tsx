import { useState, type ReactNode } from "react";
import type { ChatMessage, Snapshot, TierRow } from "../types";
import { decisionTone, decisionWord } from "./common";

function Panel({ title, count, open: initial, children }: { title: string; count?: string; open?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(!!initial);
  return (
    <div className="panel">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>
        <span>{title}{count && <span className="count">{count}</span>}</span>
        <span className="chev">{open ? "Hide" : "Show"}</span>
      </button>
      {open && <div className="body">{children}</div>}
    </div>
  );
}

interface Group { row: TierRow; times: number }

/** Folds consecutive identical decisions (for example five inbox scans) into one line. */
function group(rows: TierRow[]): Group[] {
  const out: Group[] = [];
  for (const row of [...rows].reverse()) {
    const last = out[out.length - 1];
    if (last && last.row.tool === row.tool && last.row.decision === row.decision && last.row.agent === row.agent) last.times += 1;
    else out.push({ row, times: 1 });
  }
  return out;
}

export function Activity({ rows, total, onMore }: { rows: TierRow[]; total: number; onMore: () => void }) {
  const groups = group(rows).slice(0, 8);
  return (
    <Panel title="Activity" count={`${total} logged`}>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 8px" }}>Financing and submission actions use the permission gate. Informational analytics and unsigned drafts are separately audit-logged. Level 4 money movement is refused.</p>
      {groups.length === 0 && <div className="muted">Nothing yet.</div>}
      {groups.map(({ row, times }) => (
        <div className="mon" key={row.seq}>
          <span className="tool">{row.tool}{times > 1 && <small>×{times}</small>}<small>{row.tier.slice(0, 2)}</small></span>
          <span className={`dec ${decisionTone(row.decision)}`}>{decisionWord(row.decision)}</span>
          <span className="why">{row.agent} · {row.reason}</span>
        </div>
      ))}
      <button className="textbtn" style={{ marginTop: 10 }} onClick={onMore}>Open the full audit log</button>
    </Panel>
  );
}

export function Assistant({ history, onAsk }: { history: ChatMessage[]; onAsk: (text: string) => Promise<void> }) {
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
    <Panel title="CFO assistant" open>
      <div className="chat">
        {history.map((message, index) => (
          <div className={`msg ${message.role}`} key={index}>
            <div className="label who">{message.role === "user" ? "You" : `Assistant · ${message.mode}`}</div>
            <div>{message.text}</div>
            {message.citations.length > 0 && (
              <details>
                <summary>Where do these numbers come from?</summary>
                <ul>
                  {message.citations.map((c) => (
                    <li key={c.source_id}>{c.label} <span className="mono">[{c.source_id}]</span></li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>
      <div className="ask">
        <input
          value={text} placeholder="Ask about cash or funding"
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button onClick={submit} disabled={busy}>Ask</button>
      </div>
    </Panel>
  );
}

export function Privacy({ data }: { data: Snapshot["pii_inspector"] }) {
  return (
    <Panel title="Privacy check">
      <div className="pii">
        {!data.before ? (
          <div className="muted">Nothing has been prepared for a model call yet.</div>
        ) : (
          <>
            <p className="muted" style={{ fontSize: 13, margin: "0 0 8px" }}>Account numbers, emails and names are swapped for tokens before any text could reach a cloud model.</p>
            <div className="label">Original</div>
            <pre>{data.before}</pre>
            <div className="label">What a model would see</div>
            <pre className="after">{data.after}</pre>
            {data.note && <div className="muted" style={{ fontSize: 12.5 }}>{data.note}</div>}
          </>
        )}
      </div>
    </Panel>
  );
}
