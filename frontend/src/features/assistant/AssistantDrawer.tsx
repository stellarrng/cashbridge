import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSnapshotContext } from "@/entities/case";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { Button } from "@/shared/ui";
import { askCfo } from "./api";

const SUGGEST = ["When do we run short?", "What is the cheapest funding?", "Which buyer is most at risk?", "What if buyers pay 15 days late?"];

/** Read-only CFO chat. Answers come from the forecast and funding engines and cite their source; it never acts. */
export function AssistantDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const act = useAct();
  const { snapshot, refresh } = useSnapshotContext();
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const history = snapshot?.chat.history ?? [];

  useEffect(() => {
    if (!open) return;
    void refresh().catch(() => undefined);
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, refresh, onClose]);

  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [history.length, open]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q) return;
    setText("");
    if (await act(() => askCfo(q))) await refresh();
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(text);
  };

  return (
    <aside className="drawer" aria-label="CFO assistant" hidden={!open}>
      <div className="drawer-head">
        <h2>{t("chat.title")}</h2>
        <Button small variant="ghost" onClick={onClose}>{t("chat.close")}</Button>
      </div>
      <p className="muted small">Answers come from the forecast and funding engines and cite their source. It reads, it never acts.</p>
      <div className="chat" ref={log} aria-live="polite">
        {history.map((m, i) => (
          <div key={i} className={"bubble" + (m.role === "user" ? " user" : "")}>
            {m.text}
            {m.citations && m.citations.length > 0 && <small>{m.citations.map((c) => c.label || c.source_id).join(", ")}</small>}
          </div>
        ))}
      </div>
      <form className="chat-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="chatInput">Ask a question</label>
        <input className="input" id="chatInput" ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder="When do we run short, and what is the cheapest fix?" required />
        <Button variant="bridge" type="submit">{t("chat.ask")}</Button>
      </form>
      <div className="suggest">
        {SUGGEST.map((q) => (
          <button key={q} type="button" onClick={() => void ask(q)}>{q}</button>
        ))}
      </div>
    </aside>
  );
}
