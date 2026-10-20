import { useCallback, useEffect, useState, type FormEvent } from "react";
import { metricText } from "@/entities/funding";
import { StatusPill } from "@/entities/status";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { Button, Modal } from "@/shared/ui";
import { decideCorrection, fetchLineage, proposeCorrection } from "./api";
import { sourceRef, type Lineage, type ProvenanceSource, type ScanSource } from "./types";

interface Props {
  /** Lineage endpoint (see lineageUrl). */
  url: string;
  /** Metric to show; null closes the dialog. */
  metricKey: string | null;
  onClose: () => void;
  /** The preparer may propose a correction to a source field (SME view only). */
  canPropose?: boolean;
  /** A different person (the Director) decides pending corrections. The server enforces both rules again. */
  canDecide?: boolean;
}

const short = (h: string | null) => (h ? h.slice(0, 16) + "…" : "–");

/** The source line with the exact characters that were read highlighted. Nothing is drawn by coordinates. */
function SourceLine({ s }: { s: ScanSource }) {
  const line = s.source_line ?? "";
  const i = s.excerpt ? line.indexOf(s.excerpt) : -1;
  if (!s.excerpt || i < 0) return <pre className="prov-line">{line}</pre>;
  return (
    <pre className="prov-line">
      {line.slice(0, i)}
      <mark>{s.excerpt}</mark>
      {line.slice(i + s.excerpt.length)}
    </pre>
  );
}

function Source({ s }: { s: ProvenanceSource }) {
  const { t } = useI18n();
  if (s.kind === "scan") {
    return (
      <li>
        <b>{t("pv.scan")}</b> <span className="mono">{s.doc_id}</span> · {s.field} · {t("pv.where", { p: s.page ?? "–", l: s.line ?? "–", a: s.char_start ?? "–", b: s.char_end ?? "–" })} ·{" "}
        {t("pv.conf", { c: Number(s.confidence).toFixed(2) })}
        <SourceLine s={s} />
        <div className="small muted">
          {s.review_status} · {t("pv.hash")} <span className="mono">{short(s.text_sha256)}</span>
          {s.span_verified ? " ✓" : ""}
        </div>
        <div className="small muted">{s.bbox_note}</div>
      </li>
    );
  }
  return (
    <li>
      <b>{t("pv.record")}</b> <span className="mono">{s.file}</span> <span className="mono">{s.json_path}</span>
      {s.value != null && <> = <b>{s.value}</b></>}
      <div className="small muted">
        {s.review_status} · {t("pv.hash")} <span className="mono">{short(s.file_sha256)}</span>
      </div>
    </li>
  );
}

