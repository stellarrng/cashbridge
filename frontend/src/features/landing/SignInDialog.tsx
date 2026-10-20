import { useEffect, useRef, useState, type FormEvent } from "react";
import { saveSession, type Portal } from "@/shared/api/session";
import { useI18n } from "@/shared/i18n";
import { Button } from "@/shared/ui";
import { demoLogin, fetchAuthConfig, passcodeLogin, type DemoAccount, type LoginResponse } from "../auth";

interface Props {
  open: boolean;
  portal: Portal;
  onPortal: (p: Portal) => void;
  onClose: () => void;
}

/** After signing in, open the workspace on the screen that suits the role. */
function enter(session: LoginResponse) {
  saveSession({ token: session.token, user: session.user, expires_at: session.expires_at });
  const home = session.user.portal === "bank" ? "inbox" : session.user.role === "sme_director" ? "core/decide" : "overview";
  window.location.href = "/app#" + home;
}

export function SignInDialog({ open, portal, onPortal, onClose }: Props) {
  const { t } = useI18n();
  const [accounts, setAccounts] = useState<DemoAccount[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const tabs = useRef<Record<Portal, HTMLButtonElement | null>>({ sme: null, bank: null });
  const lastFocus = useRef<Element | null>(null);

  // Load the demo accounts the first time the dialog opens.
  useEffect(() => {
    if (open && accounts === null) {
      fetchAuthConfig().then((c) => setAccounts(c.demo_accounts || [])).catch((e: Error) => setLoadError(e.message));
    }
  }, [open, accounts]);

  // Focus management: remember what opened the dialog, restore it on close, keep Tab inside.
  useEffect(() => {
    if (!open) return;
    lastFocus.current = document.activeElement;
    document.body.style.overflow = "hidden";
    tabs.current[portal]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      if (e.key !== "Tab" || !box.current) return;
      const items = [...box.current.querySelectorAll<HTMLElement>("button, input, [tabindex]:not([tabindex='-1'])")].filter((el) => !(el as HTMLButtonElement).disabled && el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      (lastFocus.current as HTMLElement | null)?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => setError(""), [portal]);

  const list = (accounts ?? []).filter((a) => a.portal === portal);

  async function quick(userId: string) {
    setError("");
    try {
      enter(await demoLogin(userId, portal));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      enter(await passcodeLogin(user.trim(), pass, portal));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth" role="dialog" aria-modal="true" aria-labelledby="authTitle" hidden={!open} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={"auth-box" + (portal === "bank" ? " bank" : "")} ref={box}>
        <aside className={"auth-side on-navy" + (portal === "bank" ? " bank" : "")}>
          <div className="seg tabs2" role="tablist" aria-label="Portal">
            {(["sme", "bank"] as const).map((p) => (
              <button key={p} type="button" role="tab" ref={(el) => { tabs.current[p] = el; }} aria-selected={portal === p} onClick={() => onPortal(p)}>
                {t(p === "sme" ? "auth.sme" : "auth.bank")}
              </button>
            ))}
          </div>
          <h2 id="authTitle">{t(`auth.${portal}.title`)}</h2>
          <p>{t(`auth.${portal}.lede`)}</p>
          <svg className="auth-art" viewBox="0 0 300 120" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
            <path d="M10 96h60V70M290 96h-60V70M70 70c40-58 120-58 160 0" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            <path d="M80 96v-14M110 96V62M150 96V52M190 96V62M220 96v-14" stroke="currentColor" strokeWidth="1.5" opacity=".5" />
          </svg>
        </aside>
        <div className="auth-main">
          <button className="close" type="button" onClick={onClose} aria-label="Close sign-in">×</button>
          <div className="auth-head">
            <h3>{t("auth.demo")}</h3>
            <p className="muted small-text">{t("auth.demo.d")}</p>
          </div>
          <div className="accounts">
            {loadError ? (
              <p className="err">{loadError}</p>
            ) : accounts === null ? (
              <p className="muted">{t("auth.loading")}</p>
            ) : accounts.length === 0 ? (
              <p className="muted">{t("auth.off")}</p>
            ) : list.length ? (
              list.map((a) => (
                <button key={a.user_id} type="button" className="acc" onClick={() => void quick(a.user_id)}>
                  <span className="av" aria-hidden="true">{a.initials}</span>
                  <span className="acc-text">
                    <b>{a.name}</b>
                    <span className="acc-sub"><span className="role-badge">{t("role." + a.role)}</span><span className="meta">{a.org}</span></span>
                  </span>
                </button>
              ))
            ) : (
              <p className="muted">Demo accounts are switched off on this server. Use the passcode form.</p>
            )}
          </div>
          <form className="login" autoComplete="on" onSubmit={submit}>
            <h3>{t("auth.form")}</h3>
            <label className="field">
              <span>{t("auth.user")}</span>
              <input name="username" autoComplete="username" required placeholder={portal === "sme" ? "sme.lan" : "bank.lihua"} value={user} onChange={(e) => setUser(e.target.value)} />
            </label>
            <label className="field">
              <span>{t("auth.pass")}</span>
              <input name="password" type="password" autoComplete="current-password" required value={pass} onChange={(e) => setPass(e.target.value)} />
            </label>
            <p className="err" role="alert">{error}</p>
            <Button variant={portal === "bank" ? "bank" : "bridge"} type="submit" disabled={busy}>{t("auth.submit")}</Button>
          </form>
        </div>
      </div>
    </div>
  );
}
