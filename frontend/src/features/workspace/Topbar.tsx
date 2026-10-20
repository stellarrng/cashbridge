import { useEffect } from "react";
import { useI18n } from "@/shared/i18n";
import { human, sentence } from "@/shared/lib/format";
import { Button, LangSwitch, ThemeButton } from "@/shared/ui";
import { useAuth } from "../auth";
import { useSnapshotContext } from "@/entities/case";

export function Topbar({ onAssistant, onMenu, menuOpen }: { onAssistant: () => void; onMenu: () => void; menuOpen: boolean }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const { snapshot } = useSnapshotContext();
  const bank = user.portal === "bank";
  const portalName = t(bank ? "app.bank" : "app.sme");

  useEffect(() => {
    document.title = portalName + " | CashBridge";
  }, [portalName]);

  return (
    <header className="top on-navy">
      <button type="button" className="icon-btn burger" aria-label={t("app.menu")} aria-expanded={menuOpen} aria-controls="side" onClick={onMenu}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
      </button>
      <a className="logo" href="/?stay=1" aria-label="CashBridge home">
        <img className="logo-full" src="/brand/cashbridge-logo-dark-bg.svg" alt="CashBridge" width="156" height="33" />
        <img className="logo-mark" src="/brand/cashbridge-mark.svg" alt="" width="55" height="24" />
      </a>
      <span className={"portal-tag" + (bank ? " bank" : "")}>{portalName}</span>
      <div className="top-right">
        <span className="case" id="caseTag">{bank ? user.org : snapshot ? `${snapshot.meta.case_id} · ${sentence(human(snapshot.meta.case_state))}` : ""}</span>
        <LangSwitch />
        <ThemeButton />
        {!bank && <Button small variant="ghost" onClick={onAssistant}>{t("app.assistant")}</Button>}
      </div>
    </header>
  );
}
