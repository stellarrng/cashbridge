import type { PackVerification } from "@/entities/funding";
import { DonutChart } from "@/shared/charts";
import { useI18n } from "@/shared/i18n";
import { Button, Panel } from "@/shared/ui";

/** The lender recomputes every hash and the audit chain itself; nothing here is taken on the SME's word. */
export function VerificationPanel({ verification, onVerify }: { verification: PackVerification | null; onVerify: () => void }) {
  const { t } = useI18n();
  const v = verification;
  const count = {
    ok: v ? v.checks.filter((x) => x.ok === true).length : 0,
    no: v ? v.checks.filter((x) => x.ok === false).length : 0,
    na: v ? v.checks.filter((x) => x.ok === null).length : 0,
  };
  return (
    <Panel title={t("bk.verify")} sub={t("bk.verifySub")}>
      {v && (
        <DonutChart
          center={`${count.ok}/${v.checks.length}`}
          centerSub={t("chk.ok")}
          parts={[
            { label: t("chk.ok"), value: count.ok, color: "var(--good)" },
            { label: t("chk.no"), value: count.no, color: "var(--deficit)" },
            { label: t("chk.na"), value: count.na, color: "var(--risk)" },
          ]}
        />
      )}
      <div>
        {v ? (
          <ul className="checks">
            {v.checks.map((c, i) => (
              <li key={i}>
                <span className={"mark " + (c.ok === true ? "ok" : c.ok === false ? "no" : "na")}>{c.ok === true ? "✓" : c.ok === false ? "✗" : "?"}</span>
                <div><b>{c.check}</b><div className="detail">{c.detail || ""}</div></div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("bk.notVerified")}</p>
        )}
      </div>
      <div className="row mt-2">
        <Button variant={v ? "ghost" : "bridge"} onClick={onVerify}>{t(v ? "bk.verifyAgain" : "bk.runVerify")}</Button>
      </div>
    </Panel>
  );
}
