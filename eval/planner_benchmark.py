"""Planner benchmark: fixed workflow vs planner with memory vs planner that learned from outcomes.

    python eval/planner_benchmark.py      (or: make bench)

Everything is SIMULATED and says so. The question is narrow: when the world differs from what the
models were fitted on, does a planner that (a) scores plans on many paths and (b) learns from recorded
outcomes keep the SME's cash positive more often, at what financing cost, without breaking a rule?

Protocol
  * Training outcomes: 8 past quarters, each a perturbed copy of the demo portfolio, planned by the
    Core with the prior world model and realised in a HIDDEN TEST WORLD (Oakline pays later than its
    history suggests; orders slip more than their stated confidence). The learner fits on these and the
    leave-one-episode-out gate decides whether the update is accepted.
  * Test cases: 40 new perturbed quarters, never seen in training (different seed).
  * Three planners choose a plan for each test case:
      A. fixed workflow    - the original Autopilot rule: factor the largest eligible invoice in the
                              first base-case negative week;
      B. planner + memory  - the Intelligence Core with the prior world model (memory is retrieved and
                              shown, parameters unchanged);
      C. planner + learning - the same Core with the world model learned from the training outcomes.
  * Every chosen plan is re-checked by the independent policy validator, then evaluated on 1,000 paths
    of the hidden test world (a different seed from the one the planners used).

Metrics: share of paths with no negative week (goal success), share of cases where that reaches the
goal threshold, expected financing cost, policy violations, overconfidence (predicted minus realised
success) and stability (does the realised success move by more than 5 points when the inputs are
perturbed by 3% and the planner re-plans knowing the plan in force?).

Writes data/execution_evidence/planner_benchmark.json and planner_benchmark.md.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from agents import intelligence_core as ic  # noqa: E402
from config.settings import EXECUTION_EVIDENCE_DIR  # noqa: E402
from core import scenario_simulator as sim  # noqa: E402
from scripts.run_demo_story import StoryClock  # noqa: E402
from ui.backend_real import RealBackend  # noqa: E402

OUT_JSON = EXECUTION_EVIDENCE_DIR / "planner_benchmark.json"
OUT_MD = EXECUTION_EVIDENCE_DIR / "planner_benchmark.md"
PLANNERS = ("fixed_workflow", "planner_memory", "planner_learning")
LABELS = {"fixed_workflow": "A. Fixed workflow", "planner_memory": "B. Planner + memory", "planner_learning": "C. Planner + learning"}


def _shape(actions):
    """A plan's structure: which levers, invoices and weeks (amounts move with the inputs)."""
    return sorted((a["type"], a.get("ref"), int(a.get("week", 0)), a.get("new_pct")) for a in actions)


