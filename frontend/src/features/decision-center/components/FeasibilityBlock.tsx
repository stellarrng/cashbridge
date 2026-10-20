import { useI18n } from "@/shared/i18n";
import { pp, usd } from "@/shared/lib/format";
import { Note, Scroll } from "@/shared/ui";
import type { IntelligencePlan } from "../types";

/** Which limit stops the goal. Shown only when the goal is not reachable under the current rules. */
export function FeasibilityBlock({ plan }: { plan: IntelligencePlan }) {
  const { t } = useI18n();
  const f = plan.feasibility;
  if (!f || f.verdict === "REACHABLE") return null;
  return (
    <>
      <h4 className="mini">{t("tr2.feas", { g: pp(f.goal_probability) })}</h4>
      <p className="small">
        {t("tr2.feas.v." + f.verdict, { n: usd(f.cash_needed_week1_usd), c: usd(f.over_borrowing_cap_usd), e: usd(f.eligible_sources_usd) })}
      </p>
      <ul className="list small">{f.binding.map((b, i) => <li key={i}>{b.text}</li>)}</ul>
      <Scroll>
        <table className="small">
          <thead><tr><th>{t("tr2.feas.probe")}</th><th>{t("tr2.feas.p")}</th></tr></thead>
          <tbody>
            <tr><td>{t("tr2.feas.now")}</td><td><b>{pp(f.best_allowed_p_goal)}</b></td></tr>
            {f.probes.map((p) => (
              <tr key={p.id}>
                <td>{p.change}<div className="muted">{p.limit}</div></td>
                <td>{pp(p.p_goal)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Scroll>
      <Note>{t("tr2.feas.note")}</Note>
      <h4 className="mini">{t("tr2.feas.out")}</h4>
      <ul className="list small">{f.outside_financing.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </>
  );
}
