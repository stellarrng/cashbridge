import { useEffect, useState } from "react";
import { useI18n } from "@/shared/i18n";
import { Button, LangSwitch, ThemeButton } from "@/shared/ui";

export interface NavLink {
  id: string;
  label: string;
}

interface Props {
  logo: string;
  links: NavLink[];
  /** Id of the section the reader is in ("" while the hero shows). */
  active: string;
  onSignIn: () => void;
}

const MENU = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
);
const CLOSE = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
);

/**
 * Landing header: logo left, section links centred, language / theme / sign-in right. It gains a soft shadow once the
 * page scrolls, and below 960px the links move into a menu that opens under the bar.
 */
export function LandingNav({ logo, links, active, onSignIn }: Props) {
  const { t } = useI18n();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onResize = () => window.innerWidth > 960 && setOpen(false);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  return (
    <header className={"nav on-navy" + (scrolled ? " scrolled" : "")}>
      <div className="wrap nav-row">
        <a className="logo" href="#top" aria-label="CashBridge home" onClick={() => setOpen(false)}>
          <img src={logo} alt="CashBridge" width="190" height="38" />
        </a>
        <nav className="nav-links" aria-label="Page sections">
          {links.map((l) => (
            <a key={l.id} href={"#" + l.id} aria-current={active === l.id ? "true" : undefined}>{l.label}</a>
          ))}
        </nav>
        <div className="nav-tools">
          <LangSwitch />
          <ThemeButton />
          <Button small variant="bridge" onClick={onSignIn}>{t("nav.signin")}</Button>
          <button type="button" className="icon-btn nav-burger" aria-expanded={open} aria-controls="nav-menu" aria-label={t("nav.menu")} onClick={() => setOpen((o) => !o)}>
            {open ? CLOSE : MENU}
          </button>
        </div>
      </div>
      <div id="nav-menu" className="nav-menu" hidden={!open}>
        <div className="wrap">
          {links.map((l) => (
            <a key={l.id} href={"#" + l.id} aria-current={active === l.id ? "true" : undefined} onClick={() => setOpen(false)}>{l.label}</a>
          ))}
        </div>
      </div>
    </header>
  );
}
