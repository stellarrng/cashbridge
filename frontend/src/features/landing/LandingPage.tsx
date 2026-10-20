import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { getSession, type Portal } from "@/shared/api/session";
import { useActiveSection, useAsync, useReveal } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { usePreferences } from "@/shared/preferences";
import { AnimatedNumber, Button } from "@/shared/ui";
import { fetchTrustSummary } from "./api";
import { HeroCashChart } from "./HeroCashChart";
import { InstallGuide } from "./InstallGuide";
import { LandingNav } from "./LandingNav";
import { SignInDialog } from "./SignInDialog";

/** Header and footer are light in the light theme and dark in the dark theme, so the logo has a version for each. */
const BRAND = {
  dark: { logo: "/brand/cashbridge-logo-dark-bg.svg", mark: "/brand/cashbridge-mark.svg" },
  light: { logo: "/brand/cashbridge-logo-light-bg.svg", mark: "/brand/cashbridge-mark-light.svg" },
} as const;
/** Stagger helper: item i of a group appears `step` ms after the one before it. */
const delay = (i: number, step = 90) => ({ "--d": `${i * step}ms` }) as CSSProperties;

const NAV_SECTIONS = ["flow", "portals", "trust", "install"] as const;
const NAV_LABEL: Record<(typeof NAV_SECTIONS)[number], string> = { flow: "nav.flow", portals: "nav.portals", trust: "land.trust", install: "nav.install" };

const STEPS = [
  { n: 1, who: "agent" }, { n: 2, who: "agent" }, { n: 3, who: "agent" }, { n: 4, who: "director" }, { n: 5, who: "lender" },
] as const;
const SME_CAN = ["p.sme.c1", "p.sme.c2", "p.sme.c3", "p.sme.c5", "p.sme.c4"];
const SME_CANNOT = ["p.sme.x1", "p.sme.x2"];
const BANK_CAN = ["p.bank.c1", "p.bank.c2", "p.bank.c3", "p.bank.c4"];
const BANK_CANNOT = ["p.bank.x1", "p.bank.x2"];

type ClaimTone = "ok" | "mock" | "none";
const CLAIMS: ReadonlyArray<{ tone: ClaimTone; title: string; text: string }> = [
  { tone: "ok", title: "cl.works", text: "cl.works.d" },
  { tone: "mock", title: "cl.mock", text: "cl.mock.d" },
  { tone: "none", title: "cl.not", text: "cl.not.d" },
];

/** Status marks that differ by shape as well as colour: check (works), half circle (mocked), minus (not claimed). */
const CLAIM_ICON: Record<ClaimTone, ReactNode> = {
  ok: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
  ),
  mock: (
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="2.2" /><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" /></svg>
  ),
  none: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 12h12" /></svg>
  ),
};

