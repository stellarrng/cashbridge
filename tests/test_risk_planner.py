"""T11: the planner USES CVaR when choosing; the policy limits stay identical; API exposes the objective."""

import pytest

from agents import intelligence_core as ic
from eval import risk_planner_benchmark as rpb
from eval.planner_benchmark import base_inputs


def test_unknown_objective_is_refused():
    with pytest.raises(ValueError):
        ic.IntelligenceCore(n_paths=200).plan(base_inputs(), objective="yolo")


def test_risk_aware_choice_minimises_cost_plus_weighted_cvar_among_eligible_plans():
    core = ic.IntelligenceCore(n_paths=400)
    result = core.plan(base_inputs(), objective="risk_adjusted")
    chosen = result.chosen
    assert chosen["risk_adjusted_cost_usd"] == pytest.approx(chosen["cost_usd"] + ic.CVAR_WEIGHT * chosen["shortfall_cvar95_usd"], abs=0.02)
    if result.status == "GOAL_MET":
        eligible = [r for r in result.ranked if r["p_goal"] >= result.goal["min_probability"]]
        assert chosen["risk_adjusted_cost_usd"] <= min(r["risk_adjusted_cost_usd"] for r in eligible) + 0.01
    assert result.goal["objective"] == "risk_adjusted"
    assert not ic.validate_plan(chosen["actions"], base_inputs(), 1e9)


def test_small_out_of_sample_benchmark_never_worse_on_tail_and_never_breaks_policy():
    res = rpb.run(cases=6, plan_paths=300, eval_paths=500)
    s = res["summary"]
    assert s["risk_aware"]["policy_violations"] == 0 and s["cheapest"]["policy_violations"] == 0
    assert s["risk_aware"]["risk_adjusted_cost_usd"] <= s["cheapest"]["risk_adjusted_cost_usd"] + 1.0
    assert s["risk_aware"]["goal_not_reachable_cases"] == s["cheapest"]["goal_not_reachable_cases"]  # same limits, nothing relaxed


def test_api_accepts_objective_and_policy_reports_it(tmp_path):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    for objective in ("cheapest", "risk_adjusted"):
        r = client.post("/api/intelligence/plan", json={"objective": objective})
        assert r.status_code == 200 and r.json()["plan"]["goal"]["objective"] == objective
    assert client.post("/api/intelligence/plan", json={"objective": "max_profit"}).status_code == 422
    pol = client.get("/api/settings/policy").json()["planner"]
    assert pol["objective"] == "risk_adjusted" and pol["cvar_weight"] == 0.02


def test_robust_objective_chooses_on_the_worst_plausible_world():
    core = ic.IntelligenceCore(n_paths=300)
    r = core.plan(base_inputs(), objective="robust")
    ch = r.chosen
    assert ch["p_goal_worst_case"] <= ch["p_goal"]
    if r.status == "GOAL_MET":
        assert ch["p_goal_worst_case"] >= r.goal["min_probability"]
    worlds = ic.ambiguity_worlds(core.params, ["B-A", "B-B"])
    assert len(worlds) == 1 + 2 + 2 and worlds[0] is core.params
    assert all(w.label for w in worlds[1:]) and worlds[1].buyer_logit_shift["B-A"] == pytest.approx(ic.AMBIGUITY["single_buyer_logit"])


def test_stress_test_is_reported_for_the_chosen_plan(tmp_path):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    plan = client.post("/api/intelligence/plan", json={"objective": "robust"}).json()["plan"]
    stress = plan["chosen"]["stress_test"]
    assert stress[0]["world"] == "nominal" and len(stress) >= 4
    assert min(x["p_goal"] for x in stress) <= stress[0]["p_goal"]
