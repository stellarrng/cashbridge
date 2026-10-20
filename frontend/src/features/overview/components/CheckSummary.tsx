import type { InvoiceVerification } from "@/entities/case";
import { DonutChart } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";

export function CheckSummary({ verification }: { verification: InvoiceVerification[] }) {
  const { t } = useI18n();
  const count = (status: string) => verification.filter((v) => v.status === status).length;
  return (
    <DonutChart
      label={t("ov.checks")}
      center={`${count("ELIGIBLE")}/${verification.length}`}
      centerSub={t("st.ELIGIBLE")}
      parts={[
        { label: t("st.ELIGIBLE"), value: count("ELIGIBLE"), color: "var(--good)", display: count("ELIGIBLE") },
        { label: t("st.FLAGGED"), value: count("FLAGGED"), color: "var(--risk)", display: count("FLAGGED") },
        { label: t("st.BLOCKED"), value: count("BLOCKED"), color: "var(--deficit)", display: count("BLOCKED") },
      ]}
    />
  );
}
