import { useEffect } from "react";
import { useI18n } from "@/shared/i18n";
import { human } from "@/shared/lib/format";
import { Button, LangSwitch, LogoMark, ThemeButton } from "@/shared/ui";
import { useAuth } from "../auth";
import { useSnapshotContext } from "@/entities/case";

export function Topbar({ onAssistant }: { onAssistant: () => void }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const { snapshot } = useSnapshotContext();
  const bank = user.portal === "bank";
  const portalName = t(bank ? "app.bank" : "app.sme");

  useEffect(() => {
    document.title = portalName + " | CashBridge";
  }, [portalName]);

  return (
    <header className="top">
      <a className="logo" href="/?stay=1" aria-label="CashBridge home">
        <LogoMark />
        <span>CashBridge</span>
      </a>
      <span className={"portal-tag" + (bank ? " bank" : "")}>{portalName}</span>
      <div className="top-right">
        <span className="case">{bank ? user.org : snapshot ? `${snapshot.meta.case_id} · ${human(snapshot.meta.case_state)}` : ""}</span>
        <LangSwitch />
        <ThemeButton />
        {!bank && <Button small variant="ghost" onClick={onAssistant}>{t("app.assistant")}</Button>}
      </div>
    </header>
  );
}
