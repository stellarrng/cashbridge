import { useState } from "react";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { Button, Kpi, Kpis, Note, Panel, Scroll } from "@/shared/ui";
import { useAuth } from "../auth";
import { anchorNow, chainProof, duplicateDrill, fetchChain, type ChainProof } from "./api";

const short = (h: string, n = 10) => (h.length > n * 2 ? `${h.slice(0, n)}…${h.slice(-6)}` : h);

/** Challenge bonus: Vyper contracts on an in-process EVM. Shown to the SME and the lender. */
export function OnChainPanel() {
  const { t } = useI18n();
  const { can, user } = useAuth();
  const act = useAct();
  const [tick, setTick] = useState(0);
  const st = useAsync(() => fetchChain().catch(() => null), [tick]);
  const [proof, setProof] = useState<ChainProof | null>(null);
  const [entry, setEntry] = useState("0");
  const s = st.data;
  const reload = () => setTick((x) => x + 1);

  if (!s) return null;
  if (!s.available) return <Panel title={t("oc.title")} sub={t("oc.off", { reason: s.reason || "" })} />;
  const inv = s.invoice;
  return (
    <section id="onchain">
      <Panel title={t("oc.title")} sub={t("oc.sub")}>
        <Kpis>
          <Kpi label={t("oc.block")} value={s.block ?? 0} />
          <Kpi label={t("oc.registrations")} value={s.registrations ?? 0} />
          <Kpi label={t("oc.duplicates")} tone={s.duplicates_refused ? "warn" : undefined} value={s.duplicates_refused ?? 0} />
          <Kpi label={t("oc.anchors")} tone={s.audit?.all_reproduced === false ? "neg" : "pos"} value={`${s.anchors ?? 0} · ${s.audit?.all_reproduced === false ? t("oc.mismatch") : t("oc.reproduced")}`} />
        </Kpis>
        <div className="grid2 mt-2">
          <div>
            <h3 className="h-sm">{t("oc.registerTitle")}</h3>
            {inv ? (
              <p id="ocInvoice">
                {inv.invoice_no}: {inv.active ? t("oc.heldBy", { lender: inv.holder || "" }) : t("oc.free")}
                <br /><span className="mono small">{t("oc.commitment")} {short(inv.commitment)}</span>
              </p>
            ) : <p className="muted">{t("oc.noInvoice")}</p>}
            <p className="small muted">{s.on_chain_data}</p>
            <div className="row">
              {user.portal === "bank" && can("bank:decide") && (
                <Button variant="ghost" id="ocDrill" onClick={async () => {
                  const r = await act(duplicateDrill, (x) => (x.refused ? t("oc.drillRefused", { holder: x.holder, block: x.block }) : t("oc.drillAccepted")));
                  if (r) reload();
                }}>{t("oc.drill")}</Button>
              )}
              {user.portal === "sme" && (can("sme:prepare") || can("sme:approve")) && (
                <Button variant="ghost" id="ocAnchor" onClick={async () => { if (await act(anchorNow, (r) => t("oc.anchored", { n: r.entries, block: r.block }))) reload(); }}>{t("oc.anchorNow")}</Button>
              )}
            </div>
          </div>
          <div>
            <h3 className="h-sm">{t("oc.anchorTitle")}</h3>
            <Scroll label={t("oc.anchorTitle")}>
              <table>
                <thead><tr><th scope="col">#</th><th scope="col">{t("oc.entries")}</th><th scope="col">{t("oc.root")}</th><th scope="col">{t("oc.check")}</th></tr></thead>
                <tbody>
                  {(s.audit?.anchors || []).map((a) => (
                    <tr key={a.index}><td>{a.index}</td><td>{a.entries}</td><td className="mono small">{short(a.root)}</td>
                      <td>{a.reproduced ? <span className="pill ok">{t("oc.ok")}</span> : <span className="pill bad">{t("oc.bad")}</span>}</td></tr>
                  ))}
                </tbody>
              </table>
            </Scroll>
            {user.portal === "sme" && (
              <div className="row mt-1">
                <label className="field">{t("oc.entry")}
                  <input type="number" min={0} value={entry} onChange={(e) => setEntry(e.target.value)} style={{ width: 110 }} />
                </label>
                <Button small variant="ghost" id="ocProof" onClick={async () => { const p = await act(() => chainProof(Number(entry))); if (p) setProof(p); }}>{t("oc.prove")}</Button>
              </div>
            )}
            {proof && (
              <p className="small mt-1" id="ocProofResult">
                {proof.verified ? "✓ " : "✗ "}{t("oc.proofText", { seq: proof.event.seq, tool: proof.event.tool, steps: proof.path.length, anchor: proof.anchor_index })}
              </p>
            )}
          </div>
        </div>
        {(s.anchor_failures || []).map((f, i) => (
          <p key={i} className="pill bad mt-1" role="alert">{t("oc.anchorFailed", { at: f.at, reason: f.reason })}</p>
        ))}
        <p className="small mt-1">{t(s.mode === "required" ? "oc.modeRequired" : "oc.modeEvm")}</p>
        <Note>{t("oc.note", { network: s.network || "" })}</Note>
        <p className="small muted">
          {Object.entries(s.contracts || {}).map(([name, c]) => `${name} ${short(c.address, 8)} (${c.compiler}, source ${c.source_sha256.slice(0, 12)})`).join(" · ")}
        </p>
      </Panel>
    </section>
  );
}
