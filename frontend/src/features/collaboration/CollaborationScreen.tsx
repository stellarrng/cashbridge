import { useState, type FormEvent, type ReactNode } from "react";
import { StatusPill } from "@/entities/status";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Loadable, PageHead, Panel, useToast } from "@/shared/ui";
import { useAuth } from "../auth";
import {
  appeal, checkQuality, fetchBankFirstPack, fetchEvidence, fetchMessages, fetchNotifications, fetchRequests, fetchSnapshotPackId,
  openEvidenceFile, openRequest, postMessage, proposeChange, reviewEvidence, reviewRequest, revokeRequest, runScenario, uploadEvidence,
} from "./api";
import type { CaseMessage, EvidenceRequest, EvidenceView, Notification, QualityResult, RequestsView, ScenarioResult } from "./types";

const MAX_UPLOAD = 10_000_000;
const when = (iso: string) => iso.slice(0, 16).replace("T", " ");

interface WorkspaceData {
  bank: boolean;
  packId: string | null;
  requests: RequestsView | null;
  messages: CaseMessage[] | null;
  evidence: EvidenceView | null;
  notes: Notification[] | null;
}

/** Everything the SME and its lender do together on a released case, plus the SME's reviewable planning changes. */
export default function CollaborationScreen(_: ScreenProps) {
  const { user } = useAuth();
  const bank = user.portal === "bank";
  const data = useAsync<WorkspaceData>(async () => {
    const packId = bank ? await fetchBankFirstPack() : await fetchSnapshotPackId();
    const [requests, messages, evidence, notes] = await Promise.all([
      bank ? Promise.resolve(null) : fetchRequests(),
      packId ? fetchMessages(packId).then((r) => r.items).catch(() => null) : Promise.resolve(null),
      packId ? fetchEvidence(packId).catch(() => null) : Promise.resolve(null),
      fetchNotifications().then((r) => r.items).catch(() => null),
    ]);
    return { bank, packId, requests, messages, evidence, notes };
  }, [bank]);
  return <Loadable data={data.data} error={data.error}>{(d) => <Workspace d={d} reload={data.reload} />}</Loadable>;
}

function Workspace({ d, reload }: { d: WorkspaceData; reload: () => Promise<unknown> }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const act = useAct();
  // Run an action and reload the page data when it succeeded.
  const run = async <T,>(fn: () => Promise<T>, ok?: string) => {
    if ((await act(fn, ok)) !== null) await reload();
  };
  return (
    <>
      <PageHead title={t("ws.title")} lede={t("ws.lede")} />
      <div className="grid2">
        {d.packId && d.evidence && <EvidencePanel packId={d.packId} ev={d.evidence} run={run} />}
        {d.notes && (
          <Panel title={t("ws.notes")} sub={t("ws.notesSub")}>
            {d.notes.length ? (
              <ul className="list small">{d.notes.map((n, i) => <li key={i}>{when(n.time)} · {n.text}</li>)}</ul>
            ) : (
              <div className="empty">{t("ws.notesNone")}</div>
            )}
          </Panel>
        )}
        {!d.bank && <QualityPanel />}
        {!d.bank && can("sme:prepare") && <ChangeForm run={run} />}
        {!d.bank && d.requests && <Decisions requests={d.requests} run={run} />}
        {!d.bank && <AppealForm run={run} />}
        {!d.bank && d.requests && <ScenarioPanel requests={d.requests} />}
        <Messages packId={d.packId} messages={d.messages} bank={d.bank} run={run} />
      </div>
    </>
  );
}

type Run = <T>(fn: () => Promise<T>, ok?: string) => Promise<void>;

function Form({ id, onSubmit, children }: { id?: string; onSubmit: (data: FormData, form: HTMLFormElement) => void | Promise<void>; children: ReactNode }) {
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void onSubmit(new FormData(e.currentTarget), e.currentTarget);
  };
  return <form id={id} className="cb-work-form" onSubmit={submit}>{children}</form>;
}

