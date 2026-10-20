import { useCase, type CaseSnapshot } from "@/entities/case";
import { WeeklyCashChart } from "@/entities/forecast";
import { useI18n } from "@/shared/i18n";
import { usd, pct } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Kpi, Kpis, Loadable, PageHead, Panel } from "@/shared/ui";
import { RoleStrip, useAuth } from "../auth";
import { BuyerConcentration } from "./components/BuyerConcentration";
import { CheckSummary } from "./components/CheckSummary";
import { DriverBars } from "./components/DriverBars";
import { FundingCostBars } from "./components/FundingCostBars";
import { NextStep } from "./components/NextStep";
import { WorkQueue } from "./components/WorkQueue";

export default function OverviewScreen(_: ScreenProps) {
  const { snapshot, error } = useCase();
  return <Loadable data={snapshot} error={error}>{(s) => <Overview s={s} />}</Loadable>;
}

function Overview({ s }: { s: CaseSnapshot }) {
  const { t } = useI18n();
  const { can } = useAuth();
  const k = s.kpis;
  const best = s.funding_options.filter((o) => o.eligible && o.apr_pct != null).sort((a, b) => (a.apr_pct ?? 0) - (b.apr_pct ?? 0))[0];
  const needPeople =
    s.verification.filter((v) => v.status !== "ELIGIBLE").length +
    s.reconciliation.rows.filter((r) => r.status === "NEEDS_HUMAN").length +
    s.alerts.length +
    s.scans.filter((x) => x.status !== "READ").length;

  return (
    <>
      <RoleStrip />
      <PageHead title={t("ov.title")} lede={t("ov.lede")} />
      <WorkQueue s={s} director={can("sme:approve")} />
      <Kpis>
        <Kpi highlight label={t("ov.cash")} value={usd(k.cash_today_usd)} foot={t("ov.cashFoot")} />
        <Kpi
          label={t("ov.gap")}
          tone="neg"
          value={k.first_shortfall_week ? t("lbl.week", { w: k.first_shortfall_week }) : "–"}
          foot={k.shortfall_usd ? <>{t("ov.gapFoot")} <b className="neg">{usd(k.shortfall_usd)}</b></> : undefined}
        />
        <Kpi
          label={t("ov.best")}
          value={best ? pct(best.apr_pct, 1) : "–"}
          foot={best ? `${best.name.split(" (")[0]}, ${t("ov.bestFoot")} ${usd(best.cost_breakdown.total_usd)}` : undefined}
        />
        <Kpi label={t("ov.todo")} tone={needPeople ? "warn" : "pos"} value={String(needPeople)} foot={t("ov.todoFoot")} />
      </Kpis>
      <div className="dash">
        <div className="span2">
          <Panel title={t("ov.weekly")} sub={t("ov.weeklySub")}><WeeklyCashChart weeks={s.forecast.weeks} /></Panel>
        </div>
        <Panel title={t("ov.buyers")} sub={t("ov.buyersSub")}><BuyerConcentration buyers={s.buyer_risk} /></Panel>
        <Panel title={t("ov.options")} sub={t("ov.optionsSub")}><FundingCostBars options={s.funding_options} bestId={best?.id} /></Panel>
        <div className="span2">
          <Panel title={t("ov.drivers", { w: k.first_shortfall_week || "–" })} sub={t("ov.driversSub")}><DriverBars drivers={s.forecast.attribution} /></Panel>
        </div>
        <Panel title={t("ov.checks")}><CheckSummary verification={s.verification} /></Panel>
        <div className="span2">
          <Panel title={t("ov.next")}><NextStep s={s} /></Panel>
        </div>
      </div>
    </>
  );
}
