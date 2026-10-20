"""T11: does using CVaR in the choice (not just reporting it) cut tail risk, and at what cost?

    python eval/risk_planner_benchmark.py [--cases 40]   # writes reports/risk_planner.{json,md}

Three planners on the same 40 perturbed SYNTHETIC quarters (seed 99, as in planner_benchmark.py):
  A. Fixed rule: factor the nominated invoice at the first negative week (today's manual workflow).
  B. Cheapest: the Intelligence Core, lowest expected cost among plans reaching P(goal) >= 90%.
  C. Risk-aware: the same candidates and the same policy limits, objective = expected cost + 0.02 x CVaR95.

Plans are chosen on the planner's own Monte Carlo paths and then scored OUT OF SAMPLE on independent
paths from the hidden test world (different parameters and seeds), so a planner cannot win by
over-fitting its own scenarios. Paired differences B vs C carry a bootstrap 95% interval.
Policy limits (packs, over-borrowing cap, invoice eligibility) are identical for B and C and are
never relaxed; when the 90% goal is unreachable the feasibility verdict says which limit binds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from agents import intelligence_core as ic  # noqa: E402
from core import scenario_simulator as sim  # noqa: E402
from eval.planner_benchmark import base_inputs  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
PLANNERS = {"fixed_rule": "A. Fixed rule (manual workflow)", "cheapest": "B. Cheapest plan meeting the goal",
            "risk_aware": "C. Risk-aware (cost + 0.02 x CVaR95)", "robust": "D. Robust (worst case over an ambiguity set)"}


def _score(paths: sim.Paths, actions: List[Dict[str, Any]], case: ic.CoreInputs, need: float) -> Dict[str, Any]:
    closing = sim.closings(paths, actions)
    summ = sim.summarize(paths, closing)
    cost = sim.expected_cost(paths, actions)
    return {"p_goal": round(float((closing.min(axis=1) >= 0).mean()), 4), "p_shortfall": round(1 - summ["p_no_negative_week"], 4),
            "cvar95_usd": summ["shortfall_cvar95_usd"], "expected_shortfall_usd": summ["expected_shortfall_usd"],
            "cost_usd": cost, "risk_adjusted_cost_usd": round(cost + ic.CVAR_WEIGHT * summ["shortfall_cvar95_usd"], 2),
            "packs": ic.plan_packs(actions), "plan": ic.describe(actions), "violations": len(ic.validate_plan(actions, case, need))}


def _boot(diffs: List[float], seed: int = 5, n: int = 4000) -> List[float]:
    arr = np.array(diffs)
    rng = np.random.default_rng(seed)
    means = arr[rng.integers(0, len(arr), size=(n, len(arr)))].mean(axis=1)
    return [round(float(np.quantile(means, 0.025)), 2), round(float(np.quantile(means, 0.975)), 2)]


def run(cases: int = 40, plan_paths: int = 800, eval_paths: int = 1500) -> Dict[str, Any]:
    base = base_inputs()
    core = ic.IntelligenceCore(params=sim.WorldParams(), n_paths=plan_paths)
    truth = ic.HIDDEN_TEST_WORLD
    rng = np.random.default_rng(99)
    rows = []
    for k in range(cases):
        case = ic.perturb_core_inputs(base, rng)
        need = sim.evaluate(sim.sample(case.forecast_inputs, sim.WorldParams(), n=plan_paths))["shortfall_p95_usd"]
        eval_paths_k = sim.sample(case.forecast_inputs, truth, n=eval_paths, seed=90_000 + k)  # never seen by any planner
        cheap = core.plan(case, objective="cheapest")
        risky = core.plan(case, objective="risk_adjusted")
        robust = core.plan(case, objective="robust")
        row = {"case": k + 1, "fixed_rule": _score(eval_paths_k, ic.fixed_workflow_actions(case), case, need),
               "cheapest": _score(eval_paths_k, cheap.chosen["actions"], case, need),
               "risk_aware": _score(eval_paths_k, risky.chosen["actions"], case, need),
               "robust": _score(eval_paths_k, robust.chosen["actions"], case, need)}
        row["robust"].update(status=robust.status, feasibility=robust.feasibility["verdict"],
                             same_plan_as_risk_aware=robust.chosen["plan_id"] == risky.chosen["plan_id"])
        row["cheapest"].update(status=cheap.status, feasibility=cheap.feasibility["verdict"])
        row["risk_aware"].update(status=risky.status, feasibility=risky.feasibility["verdict"],
                                 same_plan_as_cheapest=cheap.chosen["plan_id"] == risky.chosen["plan_id"])
        rows.append(row)
    summary: Dict[str, Any] = {}
    for name in PLANNERS:
        xs = [r[name] for r in rows]
        summary[name] = {"label": PLANNERS[name], **{m: round(float(np.mean([x[m] for x in xs])), 4 if m.startswith("p_") else 2)
                         for m in ("p_goal", "p_shortfall", "cvar95_usd", "expected_shortfall_usd", "cost_usd", "risk_adjusted_cost_usd", "packs")},
                         "policy_violations": sum(x["violations"] for x in xs)}
    for name in ("cheapest", "risk_aware", "robust"):
        summary[name]["goal_not_reachable_cases"] = sum(1 for r in rows if r[name]["status"] == "GOAL_NOT_REACHABLE")
    d_cvar = [r["risk_aware"]["cvar95_usd"] - r["cheapest"]["cvar95_usd"] for r in rows]
    d_cost = [r["risk_aware"]["cost_usd"] - r["cheapest"]["cost_usd"] for r in rows]
    d_p = [r["risk_aware"]["p_goal"] - r["cheapest"]["p_goal"] for r in rows]
    paired = {"cases_with_different_plan": sum(1 for r in rows if not r["risk_aware"]["same_plan_as_cheapest"]),
              "cvar95_change_usd": {"mean": round(float(np.mean(d_cvar)), 2), "ci95": _boot(d_cvar)},
              "expected_cost_change_usd": {"mean": round(float(np.mean(d_cost)), 2), "ci95": _boot(d_cost)},
              "p_goal_change": {"mean": round(float(np.mean(d_p)), 4), "ci95": _boot(d_p)}}
    d_cv = [r["robust"]["cvar95_usd"] - r["risk_aware"]["cvar95_usd"] for r in rows]
    d_co = [r["robust"]["cost_usd"] - r["risk_aware"]["cost_usd"] for r in rows]
    d_pg = [r["robust"]["p_goal"] - r["risk_aware"]["p_goal"] for r in rows]
    paired_robust = {"cases_with_different_plan": sum(1 for r in rows if not r["robust"]["same_plan_as_risk_aware"]),
                     "cvar95_change_usd": {"mean": round(float(np.mean(d_cv)), 2), "ci95": _boot(d_cv)},
                     "expected_cost_change_usd": {"mean": round(float(np.mean(d_co)), 2), "ci95": _boot(d_co)},
                     "p_goal_change": {"mean": round(float(np.mean(d_pg)), 4), "ci95": _boot(d_pg)}}
    return {"synthetic": True, "paired_robust_vs_risk_aware": paired_robust, "protocol": {"cases": cases, "case_seed": 99, "plan_paths": plan_paths, "eval_paths": eval_paths,
            "eval_world": "hidden test world, seeds 90000+k (out of sample)", "cvar_weight": ic.CVAR_WEIGHT,
            "goal": "every week >= 0 with P >= 90%"}, "summary": summary, "paired_risk_vs_cheapest": paired, "cases": rows}


def write(result: Dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "risk_planner.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    s, pr, pc = result["summary"], result["paired_risk_vs_cheapest"], result["protocol"]
    lines = ["# Risk-aware financing planner (T11)", "",
             f"`python eval/risk_planner_benchmark.py --cases {pc['cases']}`. {pc['cases']} SYNTHETIC quarters, plans chosen on "
             f"{pc['plan_paths']} planner paths, scored out of sample on {pc['eval_paths']} hidden-world paths. Lower is better for every "
             "column except P(goal).", "",
             "| Planner | P(goal) | P(any negative week) | CVaR95 shortfall | Expected cost | Cost + 0.02 x CVaR | Packs | Policy violations |",
             "|---|---|---|---|---|---|---|---|"]
    for name in PLANNERS:
        x = s[name]
        lines.append(f"| {x['label']} | {x['p_goal']:.1%} | {x['p_shortfall']:.1%} | ${x['cvar95_usd']:,.0f} | ${x['cost_usd']:,.0f} | "
                     f"${x['risk_adjusted_cost_usd']:,.0f} | {x['packs']:.2f} | {x['policy_violations']} |")
    cv, co, pg = pr["cvar95_change_usd"], pr["expected_cost_change_usd"], pr["p_goal_change"]
    lines += ["", "## Paired: risk-aware minus cheapest (bootstrap 95% interval)", "",
              f"- Different plan chosen in **{pr['cases_with_different_plan']} of {pc['cases']}** cases.",
              f"- CVaR95 shortfall: **{cv['mean']:+,.0f} USD** ({cv['ci95'][0]:+,.0f} to {cv['ci95'][1]:+,.0f}).",
              f"- Expected financing cost: **{co['mean']:+,.0f} USD** ({co['ci95'][0]:+,.0f} to {co['ci95'][1]:+,.0f}).",
              f"- P(goal): **{pg['mean']:+.1%}** ({pg['ci95'][0]:+.1%} to {pg['ci95'][1]:+.1%}).", "",
              f"Goal (90%) not reachable within policy: cheapest {s['cheapest']['goal_not_reachable_cases']} cases, risk-aware "
              f"{s['risk_aware']['goal_not_reachable_cases']} cases. In those cases the planner reports the binding limit (feasibility verdict) "
              "and does not relax the policy.", "",
              "## Robust planner vs risk-aware (paired, bootstrap 95% interval)", "",
              f"- Different plan in **{result['paired_robust_vs_risk_aware']['cases_with_different_plan']} of {pc['cases']}** cases.",
              f"- P(goal) in the hidden world: **{result['paired_robust_vs_risk_aware']['p_goal_change']['mean']:+.1%}** "
              f"({result['paired_robust_vs_risk_aware']['p_goal_change']['ci95'][0]:+.1%} to {result['paired_robust_vs_risk_aware']['p_goal_change']['ci95'][1]:+.1%}).",
              f"- CVaR95: **{result['paired_robust_vs_risk_aware']['cvar95_change_usd']['mean']:+,.0f} USD**; expected cost: "
              f"**{result['paired_robust_vs_risk_aware']['expected_cost_change_usd']['mean']:+,.0f} USD**.",
              "- The ambiguity set is fixed policy (any buyer's on-time odds halve; all buyers a third worse; orders ship at 85%), "
              "not fitted to the hidden world.", "",
              "## Reading this honestly", "",
              "- The CVaR weight is a fixed policy value (5% tail x 40% emergency-funding cost), not tuned on these cases.",
              "- All quarters, buyer behaviour and the hidden world are simulated; this shows the trade-off mechanism, not real-world savings."]
    path = REPORT_DIR / "risk_planner.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=40)
    args = parser.parse_args(argv)
    result = run(args.cases)
    print(write(result))
    print(json.dumps({"summary": result["summary"], "paired": result["paired_risk_vs_cheapest"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
