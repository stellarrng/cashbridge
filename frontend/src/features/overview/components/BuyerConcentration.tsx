import type { BuyerRisk } from "@/entities/case";
import { DonutChart } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { pct } from "@/shared/lib/format";
import { SERIES } from "./palette";

const BUYER_ORDER = ["B-US-01", "B-JP-01", "B-US-02", "B-CN-01"];
const shortName = (n: string) => n.replace(" (SYNTHETIC)", "").split(" ").slice(0, 2).join(" ");

export function BuyerConcentration({ buyers }: { buyers: BuyerRisk[] }) {
  const { t } = useI18n();
  // Fixed order by buyer id, so a buyer keeps its colour from one visit to the next.
  const ordered = buyers.slice().sort((a, b) => BUYER_ORDER.indexOf(a.buyer_id) - BUYER_ORDER.indexOf(b.buyer_id));
  const first = ordered[0];
  return (
    <DonutChart
      label={t("ov.buyers")}
      center={pct(first ? first.share_of_receivables_pct : 0, 0)}
      centerSub={first ? first.buyer.split(" ")[0] : ""}
      parts={ordered.map((b, i) => ({
        label: shortName(b.buyer),
        value: b.share_of_receivables_pct,
        color: SERIES[i % 4],
        display: pct(b.share_of_receivables_pct),
        flag: b.concentration_alert ? ">40%" : "",
      }))}
    />
  );
}
