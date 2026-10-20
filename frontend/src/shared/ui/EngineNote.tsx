import { useI18n } from "../i18n";

/** Reminder (non-English UI only) that engine output such as agent findings and letters stays in English. */
export function EngineNote() {
  const { lang, t } = useI18n();
  return lang === "en" ? null : <p className="note engine-note adv">{t("ui.engineNote")}</p>;
}
