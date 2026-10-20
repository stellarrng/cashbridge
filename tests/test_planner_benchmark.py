"""The planner benchmark is reproducible and its committed numbers match its own protocol."""

import json

from config.settings import EXECUTION_EVIDENCE_DIR
from eval import planner_benchmark as pb


def test_small_benchmark_is_deterministic_and_rule_abiding():
    kwargs = dict(test_cases=3, train_episodes=4, plan_paths=200, eval_paths=200)
    a, b = pb.run(**kwargs), pb.run(**kwargs)
    assert a["summary"] == b["summary"] and a["cases"] == b["cases"]
    for name in ("planner_memory", "planner_learning"):
        assert a["summary"][name]["policy_violations"] == 0
    assert all(0 <= r[n]["realised_success"] <= 1 for r in a["cases"] for n in pb.PLANNERS)


def test_committed_benchmark_is_consistent():
    data = json.loads((EXECUTION_EVIDENCE_DIR / "planner_benchmark.json").read_text())
    assert data["synthetic"] is True and len(data["cases"]) == data["protocol"]["test_cases"]
    for name, s in data["summary"].items():
        realised = [c[name]["realised_success"] for c in data["cases"]]
        assert abs(sum(realised) / len(realised) - s["goal_success_mean"]) < 1e-3
    assert data["summary"]["planner_memory"]["policy_violations"] == 0
    assert data["summary"]["planner_learning"]["policy_violations"] == 0


def test_feasibility_ceiling_bounds_every_planner_and_calibration_is_reported():
    data = json.loads((EXECUTION_EVIDENCE_DIR / "planner_benchmark.json").read_text())
    for c in data["cases"]:
        # Free cash up to the cap, never repaid, is an upper bound for any plan inside the cap (small MC slack).
        assert c["planner_learning"]["realised_success"] <= c["ceiling_within_cap"] + 0.02
    for name in ("planner_memory", "planner_learning"):
        s = data["summary"][name]
        assert sum(b["cases"] for b in s["calibration_bins"]) == data["protocol"]["test_cases"]
        assert abs(s["overconfidence_own_world_pp"]) < 3.0  # Monte Carlo honest when its own model is right
