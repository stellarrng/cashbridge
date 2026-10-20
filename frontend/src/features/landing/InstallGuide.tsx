import { useState, type ReactNode } from "react";
import { useI18n } from "@/shared/i18n";
import { QrCode } from "./QrCode";

type Os = "ios" | "android";

const ICON = "/brand/cashbridge-icon.svg";

/** The public address the QR code opens on a phone. A QR made from localhost would be useless off this computer. */
const SITE_URL = "https://cashbridge-6qp4.onrender.com/";

const SHARE = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3v12M8 7l4-4 4 4M6 11H5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-1" />
  </svg>
);
const DOTS = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="12" cy="5" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="12" cy="19" r="2" />
  </svg>
);
const PLUS = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <rect x="4" y="4" width="16" height="16" rx="3" /><path d="M12 8v8M8 12h8" />
  </svg>
);

/** Best guess of the visitor's phone, so the matching tab is open first. */
function guessOs(): Os {
  const ua = navigator.userAgent;
  const ipadOs = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return /iPhone|iPad|iPod/.test(ua) || ipadOs ? "ios" : "android";
}

/**
 * How to put CashBridge on a phone's home screen. Left: the steps. Right: a QR code that opens this site on the phone.
 * The "what to tap" chips are pictures of buttons on the phone, not buttons on this page.
 */
export function InstallGuide() {
  const { t } = useI18n();
  const [os, setOs] = useState<Os>(guessOs);
  const k = os === "ios" ? "i" : "a";
  const hint1: ReactNode = os === "ios" ? SHARE : DOTS;
  const steps: Array<{ title: string; text: string; hint: ReactNode }> = [
    { title: t(`inst.${k}1.t`), text: t(`inst.${k}1.d`), hint: <span className="hint-ico">{hint1}</span> },
    { title: t(`inst.${k}2.t`), text: t(`inst.${k}2.d`), hint: <><span className="hint-ico">{PLUS}</span>{t(`inst.${k}2.c`)}</> },
    { title: t(`inst.${k}3.t`), text: t(`inst.${k}3.d`), hint: <><img src={ICON} alt="" width="20" height="20" />{t(`inst.${k}3.c`)}</> },
  ];
  
  return (
    <section className="sec sec--paper" id="install">
      <div className="wrap">
        <div className="install-card reveal">
          <div className="install-main">
            <h2>{t("inst.title")}</h2>
            <div className="install-app">
              <img src={ICON} alt="" width="56" height="56" />
              <div>
                <b>CashBridge</b>
                <p>{t("inst.desc")}</p>
              </div>
            </div>
            <div className="seg install-tabs" role="tablist" aria-label={t("inst.title")}>
              {(["ios", "android"] as const).map((o) => (
                <button key={o} type="button" role="tab" aria-selected={os === o} onClick={() => setOs(o)}>
                  {t(o === "ios" ? "inst.ios" : "inst.android")}
                </button>
              ))}
            </div>
            <ol className="install-steps">
              {steps.map((s, i) => (
                <li key={os + i} className="step-card">
                  <span className="step-n" aria-hidden="true">{i + 1}</span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                  <span className="step-hint" aria-hidden="true">{s.hint}</span>
                </li>
              ))}
            </ol>
          </div>
          <aside className="install-qr">
            <QrCode text={SITE_URL} label={t("inst.scan")} />
            <p>{t("inst.scan")}</p>
            <span className="qr-url mono">{new URL(SITE_URL).host}</span>
          </aside>
        </div>
      </div>
    </section>
  );
}
