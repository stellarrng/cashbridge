import { useI18n } from "@/shared/i18n";
import { Button } from "@/shared/ui";
import type { Twin } from "../types";

/** Demo-only buttons that inject business events (a late payment, a supplier delay...) into the digital twin. */
export function EventSimulator({ twin, onApply, onReset }: { twin: Twin; onApply: (kind: string) => void; onReset: () => void }) {
  const { t } = useI18n();
  return (
    <>
      <h3 className="mini">{t("core.dc.simulate")}</h3>
      <div className="row">
        {twin.catalogue.map((e) => (
          <Button key={e.kind} small variant="ghost" disabled={twin.applied.includes(e.kind)} data-tip={e.label} onClick={() => onApply(e.kind)}>
            {t("core.ev." + e.kind)}
          </Button>
        ))}
        <Button small variant="ghost" onClick={onReset}>{t("core.evReset")}</Button>
      </div>
      <p className="small muted" style={{ marginTop: 8 }}>{t("core.evCount", { e: twin.counts.events, a: twin.counts.director_alerts })}</p>
    </>
  );
}
