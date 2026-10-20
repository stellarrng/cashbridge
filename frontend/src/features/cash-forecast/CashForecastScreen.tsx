import { useEffect, useRef, useState } from "react";
import { useCase, type CaseSnapshot } from "@/entities/case";
import { WeeklyCashChart, type ForecastWeek, type ScenarioDelta } from "@/entities/forecast";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { pct, usd, usd2 } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Kpi, Kpis, Loadable, Meter, PageHead, Panel, Scroll } from "@/shared/ui";
import { simulate } from "./api";

const SLIDER_LABEL: Record<string, string> = {
  dso_change_days: "cash.sl.dso",
  deposit_pct: "cash.sl.dep",
  tariff_shared_pct: "cash.sl.tar",
  fx_change_pct: "cash.sl.fx",
};

export default function CashForecastScreen(_: ScreenProps) {
  const { snapshot, error } = useCase();
  return <Loadable data={snapshot} error={error}>{(s) => <CashForecast s={s} />}</Loadable>;
}

function CashForecast({ s }: { s: CaseSnapshot }) {
  const { t } = useI18n();
  const act = useAct();
  const k = s.kpis;
  const controls = Object.entries(s.scenario_controls);
  const defaults = Object.fromEntries(controls.map(([key, c]) => [key, c.default]));
  const [values, setValues] = useState<Record<string, number>>(defaults);
  // null until the first what-if: until then the screen shows the live case forecast.
  const [simulated, setSimulated] = useState<ForecastWeek[] | null>(null);
  const [delta, setDelta] = useState<ScenarioDelta | null>(null);
  const timer = useRef<number>();

  // What-if: the server recomputes the forecast; we wait for a pause in dragging before asking.
  function change(next: Record<string, number>) {
    setValues(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      const r = await act(() => simulate(next));
      if (!r) return;
      setSimulated(r.forecast.weeks);
      setDelta(r.delta);
    }, 180);
  }
  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <>
      <PageHead title={t("cash.title")} lede={t("cash.lede")} />
      <Kpis>
        <Kpi highlight label={t("ov.cash")} value={usd(k.cash_today_usd)} />
        <Kpi tone="neg" label={t("cash.firstNeg")} value={k.first_shortfall_week ? t("lbl.week", { w: k.first_shortfall_week }) : "–"} />
        <Kpi tone="neg" label={t("cash.short")} value={k.shortfall_usd ? "−" + usd(k.shortfall_usd) : "–"} />
        <Kpi label={t("cash.ccc")} value={k.ccc.ccc + " d"} />
        <Kpi label={t("cash.blocked")} value={k.blocked_fraud_count} />
      </Kpis>
      <Panel title={t("ov.weekly")} sub={t("ov.weeklySub")}>
        <div><WeeklyCashChart weeks={simulated ?? s.forecast.weeks} /></div>
        <div>
          {delta && (
            <div className="delta">
              <span>{t("cash.firstNeg")}: <b>{delta.first_shortfall_week_before ?? "–"}</b> → <b>{delta.first_shortfall_week_after ?? "–"}</b></span>
              <span>{t("cash.lowest")}: <b>{usd(delta.min_closing_before_usd)}</b> → <b>{usd(delta.min_closing_after_usd)}</b></span>
            </div>
          )}
        </div>
      </Panel>
      <div className="grid2">
        <Panel title={t("cash.try")} sub={t("cash.trySub")}>
          <div>
            {controls.map(([key, c]) => (
              <label key={key} className="slider">
                {t(SLIDER_LABEL[key] || key)} <output>{values[key]}</output>
                <input type="range" name={key} min={c.min} max={c.max} step={c.step} value={values[key]} onChange={(e) => change({ ...values, [key]: Number(e.target.value) })} />
              </label>
            ))}
          </div>
          <div className="row mt-2">
            <Button small variant="ghost" onClick={() => change(defaults)}>{t("cash.reset")}</Button>
          </div>
        </Panel>
        <Panel title={t("ov.drivers", { w: k.first_shortfall_week || "–" })} sub={t("ov.driversSub")}>
          <table>
            <tbody>
              {s.forecast.attribution.map((a, i) => (
                <tr key={i}>
                  <td>{a.driver}<div className="muted small mono">{a.source_ref}</div></td>
                  <td className="num">{usd2(a.amount_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
      <Panel title={t("cash.risk")} sub={`${s.risk_model.method}, ${s.risk_model.training_rows}. ${s.risk_model.on_time_definition}.`}>
        <Scroll>
          <table>
            <thead>
              <tr>
                <th>{t("cash.col.buyer")}</th>
                <th className="num">{t("cash.col.share")}</th>
                <th className="num">{t("cash.col.late")}</th>
                <th>{t("cash.col.p")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {s.buyer_risk.map((b) => (
                <tr key={b.buyer_id}>
                  <td>{b.buyer}{!b.has_history && <div className="muted small">{t("cash.noHist")}</div>}</td>
                  <td className="num">{pct(b.share_of_receivables_pct)}</td>
                  <td className="num">{b.avg_days_late}</td>
                  <td><Meter ratio={b.p_on_time} tip={Math.round(b.p_on_time * 100) + "%"} /> {Math.round(b.p_on_time * 100)}%</td>
                  <td>{b.concentration_alert && <span className="pill bad">{t("cash.conc")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
      </Panel>
    </>
  );
}
