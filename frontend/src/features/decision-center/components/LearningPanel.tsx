import { useState } from "react";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { pp, usd, usd2 } from "@/shared/lib/format";
import { Button, Panel, Scroll } from "@/shared/ui";
import { useAuth } from "../../auth";
import { decideUpdate, proposeUpdate, simulateOutcome } from "../api";
import type { IntelligenceData, SimulatedOutcome } from "../types";

const shifts = (m: Record<string, number>) => Object.entries(m).map(([b, v]) => `${b} ${v > 0 ? "+" : ""}${v}`).join(", ");

function Outcome({ result }: { result: SimulatedOutcome }) {
  const { t } = useI18n();
  const o = result.outcome;
  return (
    <div className="caution">
      <b>{t("core.outcome")} {result.run_id}: {o.goal_met ? t("core.met") : t("core.missed")}</b>
      <p>{o.attribution.label}. {o.attribution.lesson}</p>
      <p className="small muted">
        trough {usd2(o.trough_usd)} ({t("lbl.week", { w: o.trough_week })}) · {Object.entries(o.contributions_usd).map(([k, v]) => `${k.replaceAll("_", " ")} ${usd(v)}`).join(" · ")}
      </p>
    </div>
  );
}

/** The model registry: the active world model, a pending update awaiting the Director, and what the planner learned. */
export function LearningPanel({ data, hasPlan, onChanged }: { data: IntelligenceData; hasPlan: boolean; onChanged: () => void }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const act = useAct();
  const [outcome, setOutcome] = useState<SimulatedOutcome | null>(null);
  const L = data.learning;
  const reg = L.registry;
  const pend = reg.pending;

  const simulate = async () => {
    const r = await act(simulateOutcome);
    if (r) setOutcome(r);
  };
  const propose = async () => {
    if (await act(proposeUpdate, t("core.pending"))) onChanged();
  };
  const decide = async (approve: boolean) => {
    if (await act(() => decideUpdate(approve, approve ? "held-out gate passed" : "rejected"), "OK")) onChanged();
  };

  return (
    <Panel title={t("core.learn")} sub={t("core.learnSub")}>
      <div className="grid2">
        <div>
          <h3 className="mini">{t("core.active")}</h3>
          <p><b className="mono">{reg.active_version}</b> <span className="pill">{reg.active.label}</span></p>
          <p className="small muted">buyer shifts: {shifts(reg.active.buyer_logit_shift) || "none"} · order shipment scale {reg.active.ship_scale} · slowdown {pp(reg.active.slowdown_prob)}</p>
          <p className="small">{t("core.episodes")}: <b>{L.episodes}</b> ({L.episodes_with_miss} {t("core.missed")})</p>
        </div>
        <div>
          <h3 className="mini">{t("core.pending")}</h3>
          {pend ? (
            <>
              <p><b className="mono">{pend.version}</b> · {pend.proposed_by}</p>
              <p className="small">
                {t("core.gate")}: {pend.metrics.reason} ({pend.metrics.loglik_current} → {pend.metrics.loglik_candidate}, {pend.metrics.held_out_wins}/{pend.metrics.episodes})
              </p>
              <p className="small muted">buyer shifts: {shifts(pend.params.buyer_logit_shift)} · ship scale {pend.params.ship_scale}</p>
              {can("sme:approve") && (
                <div className="row">
                  <Button variant="bridge" disabled={!pend.metrics.accepted} onClick={() => void decide(true)}>{t("core.approve")}</Button>
                  <Button variant="ghost" onClick={() => void decide(false)}>{t("core.reject")}</Button>
                </div>
              )}
            </>
          ) : (
            <p className="muted">{t("core.noPending")}</p>
          )}
        </div>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        {hasPlan && <Button variant="ghost" onClick={() => void simulate()}>{t("core.simulate")}</Button>}
        {can("sme:prepare") && <Button variant="ghost" onClick={() => void propose()}>{t("core.propose")}</Button>}
      </div>
      <div>{outcome && <Outcome result={outcome} />}</div>
      <h3 className="mini">{t("core.history")}</h3>
      <Scroll>
        <table>
          <tbody>
            {reg.history.slice().reverse().map((h, i) => (
              <tr key={i}>
                <td className="mono small">{h.version}</td>
                <td>{h.label}</td>
                <td className="small">{h.approved_by || h.rejected_by || ""}</td>
                <td className="small muted">{h.ts || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Scroll>
      {L.recent.length > 0 && (
        <>
          <h3 className="mini">{t("core.episodes")}</h3>
          <Scroll>
            <table>
              <tbody>
                {L.recent.map((e, i) => (
                  <tr key={i}>
                    <td className="mono small">{e.run_id} <span className="pill">{e.source}</span></td>
                    <td className="small">{e.plan}</td>
                    <td>{pp(e.predicted_p_goal)}</td>
                    <td>{e.goal_met ? <span className="pill ok">{t("core.met")}</span> : <span className="pill bad">{t("core.missed")}</span>}</td>
                    <td className="small muted">{e.cause}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </>
      )}
    </Panel>
  );
}