export function LandingPage() {
  const { t } = useI18n();
  const { resolvedTheme } = usePreferences();
  const brand = resolvedTheme === "dark" ? BRAND.dark : BRAND.light;
  const params = new URLSearchParams(window.location.search);
  const existing = getSession();
  const returning = existing?.user && params.get("stay") !== "1" ? existing.user.portal : null;

  const [authOpen, setAuthOpen] = useState(params.has("signin"));
  const [portal, setPortal] = useState<Portal>(params.get("signin") === "bank" ? "bank" : "sme");
  const [signedOut, setSignedOut] = useState(params.has("signedout"));
  const scores = useAsync(() => fetchTrustSummary().catch(() => null), []);
  const [activeSection, pinSection] = useActiveSection(NAV_SECTIONS);
  useReveal();

  // Confirm a sign-out once, then drop the flag from the address bar.
  useEffect(() => {
    if (!signedOut) return;
    window.history.replaceState(null, "", "/");
    const timer = window.setTimeout(() => setSignedOut(false), 3200);
    return () => window.clearTimeout(timer);
  }, [signedOut]);

  const open = (p: Portal) => {
    setPortal(p);
    setAuthOpen(true);
  };

  /** A person already signed in on this tab gets a direct way back instead of the dialog. */
  function CtaButton({ target, variant, label }: { target: Portal; variant: "bridge" | "bank" | "ghost" | ""; label: string }) {
    const back = returning === target;
    return (
      <Button variant={variant} onClick={() => (back ? (window.location.href = "/app") : open(target))}>
        {back ? t(target === "bank" ? "auth.back.bank" : "auth.back.sme") : label}
      </Button>
    );
  }

  const s = scores.data?.summary;
  const stats = [
    { value: s ? `${s.security.passed}/${s.security.total}` : t("trust.na"), text: t("trust.sec") },
    { value: s ? `${s.agent.passed}/${s.agent.total}` : t("trust.na"), text: t("trust.agent") },
    { value: s ? s.model.brier_model.toFixed(3) : t("trust.na"), text: t("trust.model") },
  ];

  return (
    <div className="land">
      <a className="sr-only" href="#main">Skip to content</a>
      <LandingNav
        logo={brand.logo}
        mark={brand.mark}
        active={activeSection}
        onNavigate={pinSection}
        onSignIn={() => open("sme")}
        links={NAV_SECTIONS.map((id) => ({ id, label: t(NAV_LABEL[id]) }))}
      />

      <main id="main">
        <section className="hero-wrap" id="top">
          <div className="hero wrap">
            <div className="hero-copy on-navy">
              <p className="kicker rise">{t("hero.kicker")}</p>
              <h1 className="rise d1">{t("hero.title")}</h1>
              <p className="lede rise d2">{t("hero.lede")}</p>
              <div className="cta rise d3">
                <CtaButton target="sme" variant="bridge" label={t("hero.sme")} />
                <CtaButton target="bank" variant="ghost" label={t("hero.bank")} />
              </div>
              <p className="fineprint rise d3">{t("hero.fine")}</p>
            </div>
            <HeroCashChart />
          </div>
          <div className="stats on-navy wrap rise d4">
            {stats.map((x, i) => (
              <div key={i} className="stat">
                <b><AnimatedNumber text={x.value} /></b>
                <span>{x.text}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="sec sec--surface" id="flow">
          <div className="wrap">
            <div className="section-head reveal">
              <h2>{t("flow.title")}</h2>
              <p>{t("flow.lede")}</p>
            </div>
            <ol className="steps">
              {STEPS.map(({ n, who }, i) => (
                <li key={n} className="reveal" style={delay(i)}>
                  <span className="step-no" aria-hidden="true">{String(n).padStart(2, "0")}</span>
                  <span className={"who " + who}>{t("who." + who)}</span>
                  <h3>{t(`s${n}.t`)}</h3>
                  <p>{t(`s${n}.d`)}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="sec sec--paper" id="portals">
          <div className="wrap">
            <div className="section-head reveal">
              <h2>{t("portals.title")}</h2>
              <p>{t("portals.lede")}</p>
            </div>
            <div className="split">
              <PortalCard index={0} kind="sme" can={SME_CAN} cannot={SME_CANNOT} action={<CtaButton target="sme" variant="bridge" label={t("p.sme.b")} />} />
              <PortalCard index={1} kind="bank" can={BANK_CAN} cannot={BANK_CANNOT} action={<CtaButton target="bank" variant="bank" label={t("p.bank.b")} />} />
            </div>
          </div>
        </section>

        <section className="sec sec--surface" id="trust">
          <div className="wrap">
            <div className="section-head reveal">
              <h2>{t("trust.title")}</h2>
              <p><RichCode text={t("trust.lede")} /></p>
            </div>
            <div className="scores">
              <div className={"score reveal" + (s ? "" : " na")} style={delay(0)}>
                <b><AnimatedNumber text={s ? `${s.security.passed}/${s.security.total}` : t("trust.na")} /></b>
                <span>{t("trust.sec")}</span>
              </div>
              <div className={"score reveal" + (s ? "" : " na")} style={delay(1)}>
                <b><AnimatedNumber text={s ? `${s.agent.passed}/${s.agent.total}` : t("trust.na")} /></b>
                <span>{t("trust.agent")}</span>
              </div>
              <div className={"score model reveal" + (s ? "" : " na")} style={delay(2)}>
                <b><AnimatedNumber text={s ? `${s.model.brier_model.toFixed(3)} vs ${s.model.brier_baseline.toFixed(3)}` : t("trust.na")} /></b>
                <em className="score-note">{t("trust.lower")}</em>
                <span>{t("trust.model")}</span>
              </div>
            </div>
            <div className="claims">
              {CLAIMS.map((c, i) => (
                <div key={c.title} className={"claim reveal " + c.tone} style={delay(i, 110)}>
                  <span className="claim-ico">{CLAIM_ICON[c.tone]}</span>
                  <div>
                    <h3>{t(c.title)}</h3>
                    <p>{t(c.text)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <InstallGuide />
      </main>

      <footer className="foot on-navy">
        <div className="wrap foot-row">
          <a className="logo" href="#top" aria-label="CashBridge home">
            <img src={brand.logo} alt="CashBridge" width="141" height="30" />
          </a>
          <span>{t("foot")}</span>
          <a href="/docs">{t("foot.api")}</a>
        </div>
      </footer>

      <SignInDialog open={authOpen} portal={portal} onPortal={setPortal} onClose={() => setAuthOpen(false)} />
      {signedOut && (
        <div role="status" className="toast show">
          {t("auth.signedOut")}
        </div>
      )}
    </div>
  );
}

/** Renders `<code>…</code>` spans from a translation as real elements, so no HTML is ever injected. */
function RichCode({ text }: { text: string }) {
  return <>{text.split(/(<code>.*?<\/code>)/g).map((part, i) => (part.startsWith("<code>") ? <code key={i}>{part.slice(6, -7)}</code> : part))}</>;
}

function PortalCard({ index, kind, can, cannot, action }: { index: number; kind: "sme" | "bank"; can: string[]; cannot: string[]; action: ReactNode }) {
  const { t } = useI18n();
  return (
    <article className={"portal reveal " + kind} style={delay(index, 140)}>
      <img className="portal-art" src={`/brand/cashbridge-${kind}.svg`} alt="" width="560" height="440" loading="lazy" decoding="async" />
      <h3>{t(`p.${kind}.t`)}</h3>
      <p className="portal-who">{t(`p.${kind}.who`)}</p>
      <ul className="can">{can.map((k) => <li key={k}>{t(k)}</li>)}</ul>
      <ul className="cannot">{cannot.map((k) => <li key={k}>{t(k)}</li>)}</ul>
      {action}
    </article>
  );
}
