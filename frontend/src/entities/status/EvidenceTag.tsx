import { useI18n } from "@/shared/i18n";

export const EVIDENCE_ORDER = ["VERIFIED", "CALCULATED", "MODEL_ESTIMATE", "ASSUMPTION", "NEEDS_HUMAN", "NOT_VERIFIABLE_HERE"] as const;
export type EvidenceStatus = (typeof EVIDENCE_ORDER)[number];

/** How trustworthy a claim is: verified, calculated, estimated, assumed, needs a person, or cannot be checked here. */
export function EvidenceTag({ status }: { status: string }) {
  const { t } = useI18n();
  return <span className={"st " + status}>{t("ev." + status)}</span>;
}
