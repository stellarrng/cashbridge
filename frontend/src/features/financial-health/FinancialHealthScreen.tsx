import { useState, type FormEvent } from "react";
import { ColumnChart, DonutChart, LineChart } from "@/shared/charts";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { pct, usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Kpi, Kpis, Loadable, Note, NumberField, PageHead, Panel, readNumbers } from "@/shared/ui";
import { fetchSummary, runScenario } from "./api";
import type { AnalyticsSummary, ScenarioResult } from "./types";

const LABELS: Record<string, string> = {
  dso_days_estimate: "DSO", dio_days_estimate: "DIO", dpo_days: "DPO", cash_conversion_cycle_days: "CCC",
  net_working_capital_usd: "Net working capital", receivables_to_revenue_pct: "Receivables / revenue", inventory_to_cogs_pct: "Inventory / COGS",
  operating_margin_pct: "Operating margin", current_ratio: "Current ratio", quick_ratio: "Quick ratio", cash_ratio: "Cash ratio",
  gross_margin_pct: "Gross margin", ebitda_margin_pct: "EBITDA margin", interest_coverage: "Interest coverage", dscr_proxy: "DSCR (proxy)",
  debt_to_equity: "Debt / equity", cash_runway_months_gross_expenses: "Cash runway (months)",
};

const fmt = (key: string, v: number | null | undefined): string =>
  v == null ? "n/a" : key.endsWith("_usd") ? usd(v) : key.endsWith("_pct") ? pct(v) : Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });

export default function FinancialHealthScreen(_: ScreenProps) {
  const summary = useAsync(fetchSummary, []);
  return <Loadable data={summary.data} error={summary.error}>{(d) => <FinancialHealth d={d} />}</Loadable>;
}

function FinancialHealth({ d }: { d: AnalyticsSummary }) {
  const { t } = useI18n();
  const act = useAct();
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const r = d.ratios;
  const m = d.eda.monthly;
  const last = m[m.length - 1];
  const other = Math.max(0, last.expenses - last.marketing - last.payroll - (last.supplier || 0));
  const runway = r.cash_runway_months_gross_expenses;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const x = await act(() => runScenario(readNumbers(e.currentTarget)));
    if (x) setResult(x);
  }

  return (
    <>
      <PageHead title={t("fin.title")} lede={t("fin.lede")} />
      <Kpis>
        <Kpi highlight label="Current ratio" value={fmt("current_ratio", r.current_ratio)} />
        <Kpi label="Quick ratio" value={fmt("quick_ratio", r.quick_ratio)} />
        <Kpi label="Operating margin" value={fmt("operating_margin_pct", r.operating_margin_pct)} />
        <Kpi label="DSCR (proxy)" value={fmt("dscr_proxy", r.dscr_proxy)} />
        <Kpi label="Cash runway (months)" tone={runway != null && runway < 1 ? "neg" : ""} value={fmt("x", runway)} />
      </Kpis>
      <div className="dash">
        <div className="span2">
          <Panel title={t("fin.trend")}>
            <LineChart
              labels={m.map((x) => x.month.slice(2))}
              fmt={usd}
              series={[
                { name: "Revenue", values: m.map((x) => x.revenue), color: "var(--s1)" },
                { name: "Expenses", values: m.map((x) => x.expenses), color: "var(--s2)" },
              ]}
            />
            <Note>Expense outliers above 2σ: {d.eda.expense_outliers.map((x) => x.month).join(", ") || "none"}.</Note>
          </Panel>
        </div>
        <Panel title={t("fin.mix")}>
          <DonutChart
            center={usd(last.expenses)}
            centerSub={last.month}
            parts={[
              { label: "Supplier", value: last.supplier || 0, color: "var(--s1)", display: usd(last.supplier || 0) },
              { label: "Payroll", value: last.payroll, color: "var(--s2)", display: usd(last.payroll) },
              { label: "Marketing", value: last.marketing, color: "var(--s3)", display: usd(last.marketing) },
              { label: "Other", value: other, color: "var(--s4)", display: usd(other) },
            ]}
          />
        </Panel>
        <div className="span3">
          <Panel title={t("fin.ratios")} sub={d.definitions.dscr_proxy || ""}>
            <dl className="ratio-grid">
              {Object.entries(r).map(([k, v]) => (
                <div key={k}>
                  <dt>{LABELS[k] || k}</dt>
                  <dd className={v == null ? "muted" : ""}>{fmt(k, v)}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </div>
      </div>
      <Panel title={t("fin.scn")}>
        <form onSubmit={submit}>
          <div className="inputs">
            <NumberField name="marketing_increase_pct" value={25} label="Marketing +%" />
            <NumberField name="receipts_delayed_pct" value={10} label="Receipts delayed %" />
            <NumberField name="new_loan_usd" value={0} label="New loan USD" />
            <NumberField name="loan_apr_pct" value={15} label="Loan APR %" />
            <NumberField name="horizon_months" value={3} label="Months" />
            <NumberField name="minimum_reserve_usd" value={20000} label="Min reserve USD" />
          </div>
          <Button variant="bridge" type="submit">{t("fin.calc")}</Button>
        </form>
        <div>
          {result && (
            <>
              <div className="kpis cards" style={{ marginTop: 14 }}>
                <Kpi label="Baseline closing cash" value={usd(result.baseline_ending_cash_usd)} />
                <Kpi label="Scenario closing cash" value={usd(result.scenario_ending_cash_usd)} />
                <Kpi label="Lowest cash" tone={result.reserve_breach ? "neg" : ""} value={usd(result.minimum_cash_usd)} />
                <Kpi label="Reserve" tone={result.reserve_breach ? "neg" : "pos"} value={result.reserve_breach ? "breached" : "held"} />
              </div>
              {result.schedule && (
                <ColumnChart height={200} items={result.schedule.map((row) => ({ label: "M" + row.month, value: row.closing_cash_usd, cls: row.closing_cash_usd < 0 ? "cb-neg" : "cb-accent", tip: usd(row.closing_cash_usd) }))} />
              )}
              {(result.limitations || []).map((l, i) => <Note key={i}>{l}</Note>)}
            </>
          )}
        </div>
      </Panel>
    </>
  );
}
