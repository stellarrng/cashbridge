import type { FundingOption } from "@/entities/funding";
import { HBars } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { pct, usd2 } from "@/shared/lib/format";

export function FundingCostBars({ options, bestId }: { options: FundingOption[]; bestId?: string }) {
  const { t } = useI18n();
  return (
    <HBars
      items={options
        .filter((o) => o.apr_pct != null)
        .map((o) => ({
          label: t("opt." + o.type),
          value: o.apr_pct as number,
          display: pct(o.apr_pct, 1),
          cls: o.id === bestId ? "cb-accent" : "cb-muted",
          strong: o.id === bestId,
          tip: `${o.name}\n${t("col.apr")}: ${pct(o.apr_pct, 2)}\n${t("col.amount")}: ${usd2(o.amount_usd)}\n${t("col.total")}: ${o.cost_breakdown.total_usd != null ? usd2(o.cost_breakdown.total_usd) : "–"}`,
        }))}
    />
  );
}