// ------------------------------------------------------------------ lender evidence requests
function EvidencePanel({ packId, ev, run }: { packId: string; ev: EvidenceView; run: Run }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const counts = Object.entries(ev.counts).filter(([, n]) => n).map(([k, n]) => `${k} ${n}`).join(" · ");
  return (
    <Panel title={t("ws.ev.title")} sub={t("ws.ev.sub")}>
      <p className="note"><b>{t(ev.ready_for_decision ? "ws.ev.ready" : "ws.ev.blocking")}</b> · {counts || t("ws.ev.none")}</p>
      {ev.items.map((r) => <EvidenceRow key={r.id} packId={packId} r={r} run={run} />)}
      {can("bank:decide") && (
        <Form id="cb-evopen" onSubmit={(f) => run(() => openRequest(packId, String(f.get("item")), String(f.get("detail")), Number(f.get("due"))))}>
          <label>{t("ws.ev.item")}<input name="item" minLength={3} maxLength={120} required placeholder="Signed bill of lading" /></label>
          <label>{t("ws.ev.detail")}<textarea name="detail" minLength={4} maxLength={1000} required rows={2} /></label>
          <label>{t("ws.ev.due")}<input name="due" type="number" min={1} max={60} defaultValue={7} required /></label>
          <Button variant="bridge" type="submit">{t("ws.ev.request")}</Button>
        </Form>
      )}
    </Panel>
  );
}

