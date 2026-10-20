import type { ReactNode } from "react";
import { resetDemo, useSnapshotContext } from "@/entities/case";
import { getSession } from "@/shared/api/session";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n, type Lang } from "@/shared/i18n";
import { formatExpiry, usd } from "@/shared/lib/format";
import type { ScreenProps } from "@/shared/lib/screen";
import { usePreferences, type ThemeChoice } from "@/shared/preferences";
import { Button, Note, PageHead, Panel, Scroll, useToast } from "@/shared/ui";
import { RoleStrip, UserCard, useAuth } from "../auth";
import { fetchHealth, fetchPolicy } from "./api";

function Segmented<T extends string>({ label, options, current, onPick }: { label: string; options: ReadonlyArray<readonly [T, string]>; current: T; onPick: (v: T) => void }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" className={v === current ? "on" : ""} aria-pressed={v === current} onClick={() => onPick(v)}>{text}</button>
      ))}
    </div>
  );
}

function Row({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="set-row">
      <div><b>{title}</b>{hint ? <span>{hint}</span> : null}</div>
      {children}
    </div>
  );
}

function Switch({ checked, title, hint, onChange }: { checked: boolean; title: string; hint: string; onChange: (on: boolean) => void }) {
  return (
    <Row title={title} hint={hint}>
      <label className="switch">
        <input type="checkbox" checked={checked} aria-label={title} onChange={(e) => onChange(e.target.checked)} />
        <span></span>
      </label>
    </Row>
  );
}

/**
 * Personal display preferences live on this device only. Organisation policy is read from the server and shown
 * read-only: no permission, limit or approval rule is ever stored or decided in the browser.
 */
export default function SettingsScreen(_: ScreenProps) {
  const { t, lang, setLang } = useI18n();
  const { user, can, switchAccount, signOut } = useAuth();
  const prefs = usePreferences();
  const toast = useToast();
  const act = useAct();
  const { refresh } = useSnapshotContext();
  const policy = useAsync(fetchPolicy, []);
  const health = useAsync(fetchHealth, []);
  const pol = policy.data;
  const session = getSession();
  const saved = () => toast(t("set.saved"));

  return (
    <>
      <PageHead title={t("set.title")} lede={t("set.lede")} />
      <div className="grid2 settings-grid">
        <Panel title={t("set.display")} sub={t("set.personalSub")}>
          <Row title={t("set.lang")}>
            <Segmented<Lang> label={t("set.lang")} current={lang} onPick={(v) => { setLang(v); saved(); }} options={[["en", "English"], ["vi", "Tiếng Việt"], ["zh", "中文"]]} />
          </Row>
          <Row title={t("set.theme")}>
            <Segmented<ThemeChoice> label={t("set.theme")} current={prefs.theme} onPick={(v) => { prefs.setTheme(v); saved(); }} options={[["system", t("set.system")], ["light", t("set.light")], ["dark", t("set.dark")]]} />
          </Row>
          <Row title={t("set.view")} hint={t("set.viewHint")}>
            <Segmented label={t("set.view")} current={prefs.view} onPick={(v) => { prefs.setPref("view", v); saved(); }} options={[["advanced", t("set.advanced")], ["simple", t("set.simple")]]} />
          </Row>
          <Row title={t("set.text")}>
            <Segmented label={t("set.text")} current={prefs.text} onPick={(v) => { prefs.setPref("text", v); saved(); }} options={[["normal", t("set.normal")], ["large", t("set.large")]]} />
          </Row>
          <Switch checked={prefs.motion === "reduce"} title={t("set.motion")} hint={t("set.motionHint")} onChange={(on) => { prefs.setPref("motion", on ? "reduce" : "normal"); saved(); }} />
          <Switch checked={prefs.contrast === "high"} title={t("set.contrast")} hint={t("set.contrastHint")} onChange={(on) => { prefs.setPref("contrast", on ? "high" : "normal"); saved(); }} />
        </Panel>

        <Panel title={t("set.profile")} sub={t("set.profileSub")}>
          <div className="side-user big"><UserCard user={user} /></div>
          <Row title={t("set.orgName")}><span>{user.org || "–"}</span></Row>
          <Row title={t("set.uid")}><span className="mono">{user.user_id}</span></Row>
          {pol && <Row title={t("set.tenant")}><span className="mono">{pol.you.tenant}</span></Row>}
          <Note>{t("set.roleNote")}</Note>
          {user.portal === "sme" && <RoleStrip />}
        </Panel>

        <Panel title={t("set.sessionData")} sub={t("set.sessionSub")}>
          <Row title={t("set.server")}>
            <span className={"pill " + (health.data ? "ok" : "bad")}>{t(health.data ? "set.online" : "set.offline")}</span>
          </Row>
          {pol && <Row title={t("set.mode")}><span className="mono">{pol.mode}</span></Row>}
          {session?.expires_at && <Row title={t("set.expires")}><span>{formatExpiry(session.expires_at, lang)}</span></Row>}
          <div className="row mt-2">
            <Button small variant="ghost" onClick={() => void switchAccount()}>{t("app.switch")}</Button>
            <Button small variant="ghost" onClick={() => void signOut()}>{t("app.logout")}</Button>
            {can("demo:reset") && (
              <Button small variant="danger" onClick={async () => { if (window.confirm(t("tr.reset") + "?") && (await act(resetDemo, "OK"))) await refresh().catch(() => null); }}>{t("tr.reset")}</Button>
            )}
          </div>
        </Panel>

        <Panel title={t("set.org")} sub={t("set.orgSub")}>
          {pol ? (
            <>
              <Scroll>
                <table className="small">
                  <tbody>
                    <tr><td>{t("set.you")}</td><td>{t("role." + pol.you.role)}<div className="muted mono">{pol.you.permissions.join(", ")}</div></td></tr>
                    <tr><td>{t("set.buffer")}</td><td>{usd(pol.cash.buffer_usd)} · {t("set.conc")} {pol.cash.concentration_alert_pct}%</td></tr>
                    <tr>
                      <td>{t("set.approvals")}</td>
                      <td>OTP {pol.approvals.otp_validity_seconds}s · {t("set.session")} {pol.approvals.session_hours}h<div className="muted">{pol.approvals.segregation_of_duties}. {pol.approvals.lender_decision}.</div></td>
                    </tr>
                    <tr>
                      <td>{t("set.planner")}</td>
                      <td>{Object.values(pol.planner.goals).map((g) => `${g.label} (${Math.round(g.min_probability * 100)}%)`).join("; ")} · max {pol.planner.max_packs_per_plan} · ×{pol.planner.over_borrowing_factor}</td>
                    </tr>
                    <tr><td>{t("set.alerts")}</td><td>{pol.alerts}</td></tr>
                  </tbody>
                </table>
              </Scroll>
              <Note>{pol.change_process}</Note>
            </>
          ) : (
            <p className="muted">–</p>
          )}
        </Panel>
      </div>
    </>
  );
}
