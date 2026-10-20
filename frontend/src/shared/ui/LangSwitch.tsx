import { LANGS, useI18n } from "../i18n";

export function LangSwitch() {
  const { lang, setLang } = useI18n();
  return (
    <div className="lang" role="group" aria-label="Language">
      {LANGS.map((l) => (
        <button key={l.id} type="button" aria-pressed={l.id === lang} aria-label={l.name} lang={l.id} onClick={() => setLang(l.id)}>
          {l.label}
        </button>
      ))}
    </div>
  );
}
