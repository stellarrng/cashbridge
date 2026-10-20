import { useEffect, useState } from "react";
import { getSession, type Portal } from "@/shared/api/session";
import { useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { Button, LangSwitch, LogoMark, ThemeButton } from "@/shared/ui";
import { fetchTrustSummary } from "./api";
import { HeroCashChart } from "./HeroCashChart";
import { SignInDialog } from "./SignInDialog";

const STEPS = [
  { n: 1, who: "agent" }, { n: 2, who: "agent" }, { n: 3, who: "agent" }, { n: 4, who: "director" }, { n: 5, who: "lender" },
] as const;
const SME_CAN = ["p.sme.c1", "p.sme.c2", "p.sme.c3", "p.sme.c5", "p.sme.c4"];
const SME_CANNOT = ["p.sme.x1", "p.sme.x2"];
const BANK_CAN = ["p.bank.c1", "p.bank.c2", "p.bank.c3", "p.bank.c4"];
const BANK_CANNOT = ["p.bank.x1", "p.bank.x2"];

export function LandingPage() {
  const { t } = useI18n();
  const params = new URLSearchParams(window.location.search);
  const existing = getSession();
  const returning = existing?.user && params.get("stay") !== "1" ? existing.user.portal : null;

  const [authOpen, setAuthOpen] = useState(params.has("signin"));
  const [portal, setPortal] = useState<Portal>(params.get("signin") === "bank" ? "bank" : "sme");
  const [signedOut, setSignedOut] = useState(params.has("signedout"));
  const scores = useAsync(() => fetchTrustSummary().catch(() => null), []);

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
  function CtaButton({ target, variant, label }: { target: Portal; variant: "bridge" | "ghost" | ""; label: string }) {
    const back = returning === target;
    return (
      <Button variant={variant} onClick={() => (back ? (window.location.href = "/app") : open(target))}>
        {back ? t(target === "bank" ? "auth.back.bank" : "auth.back.sme") : label}
      </Button>
    );
  }

  const s = scores.data?.summary;

  return (
    <>
      <a className="sr-only" href="#main">Skip to content</a>
      <header className="nav">
        <div className="wrap nav-row">
          <a className="logo" href="#top" aria-label="CashBridge home">
            <LogoMark />
            CashBridge
          </a>
          <nav className="nav-links" aria-label="Page sections">
            <a href="#flow">{t("nav.flow")}</a>
            <a href="#portals">{t("nav.portals")}</a>
            <a href="#trust">{t("land.trust")}</a>
          </nav>
          <div className="nav-tools">
            <LangSwitch />
            <ThemeButton />
            <Button small variant="ghost" onClick={() => open("sme")}>{t("nav.signin")}</Button>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="hero wrap" id="top">
          <div className="hero-copy">
            <p className="kicker">{t("hero.kicker")}</p>
            <h1>{t("hero.title")}</h1>
            <p className="lede">{t("hero.lede")}</p>
            <div className="cta">
              <CtaButton target="sme" variant="bridge" label={t("hero.sme")} />
              <CtaButton target="bank" variant="ghost" label={t("hero.bank")} />
            </div>
            <p className="fineprint">{t("hero.fine")}</p>
          </div>
          <HeroCashChart />
        </section>

        <section className="band" id="flow">
          <div className="wrap">
            <div className="section-head">
              <h2>{t("flow.title")}</h2>
              <p>{t("flow.lede")}</p>
            </div>
            <ol className="steps">
              {STEPS.map(({ n, who }) => (
                <li key={n}>
                  <span className={"who " + (who === "agent" ? "agent" : "person")}>{t("who." + who)}</span>
                  <h3>{t(`s${n}.t`)}</h3>
                  <p>{t(`s${n}.d`)}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="wrap portals" id="portals">
          <div className="section-head">
            <h2>{t("portals.title")}</h2>
            <p>{t("portals.lede")}</p>
          </div>
          <div className="split">
            <PortalCard kind="sme" can={SME_CAN} cannot={SME_CANNOT} action={<CtaButton target="sme" variant="bridge" label={t("p.sme.b")} />} />
            <PortalCard kind="bank" can={BANK_CAN} cannot={BANK_CANNOT} action={<CtaButton target="bank" variant="" label={t("p.bank.b")} />} />
          </div>
        </section>

        <section className="band" id="trust">
          <div className="wrap">
            <div className="section-head">
              <h2>{t("trust.title")}</h2>
              <p dangerouslySetInnerHTML={{ __html: t("trust.lede") }} />
            </div>
            <div className="scores">
              <div className="score"><b>{s ? `${s.security.passed}/${s.security.total}` : "25/25"}</b><span>{t("trust.sec")}</span></div>
              <div className="score"><b>{s ? `${s.agent.passed}/${s.agent.total}` : "5/5"}</b><span>{t("trust.agent")}</span></div>
              <div className="score"><b>{s ? `${s.model.brier_model.toFixed(3)} vs ${s.model.brier_baseline.toFixed(3)}` : "0.091 vs 0.146"}</b><span>{t("trust.model")}</span></div>
            </div>
            <div className="claims">
              <div><h3>{t("cl.works")}</h3><p>{t("cl.works.d")}</p></div>
              <div><h3>{t("cl.mock")}</h3><p>{t("cl.mock.d")}</p></div>
              <div><h3>{t("cl.not")}</h3><p>{t("cl.not.d")}</p></div>
            </div>
          </div>
        </section>
      </main>

      <footer className="wrap foot">
        <span className="logo small">CashBridge</span>
        <span>{t("foot")}</span>
        <a href="/docs">{t("foot.api")}</a>
      </footer>

      <SignInDialog open={authOpen} portal={portal} onPortal={setPortal} onClose={() => setAuthOpen(false)} />
      {signedOut && (
        <div role="status" style={{ position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)", zIndex: 90, background: "var(--ink)", color: "var(--paper)", padding: "10px 16px", borderRadius: 10, maxWidth: "calc(100% - 32px)" }}>
          {t("auth.signedOut")}
        </div>
      )}
    </>
  );
}

function PortalCard({ kind, can, cannot, action }: { kind: "sme" | "bank"; can: string[]; cannot: string[]; action: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <article className={"portal " + kind}>
      <h3>{t(`p.${kind}.t`)}</h3>
      <p className="portal-who">{t(`p.${kind}.who`)}</p>
      <ul className="can">{can.map((k) => <li key={k}>{t(k)}</li>)}</ul>
      <ul className="cannot">{cannot.map((k) => <li key={k}>{t(k)}</li>)}</ul>
      {action}
    </article>
  );
}