/** Click-to-source for one locked figure: formula, inputs, sources (file/JSON path or scan page/line/span), hashes, history. */
export function ProvenanceDialog({ url, metricKey, onClose, canPropose = false, canDecide = false }: Props) {
  const { t } = useI18n();
  const act = useAct();
  const [lin, setLin] = useState<Lineage | null>(null);
  const [form, setForm] = useState({ source_ref: "", proposed_value: "", reason: "" });
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const data = await act(() => fetchLineage(url));
    if (data) setLin(data);
  }, [act, url]);

  useEffect(() => {
    if (metricKey) {
      setLin(null);
      setForm({ source_ref: "", proposed_value: "", reason: "" });
      void load();
    }
  }, [metricKey, load]);

  const m = lin?.metrics.find((x) => x.key === metricKey) ?? null;
  const locked = m ? metricText({ key: m.key, label: m.label, unit: m.unit, value: m.locked_value }, t) : "";

  const propose = async (e: FormEvent) => {
    e.preventDefault();
    if (!m) return;
    const ref = form.source_ref || (m.sources[0] ? sourceRef(m.sources[0]) : "");
    if (await act(() => proposeCorrection({ metric_key: m.key, source_ref: ref, proposed_value: form.proposed_value, reason: form.reason }), (r) => r.id)) {
      setForm({ source_ref: "", proposed_value: "", reason: "" });
      await load();
    }
  };
  const decide = async (id: string, approve: boolean) => {
    if (await act(() => decideCorrection(id, approve, notes[id] ?? ""), (r) => r.status)) await load();
  };

  return (
    <Modal id="provModal" wide open={metricKey !== null} titleId="provTitle" onClose={onClose}>
      <div className="prov" id="provDialog">
        {!m ? (
          <p className="muted">…</p>
        ) : (
          <>
            <h2 id="provTitle">{t("pv.title", { m: m.label })}</h2>
            <p>
              <b>{t("pv.locked")}:</b> {locked} · <span className="small muted">{t("pv.lockedIn", { p: lin!.pack_id })}</span>
            </p>
            <p className={m.reproduces_locked_value ? "" : "caution"}>{m.reproduces_locked_value ? t("pv.repro") : t("pv.noRepro", { v: String(m.recomputed_now) })}</p>
            <h3 className="mini">{t("pv.formula")}</h3>
            <p>{m.formula}</p>
            <h3 className="mini">{t("pv.calc")}</h3>
            <p className="mono small">{m.computation}</p>
            <details>
              <summary>{t("pv.inputs")} ({m.inputs.length})</summary>
              <ul className="list small">
                {m.inputs.map((i, n) => (
                  <li key={n}>{i.name}: <span className="mono">{i.value}</span></li>
                ))}
              </ul>
            </details>
            <h3 className="mini">{t("pv.sources")}</h3>
            <ul className="list small prov-sources">{m.sources.map((s, i) => <Source key={i} s={s} />)}</ul>
            <h3 className="mini">{t("pv.history")}</h3>
            <ul className="list small">
              <li>
                {t("pv.lockedIn", { p: lin!.pack_id })}: {locked} · bundle <span className="mono">{short(lin!.bundle_sha256)}</span>
              </li>
              {(m.corrections ?? []).map((c) => (
                <li key={c.id}>
                  <span className="mono">{c.id}</span> <StatusPill status={c.status.toUpperCase()} /> {c.source_ref}: {c.original_value ?? "–"} → <b>{c.proposed_value}</b> · {c.proposed_by}
                  {c.decided_by ? " → " + c.decided_by : ""} · {c.reason}
                  <div className="small muted">{c.effect}</div>
                  {c.status === "pending" && canDecide && (
                    <div className="cb-review">
                      <input data-cnote={c.id} maxLength={500} placeholder={t("pv.note")} value={notes[c.id] ?? ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} />
                      <Button small variant="bridge" data-cdec={c.id} data-ok="true" onClick={() => void decide(c.id, true)}>{t("pv.approve")}</Button>
                      <Button small variant="ghost" data-cdec={c.id} data-ok="false" onClick={() => void decide(c.id, false)}>{t("pv.reject")}</Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {canPropose ? (
              <form id="pvForm" className="cb-work-form" onSubmit={(e) => void propose(e)}>
                <h3 className="mini">{t("pv.propose")}</h3>
                <label>
                  {t("pv.field")}
                  <select name="source_ref" value={form.source_ref || (m.sources[0] ? sourceRef(m.sources[0]) : "")} onChange={(e) => setForm({ ...form, source_ref: e.target.value })}>
                    {m.sources.map((s) => (
                      <option key={sourceRef(s)} value={sourceRef(s)}>
                        {sourceRef(s)}
                        {s.value != null ? " = " + s.value : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("pv.newValue")}
                  <input name="proposed_value" maxLength={200} required value={form.proposed_value} onChange={(e) => setForm({ ...form, proposed_value: e.target.value })} />
                </label>
                <label>
                  {t("pv.reason")}
                  <textarea name="reason" minLength={8} maxLength={500} rows={2} required value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                </label>
                <p className="note">{t("pv.policy")}</p>
                <Button small variant="bridge" type="submit">{t("pv.send")}</Button>
              </form>
            ) : (
              <p className="note">{t("pv.policy")}</p>
            )}
          </>
        )}
        <div className="row mt-2" style={{ justifyContent: "flex-end" }}>
          <Button variant="ghost" id="provClose" onClick={onClose}>{t("pv.close")}</Button>
        </div>
      </div>
    </Modal>
  );
}

/** A locked figure shown as a button that opens its provenance. */
export function MetricLink({ label, metricKey, onOpen }: { label: string; metricKey: string; onOpen: (key: string) => void }) {
  const { t } = useI18n();
  return (
    <button type="button" className="prov-link num" data-prov={metricKey} title={t("pv.open")} onClick={() => onOpen(metricKey)}>
      {label}
    </button>
  );
}
