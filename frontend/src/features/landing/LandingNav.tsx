import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { useI18n } from "@/shared/i18n";
import { Button, LangSwitch, ThemeButton } from "@/shared/ui";

export interface NavLink {
  id: string;
  label: string;
}

interface Props {
  logo: string;
  /** The arch on its own, shown instead of the full logo on phones. */
  mark: string;
  links: NavLink[];
  /** Id of the section the reader is in ("" while the hero shows). */
  active: string;
  /** A section link was clicked: highlight it straight away. */
  onNavigate: (id: string) => void;
  onSignIn: () => void;
}

const MENU = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
);
const CLOSE = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
);

interface Indicator {
  x: number;
  w: number;
  on: boolean;
  /** The underline was hidden a moment ago: jump to the link instead of sliding in from the left. */
  snap: boolean;
}

/**
 * Landing header: logo left, section links centred, language / theme / sign-in right.
 * - a gold underline slides from link to link as you scroll or click
 * - a thin progress line along the bottom edge fills as you read down the page
 * - the bar shrinks and gains a shadow once the page scrolls
 * - below 960px the links move into a menu that slides open under the bar
 */
export function LandingNav({ logo, mark, links, active, onNavigate, onSignIn }: Props) {
  const { t } = useI18n();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [ind, setInd] = useState<Indicator>({ x: 0, w: 0, on: false, snap: true });
  const linksEl = useRef<HTMLElement>(null);
  const progress = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      setScrolled(window.scrollY > 8);
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (progress.current) progress.current.style.transform = `scaleX(${max > 0 ? Math.min(1, window.scrollY / max) : 0})`;
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(frame);
    };
  }, []);

  // Put the underline under the active link; measure again when labels change (language) or fonts finish loading.
  const labels = links.map((l) => l.label).join("|");
  useLayoutEffect(() => {
    const measure = () => {
      const a = linksEl.current?.querySelector<HTMLElement>('a[aria-current="true"]');
      setInd((prev) => (a ? { x: a.offsetLeft, w: a.offsetWidth, on: true, snap: !prev.on } : { ...prev, on: false }));
    };
    measure();
    void document.fonts?.ready.then(measure);
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [active, labels]);

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

  // `inert` keeps the closed menu out of the tab order; React 18's types do not know the attribute yet.
  const inert = (open ? {} : { inert: "" }) as Record<string, unknown>;

  return (
    <header className={"nav on-navy" + (scrolled ? " scrolled" : "") + (open ? " menu-open" : "")}>
      <div className="wrap nav-row">
        <a className="logo" href="#top" aria-label="CashBridge home" onClick={() => setOpen(false)}>
          <img className="logo-full" src={logo} alt="CashBridge" width="178" height="38" />
          <img className="logo-mark" src={mark} alt="" width="55" height="24" />
        </a>
        <nav className="nav-links" aria-label="Page sections" ref={linksEl}>
          {links.map((l) => (
            <a key={l.id} href={"#" + l.id} aria-current={active === l.id ? "true" : undefined} onClick={() => onNavigate(l.id)}>{l.label}</a>
          ))}
          <span className="nav-ind" aria-hidden="true" style={{ transform: `translateX(${ind.x}px)`, width: ind.w, opacity: ind.on ? 1 : 0, transition: ind.snap ? "opacity 0.2s" : undefined }} />
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
      <div id="nav-menu" className={"nav-menu" + (open ? " open" : "")} aria-hidden={!open} {...inert}>
        <div className="nav-menu-in">
          <div className="wrap">
            {links.map((l, i) => (
              <a key={l.id} href={"#" + l.id} style={{ "--i": i } as CSSProperties} aria-current={active === l.id ? "true" : undefined} onClick={() => { onNavigate(l.id); setOpen(false); }}>{l.label}</a>
            ))}
          </div>
        </div>
      </div>
      <span className="nav-progress" aria-hidden="true" ref={progress} />
    </header>
  );
}
