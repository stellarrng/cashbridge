import { StatusPill } from "@/entities/status";
import { useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { pct, usd2 } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { Empty, Kpi, Kpis, Loadable, PageHead } from "@/shared/ui";
import { RoleStrip } from "../../auth";
import { fetchInbox } from "../api";

const DECIDED = ["FUNDED_MOCK", "DECLINED"];

/** Packs the SME Director released to this lender. Nothing else about the SME is visible here. */
export default function InboxScreen(_: ScreenProps) {
  const { t } = useI18n();
  const inbox = useAsync(fetchInbox, []);
  return (
    <Loadable data={inbox.data} error={inbox.error}>
      {({ items }) => {
        const decided = items.filter((i) => DECIDED.includes(i.review.status)).length;
        const waiting = items.length - decided;
        return (
          <>
            <RoleStrip />
            <PageHead title={t("bk.inbox")} lede={t("bk.notice")} />
            <Kpis>
              <Kpi highlight label={t("bk.received")} value={items.length} />
              <Kpi label={t("bk.awaiting")} tone={waiting ? "warn" : ""} value={waiting} />
              <Kpi label={t("bk.decided")} value={decided} />
            </Kpis>
            {items.length ? (
              items.map((i) => (
                <a key={i.pack_id} className="inbox-item" href={"#case/" + i.pack_id}>
                  <div>
                    <b>{i.company}</b>
                    <div>{i.product}: {usd2(i.amount_usd)} · {pct(i.apr_pct, 2)} · {i.invoice_no}</div>
                    <div className="muted small">{i.pack_id} · {i.prepared_by} → {i.submitted_by} · {i.lender_ref}</div>
                  </div>
                  <StatusPill status={i.review.status} />
                </a>
              ))
            ) : (
              <Empty title={t("bk.empty")}>{t("bk.emptyD")}</Empty>
            )}
          </>
        );
      }}
    </Loadable>
  );
}