def _bins(r: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reliability table: predicted success band vs realised success in the hidden world."""
    out = []
    for lo, hi in ((0.0, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 1.01)):
        xs = [x for x in r if lo <= x["predicted_success"] < hi]
        if xs:
            out.append({"band": f"{lo:.0%}-{min(hi, 1):.0%}", "cases": len(xs),
                        "predicted": round(float(np.mean([x["predicted_success"] for x in xs])), 4),
                        "realised": round(float(np.mean([x["realised_success"] for x in xs])), 4)})
    return out


def base_inputs() -> ic.CoreInputs:
    with tempfile.TemporaryDirectory() as tmp:
        backend = RealBackend(runtime_dir=Path(tmp), clock=StoryClock())
        return ic.CoreInputs.from_coordinator(backend.coord)


def run(test_cases: int = 40, train_episodes: int = 8, plan_paths: int = 1000, eval_paths: int = 1000) -> Dict[str, Any]:
    base = base_inputs()
    truth = ic.HIDDEN_TEST_WORLD
    prior = sim.WorldParams()
    prior_core = ic.IntelligenceCore(params=prior, n_paths=plan_paths)

    with tempfile.TemporaryDirectory() as tmp:
        memory = ic.CaseMemory(Path(tmp) / "memory.jsonl")
        observed = ic.seed_memory(memory, base, prior_core, episodes=train_episodes, seed=7, truth=truth)
        learner = ic.WorldModelLearner(prior)
        gate = learner.evaluate(observed, prior)
        learned = learner.fit(observed) if gate["accepted"] else prior
        learned_core = ic.IntelligenceCore(params=learned, n_paths=plan_paths)

        rng = np.random.default_rng(99)
        rows: List[Dict[str, Any]] = []
        for k in range(test_cases):
            case = ic.perturb_core_inputs(base, rng)
            nudged = ic.perturb_core_inputs(case, np.random.default_rng(1000 + k), noise=0.03)
            truth_paths = sim.sample(case.forecast_inputs, truth, n=eval_paths, seed=50_000 + k)
            nudged_truth = sim.sample(nudged.forecast_inputs, truth, n=eval_paths, seed=50_000 + k)
            need = sim.evaluate(sim.sample(case.forecast_inputs, prior, n=plan_paths))["shortfall_p95_usd"]
            row: Dict[str, Any] = {"case": k + 1}
            # Ceiling in the hidden world: free cash equal to the over-borrowing cap from week 1, never repaid.
            # No plan within the cap can do better, so it bounds what any financing planner could reach.
            truth_trough = sim.closings(truth_paths).min(axis=1)
            row["ceiling_within_cap"] = round(float(np.mean(truth_trough + ic.POLICY["over_borrowing_factor"] * max(need, 1.0) >= 0)), 4)
            for name in PLANNERS:
                if name == "fixed_workflow":
                    actions = ic.fixed_workflow_actions(case)
                    predicted = float(np.mean(sim.closings(sim.sample(case.forecast_inputs, prior, n=plan_paths), actions).min(axis=1) >= 0))
                    nudged_actions = ic.fixed_workflow_actions(nudged)
                    status = "RULE"
                else:
                    core = prior_core if name == "planner_memory" else learned_core
                    result = core.plan(case, memory=memory)
                    actions, predicted, status = result.chosen["actions"], result.chosen["p_goal"], result.status
                    # Re-planning knows the plan in force (as it would in use); it switches only for a real gain.
                    nudged_actions = core.plan(nudged, incumbent=actions).chosen["actions"]
                    # Ablation: the same re-plan without knowing the plan in force.
                    nudged_cold = core.plan(nudged).chosen["actions"]
                    # Calibration in the planner's own world (fresh scenarios): is the Monte Carlo honest when the
                    # model is right? Any remaining gap in the hidden world is then model error, not arithmetic.
                    own = sim.sample(case.forecast_inputs, core.params, n=eval_paths, seed=70_000 + k)
                    own_realised = float(np.mean(sim.closings(own, actions).min(axis=1) >= 0))
                    feas = result.feasibility
                violations = ic.validate_plan(actions, case, need)
                truth_closing = sim.closings(truth_paths, actions)
                realised = float(np.mean(truth_closing.min(axis=1) >= 0))
                cvar = sim.summarize(truth_paths, truth_closing)["shortfall_cvar95_usd"]
                realised_nudged = float(np.mean(sim.closings(nudged_truth, nudged_actions).min(axis=1) >= 0))
                row[name] = {"plan": ic.describe(actions), "status": status, "packs": ic.plan_packs(actions),
                             "predicted_success": round(predicted, 4), "realised_success": round(realised, 4),
                             "cost_usd": sim.expected_cost(truth_paths, actions), "cvar95_usd": cvar, "violations": violations,
                             "stable": abs(realised - realised_nudged) <= 0.05,
                             "same_plan": _shape(actions) == _shape(nudged_actions)}
                if name != "fixed_workflow":
                    row[name].update({"same_plan_without_incumbent": _shape(actions) == _shape(nudged_cold),
                                      "realised_in_own_world": round(own_realised, 4),
                                      "feasibility": {"verdict": feas["verdict"], "binding": [b["limit"] for b in feas["binding"]],
                                                      "cash_needed_week1_usd": feas["cash_needed_week1_usd"],
                                                      "over_borrowing_cap_usd": feas["over_borrowing_cap_usd"]}})
            rows.append(row)

    summary: Dict[str, Any] = {}
    for name in PLANNERS:
        r = [row[name] for row in rows]
        summary[name] = {
            "label": LABELS[name],
            "goal_success_mean": round(float(np.mean([x["realised_success"] for x in r])), 4),
            "cases_reaching_90pct": sum(1 for x in r if x["realised_success"] >= 0.90),
            "cases_reaching_80pct": sum(1 for x in r if x["realised_success"] >= 0.80),
            "expected_cost_mean_usd": round(float(np.mean([x["cost_usd"] for x in r])), 2),
            "shortfall_cvar95_mean_usd": round(float(np.mean([x["cvar95_usd"] for x in r])), 2),
            "packs_mean": round(float(np.mean([x["packs"] for x in r])), 2),
            "policy_violations": sum(len(x["violations"]) for x in r),
            "cases_with_violations": sum(1 for x in r if x["violations"]),
            "overconfidence_pp": round(float(np.mean([x["predicted_success"] - x["realised_success"] for x in r])) * 100, 1),
            "stability_pct": round(100 * sum(1 for x in r if x["stable"]) / len(r), 1),
            "same_plan_pct": round(100 * sum(1 for x in r if x["same_plan"]) / len(r), 1),
            "goal_not_reachable_cases": sum(1 for x in r if x["status"] == "GOAL_NOT_REACHABLE"),
        }
        if name != "fixed_workflow":
            summary[name].update({
                "same_plan_without_incumbent_pct": round(100 * sum(1 for x in r if x["same_plan_without_incumbent"]) / len(r), 1),
                "overconfidence_own_world_pp": round(float(np.mean([x["predicted_success"] - x["realised_in_own_world"] for x in r])) * 100, 1),
                "calibration_bins": _bins(r),
                "feasibility_verdicts": dict(sorted(Counter(x["feasibility"]["verdict"] for x in r).items())),
                "binding_limits": dict(sorted(Counter(b for x in r for b in x["feasibility"]["binding"]).items())),
            })
    ceilings = [row["ceiling_within_cap"] for row in rows]
    ceiling = {"mean": round(float(np.mean(ceilings)), 4), "cases_reaching_90pct": sum(1 for c in ceilings if c >= 0.90),
                          "cases_reaching_80pct": sum(1 for c in ceilings if c >= 0.80),
                          "rule": "hidden world, free cash = over-borrowing cap from week 1, never repaid: an upper bound for any plan within the cap"}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synthetic": True,
        "protocol": {"test_cases": test_cases, "train_episodes": train_episodes, "plan_paths": plan_paths, "eval_paths": eval_paths,
                     "hidden_test_world": truth.label, "goal": ic.GOALS["keep_cash_positive"]},
        "learning_gate": gate,
        "ceiling_within_cap": ceiling,
        "prior_world_model": {"version": prior.version, **prior.as_dict()},
        "learned_world_model": {"version": learned.version, **learned.as_dict()},
        "summary": summary,
        "cases": rows,
    }


def write(result: Dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    s, p = result["summary"], result["protocol"]
    lines = [
        "# Planner benchmark (SIMULATED)",
        "",
        f"Generated {result['generated_at']}. {p['test_cases']} held-out test quarters, {p['train_episodes']} training quarters, "
        f"plans evaluated on {p['eval_paths']} paths of the hidden test world: *{p['hidden_test_world']}*.",
        "",
        "This measures planners against a world model we wrote ourselves. It shows whether learning corrects a mis-specified "
        "model in simulation; it is not evidence about real SMEs.",
        "",
        "| Metric | " + " | ".join(s[n]["label"] for n in PLANNERS) + " |",
        "|---|" + "---|" * len(PLANNERS),
    ]
    metrics = [
        ("Paths with no negative week (mean)", lambda x: f"{x['goal_success_mean']:.1%}"),
        ("Cases reaching 90%", lambda x: f"{x['cases_reaching_90pct']} / {p['test_cases']}"),
        ("Cases reaching 80%", lambda x: f"{x['cases_reaching_80pct']} / {p['test_cases']}"),
        ("Expected financing cost (mean)", lambda x: f"USD {x['expected_cost_mean_usd']:,.0f}"),
        ("Shortfall in worst 5% of paths, CVaR 95% (mean)", lambda x: f"USD {x['shortfall_cvar95_mean_usd']:,.0f}"),
        ("Packs to approve (mean)", lambda x: f"{x['packs_mean']:.1f}"),
        ("Policy violations", lambda x: str(x["policy_violations"])),
        ("Overconfidence (predicted - realised)", lambda x: f"{x['overconfidence_pp']:+.1f} pp"),
        ("Same plan after 3% input noise (re-plan)", lambda x: f"{x['same_plan_pct']:.0f}%"),
        ("Outcome within 5 points after 3% noise", lambda x: f"{x['stability_pct']:.0f}%"),
        ("Planner said goal not reachable", lambda x: str(x["goal_not_reachable_cases"])),
    ]
    for label, fmt in metrics:
        lines.append(f"| {label} | " + " | ".join(fmt(s[n]) for n in PLANNERS) + " |")
    for label, key, fmt in (("Same plan after 3% noise, re-plan WITHOUT the plan in force (ablation)", "same_plan_without_incumbent_pct", lambda v: f"{v:.0f}%"),
                            ("Overconfidence in the planner's own world (calibration check)", "overconfidence_own_world_pp", lambda v: f"{v:+.1f} pp")):
        lines.append(f"| {label} | " + " | ".join(fmt(s[n][key]) if key in s[n] else "n/a" for n in PLANNERS) + " |")
    c = result["ceiling_within_cap"]
    lines += ["", "## Why no planner reaches 90%: feasibility", "",
              f"Upper bound for ANY plan inside the over-borrowing cap, in the hidden world: free cash equal to the cap from week 1, never repaid. "
              f"Mean {c['mean']:.1%}; cases where even this bound reaches 90%: **{c['cases_reaching_90pct']} / {p['test_cases']}**, 80%: {c['cases_reaching_80pct']} / {p['test_cases']}.", ""]
    for n in PLANNERS[1:]:
        lines.append(f"- {s[n]['label']}: certificate verdicts {s[n]['feasibility_verdicts']}; binding limits {s[n]['binding_limits']} "
                     "(computed in the planner's own world model, one limit relaxed at a time; diagnostics, not plans).")
    lines += ["", "Calibration (predicted success band vs realised in the hidden world):", "",
              "| Planner | Band | Cases | Predicted | Realised |", "|---|---|---|---|---|"]
    for n in PLANNERS[1:]:
        for b in s[n]["calibration_bins"]:
            lines.append(f"| {s[n]['label']} | {b['band']} | {b['cases']} | {b['predicted']:.1%} | {b['realised']:.1%} |")
    g = result["learning_gate"]
    lw = result["learned_world_model"]
    lines += [
        "",
        "## Learning gate",
        "",
        f"Leave-one-episode-out on {g.get('episodes')} quarters ({g.get('observations')} observations): mean log-likelihood "
        f"{g.get('loglik_current')} (prior) vs {g.get('loglik_candidate')} (candidate), gain {g.get('gain_per_observation')} per observation, "
        f"better on {g.get('held_out_wins')} of {g.get('episodes')} held-out quarters. Accepted: **{g['accepted']}**.",
        "",
        f"Learned corrections: buyer logit shifts {lw['buyer_logit_shift']}, order shipment scale {lw['ship_scale']} "
        f"(hidden truth: B-US-01 -1.2, B-US-02 -0.4, scale 0.8; shrinkage pulls estimates toward zero).",
        "",
        "## How to read it",
        "",
        "* A plan sized for the expected path (A) is cheap and fails often when buyers are slower than the model thinks.",
        "* B plans for bad paths, so it succeeds more often and costs more; it still trusts the prior model and is overconfident.",
        "* C keeps the same rules and plan space; only the world model changed, after an offline gate. Lower overconfidence is the main point: "
        "the planner's stated probability is closer to what happens.",
        "* All planners' plans pass the same independent policy validator; the learner cannot change limits.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    result = run()
    write(result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