async function sha256Of(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

function EvidenceRow({ packId, r, run }: { packId: string; r: EvidenceRequest; run: Run }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const act = useAct();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [received, setReceived] = useState<File | null>(null);
  const canPrepare = can("sme:prepare");
  const canDecide = can("bank:decide");

  const upload = async (f: FormData, form: HTMLFormElement) => {
    const file = f.get("file");
    if (!(file instanceof File) || !file.size) return toast(t("ws.ev.chooseFile"), true);
    if (file.size > MAX_UPLOAD) return toast(t("ws.ev.tooBig"), true);
    await run(() => uploadEvidence(packId, r.id, file, String(f.get("ref") ?? ""), String(f.get("note") ?? "")));
    form.reset();
  };
  const open = async () => {
    const ok = await act(async () => {
      await openEvidenceFile(packId, r.id, r.evidence_ref || "document");
      return true;
    }, t("ws.ev.opened"));
    if (ok) await run(async () => true);
  };
  const review = async (accept: boolean) => {
    if (reason.trim().length < 3) return toast(t("ws.ev.needReason"), true);
    // A document sent outside CashBridge (hash-only submission) is checked on this device before it can be accepted.
    const needsLocalCheck = accept && !r.evidence_file_id;
    if (needsLocalCheck && !received) return toast(t("ws.ev.chooseReceived"), true);
    const received_sha256 = needsLocalCheck && received ? await sha256Of(received) : undefined;
    await run(() => reviewEvidence(packId, r.id, { accept, reason, version: r.version, received_sha256 }));
  };

  return (
    <article className="cb-work-row" data-evr={r.id}>
      <div className="row between"><b>{r.item}</b><StatusPill status={r.status.toUpperCase()} /></div>
      <p>{r.detail}</p>
      <small>
        {r.id} · {t("ws.ev.dueOn")} {r.due.slice(0, 10)}
        {r.evidence_ref && (
          <> · v{r.version}: {r.evidence_ref} <span className="mono">{(r.evidence_sha256 ?? "").slice(0, 16)}…</span></>
        )}
        {r.decision_reason ? " · " + r.decision_reason : ""}
      </small>
      <details>
        <summary>{t("ws.timeline")}</summary>
        {r.timeline.map((a, i) => <p key={i} className="note">{when(a.time)} · {a.action} · {a.actor} · {a.detail}</p>)}
      </details>
      {canPrepare && ["open", "rejected"].includes(r.status) && (
        <form className="cb-work-form" data-evsubmit={r.id} onSubmit={(e) => { e.preventDefault(); void upload(new FormData(e.currentTarget), e.currentTarget); }}>
          <label>{t("ws.ev.ref")}<input name="ref" maxLength={150} required placeholder="DOC-BL-1030" /></label>
          <label>{t("ws.ev.file")}<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,application/pdf,image/png,image/jpeg,text/plain" required /></label>
          <label>{t("ws.ev.note")}<input name="note" maxLength={500} /></label>
          <Button small variant="bridge" type="submit">{t("ws.ev.submit")}</Button>
        </form>
      )}
      {r.evidence_file_id && r.status !== "revoked" && (
        <p className="note">
          <Button small variant="ghost" data-evopen={r.id} onClick={() => void open()}>{t("ws.ev.open")}</Button>{" "}
          {r.viewed_version === r.version && <span className="pill ok">{t("ws.ev.openedBy")}</span>}
        </p>
      )}
      {canDecide && r.status === "submitted" && (
        <>
          {!r.evidence_file_id && (
            <label className="field small">
              {t("ws.ev.received")}
              <input type="file" data-evfile={r.id} onChange={(e) => setReceived(e.target.files?.[0] ?? null)} />
            </label>
          )}
          <div className="cb-review">
            <input data-evreason={r.id} maxLength={500} aria-label={t("ws.reason")} placeholder={t("ws.reasonReq")} value={reason} onChange={(e) => setReason(e.target.value)} />
            <Button small variant="bridge" data-evreview={r.id} data-ok="true" onClick={() => void review(true)}>{t("ws.accept")}</Button>
            <Button small variant="ghost" data-evreview={r.id} data-ok="false" onClick={() => void review(false)}>{t("ws.reject")}</Button>
          </div>
        </>
      )}
      {canDecide && ["open", "rejected"].includes(r.status) && (
        <Button small variant="ghost" data-evrevoke={r.id} onClick={() => void run(() => revokeRequest(packId, r.id, t("ws.ev.noLonger")))}>{t("ws.ev.revoke")}</Button>
      )}
    </article>
  );
}

// ------------------------------------------------------------------ SME planning workspace
function QualityPanel() {
  const { t } = useI18n();
  const act = useAct();
  const [q, setQ] = useState<QualityResult | null>(null);
  const runDemo = async () => {
    const date = new Date().toISOString().slice(0, 10);
    const demo = {
      sources: ["bank_statement", "receivables_aging", "ledger"].map((type, i) => ({ type, source_id: "DEMO-" + i, as_of: date })),
      ledger_entries: [{ reference: "DEMO-INV-1", amount: "2000.00" }],
      bank_entries: [{ reference: "DEMO-INV-1", amount: "2000.00" }],
    };
    const r = await act(() => checkQuality(demo));
    if (r) setQ(r);
  };
  return (
    <Panel title={t("ws.q.title")} sub={t("ws.q.sub")}>
      <div className="cb-work-form">
        <p className="note">{t("ws.q.note")}</p>
        <Button variant="bridge" id="cb-quality-run" onClick={() => void runDemo()}>{t("ws.q.run")}</Button>
        <div className="cb-result">
          {q && (
            <>
              <p><strong>{q.gate}</strong> · {q.quality_index}/100</p>
              <p className="note">{q.notice}</p>
              {q.issues.map((i, n) => <p key={n} className="note">{i.detail}</p>)}
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}

function ChangeForm({ run }: { run: Run }) {
  const { t } = useI18n();
  return (
    <Panel title={t("ws.ch.title")} sub={t("ws.ch.sub")}>
      <Form id="cb-change" onSubmit={(f, form) => run(() => proposeChange(String(f.get("field")), String(f.get("value")), String(f.get("reason")))).then(() => form.reset())}>
        <label>
          {t("ws.ch.field")}
          <select name="field">
            <option value="marketing_usd">Marketing (USD)</option>
            <option value="working_capital_usd">Working capital (USD)</option>
            <option value="green_investment_usd">Green investment (USD)</option>
          </select>
        </label>
        <label>{t("ws.ch.value")}<input type="number" name="value" min={0} max={1000000000} step="0.01" required placeholder="25000" /></label>
        <label>{t("ws.reasonReq")}<textarea name="reason" maxLength={500} minLength={8} required rows={2} placeholder={t("ws.ch.example")} /></label>
        <Button variant="bridge" type="submit">{t("ws.ch.send")}</Button>
      </Form>
    </Panel>
  );
}

function Decisions({ requests, run }: { requests: RequestsView; run: Run }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const toast = useToast();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const decide = (id: string, approve: boolean) => {
    const note = notes[id] ?? "";
    if (note.trim().length < 3) return toast(t("ws.needNote"), true);
    void run(() => reviewRequest(id, approve, note));
  };
  return (
    <Panel title={t("ws.dec.title")} sub={t("ws.dec.sub")}>
      {requests.requests.length ? (
        requests.requests.map((r) => (
          <article key={r.id} className="cb-work-row">
            <div className="row between"><b>{r.kind === "planning_change" ? r.field : t("ws.dec.appeal")}</b><StatusPill status={r.status.toUpperCase()} /></div>
            <p>{r.reason}</p>
            <small>
              {r.actor} · {when(r.created)}
              {r.field ? ` · ${r.old_value ?? t("ws.notSet")} → ${r.proposed}` : ""}
            </small>
            {r.activities.length > 0 && (
              <details>
                <summary>{t("ws.history")}</summary>
                {r.activities.map((a, i) => <p key={i} className="note">{a.action} · {a.actor} · {a.detail}</p>)}
              </details>
            )}
            {can("sme:approve") && r.status === "pending" && (
              <div className="cb-review">
                <input aria-label={t("ws.dec.note")} placeholder={t("ws.dec.notePh")} maxLength={500} value={notes[r.id] ?? ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} />
                <Button small variant="bridge" onClick={() => decide(r.id, true)}>{t("ws.approve")}</Button>
                <Button small variant="ghost" onClick={() => decide(r.id, false)}>{t("ws.reject")}</Button>
              </div>
            )}
          </article>
        ))
      ) : (
        <div className="empty">{t("ws.dec.none")}</div>
      )}
    </Panel>
  );
}

function AppealForm({ run }: { run: Run }) {
  const { t } = useI18n();
  return (
    <Panel title={t("ws.ap.title")} sub={t("ws.ap.sub")}>
      <Form id="cb-appeal" onSubmit={(f, form) => run(() => appeal(String(f.get("ref")), String(f.get("reason")))).then(() => form.reset())}>
        <label>{t("ws.ap.ref")}<input name="ref" maxLength={150} required placeholder="INV-1030 / bank statement" /></label>
        <label>{t("ws.ap.why")}<textarea name="reason" minLength={12} maxLength={500} required rows={2} /></label>
        <Button variant="ghost" type="submit">{t("ws.ap.send")}</Button>
      </Form>
    </Panel>
  );
}

function ScenarioPanel({ requests }: { requests: RequestsView }) {
  const { t } = useI18n();
  const act = useAct();
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const items = Object.entries(requests.approved_scenario_assumptions);
  return (
    <Panel title={t("ws.sc.title")} sub={t("ws.sc.sub")}>
      <ul className="cb-assumptions">
        {items.length ? items.map(([field, v]) => <li key={field}>{field}: <b>{usd(v.value)}</b> · v{v.version}</li>) : <li>{t("ws.sc.none")}</li>}
      </ul>
      <Form id="cb-scenario" onSubmit={async (f) => { const r = await act(() => runScenario(Number(f.get("cash")), Number(f.get("reserve")))); if (r) setResult(r); }}>
        <label>{t("ws.sc.cash")} (USD)<input name="cash" type="number" defaultValue={100000} min={0} required /></label>
        <label>{t("ws.sc.reserve")} (USD)<input name="reserve" type="number" defaultValue={10000} min={0} required /></label>
        <Button variant="ghost" type="submit">{t("ws.sc.run")}</Button>
      </Form>
      <div className="cb-result">
        {result && (
          <>
            <p><strong>{t("ws.sc.gap")}: {usd(result.funding_gap_usd)}</strong></p>
            <p className="note">{result.notes.join(" ")}</p>
          </>
        )}
      </div>
    </Panel>
  );
}

function Messages({ packId, messages, bank, run }: { packId: string | null; messages: CaseMessage[] | null; bank: boolean; run: Run }) {
  const { t } = useI18n();
  if (!packId || !messages) {
    return (
      <Panel title={t("ws.msg.title")}>
        <div className="empty">{t("ws.msg.after")}</div>
      </Panel>
    );
  }
  const kinds = bank ? [["question", t("ws.msg.question")], ["evidence_request", t("ws.msg.evidence")]] : [["question", t("ws.msg.question")], ["response", t("ws.msg.response")]];
  return (
    <Panel title={t("ws.msg.title")} sub={t("ws.msg.sub")}>
      <p className="note">{packId}</p>
      {messages.length ? (
        messages.map((m) => (
          <article key={m.id} className="cb-work-row">
            <strong>{m.actor_role}</strong> · <small>{m.kind} · {m.created.slice(0, 16)}</small>
            <p>{m.message}</p>
          </article>
        ))
      ) : (
        <div className="empty">{t("ws.msg.none")}</div>
      )}
      <Form id="cb-message" onSubmit={(f, form) => run(() => postMessage(packId, String(f.get("kind")), String(f.get("message")))).then(() => form.reset())}>
        <label>{t("ws.msg.kind")}<select name="kind">{kinds.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label>{t("ws.msg.text")}<textarea name="message" minLength={4} maxLength={1000} required rows={3} /></label>
        <Button variant="bridge" type="submit">{t("ws.msg.send")}</Button>
      </Form>
    </Panel>
  );
}
