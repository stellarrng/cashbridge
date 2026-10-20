import { useState, type FormEvent } from "react";
import { HBars } from "@/shared/charts";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { pct, usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Kpi, Note, NumberField, PageHead, Panel, readNumbers } from "@/shared/ui";
import { assessBid, type BidAssessment } from "./api";

const DEFAULTS = {
  contract_value_usd: 200000, upfront_cost_usd: 110000, remaining_cost_usd: 55000, available_cash_usd: 60000, minimum_reserve_usd: 15000,
  advance_payment_pct: 20, stress_cost_overrun_pct: 15, loan_apr_pct: 15, financing_days: 90,
  workforce_required_hours: 400, workforce_available_hours: 300, outsourced_hourly_cost_usd: 25,
};

export default function BidSimulatorScreen(_: ScreenProps) {
  const { t } = useI18n();
  const act = useAct();
  const [x, setX] = useState<BidAssessment | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const out = await act(() => assessBid(readNumbers(e.currentTarget)));
    if (out) setX(out);
  }

  const stress = x?.stress_gap_if_advance_delayed_and_cost_overruns_usd ?? 0;
  return (
    <>
      <PageHead title={t("prj.title")} lede={t("prj.lede")} />
      <Panel title="">
        <form onSubmit={submit}>
          <div className="inputs">{Object.entries(DEFAULTS).map(([k, v]) => <NumberField key={k} name={k} value={v} />)}</div>
          <Button variant="bridge" type="submit">{t("prj.assess")}</Button>
        </form>
        <div>
          {x && (
            <>
              <div className="kpis cards" style={{ marginTop: 14 }}>
                <Kpi label="Upfront funding gap" tone={x.initial_funding_gap_usd > 0 ? "neg" : "pos"} value={usd(x.initial_funding_gap_usd)} />
                <Kpi label="Gap under stress" tone="neg" value={usd(stress)} />
                <Kpi label="Indicative margin" value={pct(x.estimated_margin_pct)} />
                <Kpi label="Team hours short" value={x.workforce_readiness.uncovered_team_hours} />
                <Kpi label="Outsourcing cost" value={usd(x.workforce_readiness.indicative_outsourcing_cost_usd)} />
              </div>
              <HBars
                items={[
                  { label: "Upfront gap", value: x.initial_funding_gap_usd, display: usd(x.initial_funding_gap_usd), cls: "cb-risk" },
                  { label: "Stress gap", value: stress, display: usd(stress), cls: "cb-neg" },
                ]}
              />
              {(x.limitations || []).map((l, i) => <Note key={i}>{l}</Note>)}
            </>
          )}
        </div>
      </Panel>
    </>
  );
}
