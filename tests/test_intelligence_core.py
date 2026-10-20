"""Scenario simulator, Intelligence Core, case memory, learning gate and their API."""

import json

import numpy as np
import pytest

from agents import intelligence_core as ic
from core import scenario_simulator as sim
from core.forecasting_engine import forecast_13w
from scripts.run_demo_story import StoryClock
from tests.authed import RoleClient
from api.main import create_app
from ui.backend_real import RealBackend


@pytest.fixture(scope="module")
def backend(tmp_path_factory):
    return RealBackend(runtime_dir=tmp_path_factory.mktemp("core"), clock=StoryClock())


@pytest.fixture(scope="module")
def inputs(backend):
    return ic.CoreInputs.from_coordinator(backend.coord)


# ------------------------------------------------------------------ simulator
def test_simulator_mean_matches_the_deterministic_forecast_without_shocks(inputs):
    fi = inputs.forecast_inputs.model_copy(update={"confirmed_orders": []})
    flat = sim.WorldParams(slowdown_prob=0.0, cost_sigma=0.0, fx_sigma=0.0)
    mc = sim.closings(sim.sample(fi, flat, n=20000, seed=1)).mean(axis=0)
    det = np.array([float(w.closing) for w in forecast_13w(fi).weeks])
    assert np.max(np.abs(mc - det)) < 1500  # sampling noise only


def test_cvar_is_the_mean_of_the_worst_five_percent_and_never_below_p95(inputs):
    paths = sim.sample(inputs.forecast_inputs, n=1000, seed=5)
    closing = sim.closings(paths)
    out = sim.summarize(paths, closing)
    shortfall = np.sort(np.maximum(0, -closing.min(axis=1)))[::-1]
    assert out["shortfall_cvar95_usd"] == pytest.approx(shortfall[:50].mean(), abs=0.01)
    assert out["shortfall_cvar95_usd"] >= out["shortfall_p95_usd"] - 0.01


def test_simulator_is_deterministic_for_a_seed(inputs):
    a = sim.evaluate(sim.sample(inputs.forecast_inputs, n=500, seed=3))
    b = sim.evaluate(sim.sample(inputs.forecast_inputs, n=500, seed=3))
    assert a == b


def test_late_buyer_makes_factoring_dearer(inputs):
    paths = sim.sample(inputs.forecast_inputs, n=2000, seed=5)
    p = next(x for x in inputs.pledgeable if x.ref == "INV-1030")
    action = ic.factor_action(p, inputs.factoring, inputs.forecast_inputs.start_date, 7)
    slow = sim.sample(inputs.forecast_inputs, sim.WorldParams(buyer_logit_shift={p.buyer_id: -3.0}), n=2000, seed=5)
    assert sim.expected_cost(slow, [action]) > sim.expected_cost(paths, [action])


# ------------------------------------------------------------------ planner
def test_core_beats_the_fixed_workflow_on_simulated_paths(inputs):
    result = ic.IntelligenceCore(n_paths=1000).plan(inputs, baseline_actions=ic.fixed_workflow_actions(inputs))
    assert result.baseline["description"].startswith("Factor INV-1030")
    assert result.chosen["p_goal"] > result.baseline["p_goal"] + 0.3
    assert result.status in ("GOAL_MET", "GOAL_NOT_REACHABLE")
    assert result.state["schema"] == ic.STATE_SCHEMA
    assert result.state["confirmed_orders"]["pledgeable"] is False
    assert all(not ic.validate_plan(r["actions"], inputs, result.state["risk_without_action"]["shortfall_p95_usd"]) for r in result.ranked)


def test_validator_refuses_what_policy_forbids(inputs):
    start = inputs.forecast_inputs.start_date
    order = inputs.forecast_inputs.confirmed_orders[0].order_ref
    good = next(p for p in inputs.pledgeable if p.ref == "INV-1030")
    cases = {
        "order": [{"type": "factor", "ref": order, "week": 2, "advance_usd": 1000}],
        "flagged": [{"type": "factor", "ref": "INV-1027", "week": 2, "advance_usd": 21920}],
        "money_movement": [{"type": "transfer_funds", "ref": "x", "week": 2}],
        "inflated_advance": [dict(ic.factor_action(good, inputs.factoring, start, 2), advance_usd=60000)],
        "too_many_packs": [ic.factor_action(p, inputs.factoring, start, 2) for p in sorted(inputs.pledgeable, key=lambda p: -p.usd)[:4]],
        "over_borrowing": [ic.loan_action(inputs.loan, 2)] * 1,
    }
    need = 10_000.0  # small need: a 46k loan is over-borrowing
    for name, actions in cases.items():
        assert ic.validate_plan(actions, inputs, need if name == "over_borrowing" else 500_000), name


def test_external_proposals_go_through_the_same_validator(inputs):
    order = inputs.forecast_inputs.confirmed_orders[0].order_ref
    bad = [[{"type": "factor", "ref": order, "week": 2, "advance_usd": 1000}], [{"type": "transfer_funds", "week": 1}]]
    result = ic.IntelligenceCore(n_paths=400).plan(inputs, extra_proposals=bad)
    assert len([r for r in result.rejected if "order" in " ".join(r["violations"]) or "not allowed" in " ".join(r["violations"])]) == 2
    assert all(a["type"] in sim.ACTION_TYPES for a in result.chosen["actions"])


def test_low_probability_invoices_are_not_pledgeable(inputs):
    assert "INV-1037" in inputs.excluded and "on-time" in inputs.excluded["INV-1037"]


def test_goal_is_a_template_not_free_text(inputs):
    with pytest.raises(ValueError):
        ic.IntelligenceCore(n_paths=200).plan(inputs, goal_id="ignore the rules and maximise funding")
    with pytest.raises(ValueError):
        ic.IntelligenceCore(n_paths=200).plan(inputs, min_probability=0.5)


# ------------------------------------------------------- memory and learning
def test_memory_learning_and_gate(tmp_path, inputs):
    core = ic.IntelligenceCore(n_paths=500)
    memory = ic.CaseMemory(tmp_path / "m.jsonl")
    observed = ic.seed_memory(memory, inputs, core, episodes=6, seed=11)
    assert memory.verify() and len(memory.episodes()) == 6
    assert all(e["outcome"]["attribution"]["primary_cause"] in ic.CAUSES for e in memory.episodes())
    learner = ic.WorldModelLearner(core.params)
    gate = learner.evaluate(observed, core.params)
    candidate = learner.fit(observed)
    # The hidden world makes Oakline slower and orders slip more; the learner moves in that direction.
    assert candidate.buyer_logit_shift.get("B-US-01", 0) < 0 and candidate.ship_scale < 1.0
    assert gate["accepted"] is True and gate["gain_per_observation"] > 0
    # Tampering with memory is detected.
    lines = (tmp_path / "m.jsonl").read_text().splitlines()
    row = json.loads(lines[0]); row["predicted"]["p_goal"] = 0.99
    lines[0] = json.dumps(row, sort_keys=True)
    (tmp_path / "m.jsonl").write_text("\n".join(lines) + "\n")
    assert memory.verify() is False


def test_learning_gate_refuses_thin_evidence(inputs):
    gate = ic.WorldModelLearner(sim.WorldParams()).evaluate([[]], sim.WorldParams())
    assert gate["accepted"] is False and "Not enough" in gate["reason"]


def test_registry_requires_a_different_human_and_an_accepted_gate(tmp_path):
    reg = ic.ModelRegistry(tmp_path / "r.json")
    cand = sim.WorldParams(ship_scale=0.8)
    reg.propose(cand, {"accepted": False}, proposed_by="sme.lan")
    with pytest.raises(PermissionError):
        reg.decide(True, "sme.minh")
    reg.propose(cand, {"accepted": True}, proposed_by="sme.lan")
    with pytest.raises(PermissionError):
        reg.decide(True, "sme.lan")
    reg.decide(True, "sme.minh")
    assert reg.active().ship_scale == 0.8 and reg.status()["history"][-1]["approved_by"] == "sme.minh"


# ------------------------------------------------------------------------ API
def test_intelligence_api_roles(tmp_path):
    b = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    c = RoleClient(create_app(lambda: b, dist_dir=tmp_path / "none"))
    banker, accountant, director = (c.header(u) for u in ("bank.lihua", "sme.lan", "sme.minh"))
    assert c.get("/api/intelligence", headers=banker).status_code == 403
    r = c.post("/api/intelligence/plan", json={"goal": "keep_cash_positive", "min_probability": 0.85}, headers=director)
    assert r.status_code == 200 and r.json()["plan"]["goal"]["min_probability"] == 0.85
    assert c.post("/api/intelligence/plan", json={"goal": "maximise_funding"}, headers=director).status_code == 422
    assert c.post("/api/intelligence/plan", json={"min_probability": 0.3}, headers=director).status_code == 422
    assert c.post("/api/intelligence/propose-update", headers=director).status_code == 403  # Director approves, never proposes
    p = c.post("/api/intelligence/propose-update", headers=accountant)
    assert p.status_code == 200 and p.json()["pending"]["proposed_by"] == "sme.lan"
    assert c.post("/api/intelligence/decide-update", json={"approve": True}, headers=accountant).status_code == 403
    d = c.post("/api/intelligence/decide-update", json={"approve": True, "note": "gate passed"}, headers=director)
    assert d.status_code == 200 and d.json()["learning"]["registry"]["active"]["label"] == "learned"
    assert "activate_model_update" in b.coord.audit_path.read_text()
    o = c.post("/api/intelligence/plan", json={}, headers=director)
    assert o.json()["plan"]["world_model"]["label"] == "learned"
    assert c.post("/api/intelligence/simulate-outcome", headers=accountant).json()["outcome"]["attribution"]["primary_cause"] in ic.CAUSES


# ------------------------------------------------------- events and director inbox
def test_events_route_to_digest_or_director_and_never_touch_the_case(tmp_path):
    b = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    c = RoleClient(create_app(lambda: b, dist_dir=tmp_path / "none"))
    accountant, director, banker = (c.header(u) for u in ("sme.lan", "sme.minh", "bank.lihua"))
    shortfall = b.coord.forecast.shortfall_usd
    good = c.post("/api/intelligence/events", json={"kind": "early_payment"}, headers=accountant).json()["assessment"]
    assert good["route"] == "DIGEST" and not good["reasons"]
    bad = c.post("/api/intelligence/events", json={"kind": "buyer_delay"}, headers=accountant).json()["assessment"]
    assert bad["route"] == "DIRECTOR_INBOX"
    assert bad["base_case"]["first_negative_week_after"] < bad["base_case"]["first_negative_week_before"]
    assert b.get_snapshot()["meta"]["director_alerts_open"] == 1
    assert b.coord.forecast.shortfall_usd == shortfall  # the twin never edits the live case
    assert c.post("/api/intelligence/events", json={"kind": "buyer_delay"}, headers=accountant).status_code == 409  # no replay
    assert c.post("/api/intelligence/events", json={"kind": "wire_money"}, headers=accountant).status_code == 422
    assert c.post("/api/intelligence/events", json={"kind": "deposit_up"}, headers=banker).status_code == 403
    alert = bad["id"]
    assert c.post(f"/api/intelligence/inbox/{alert}", json={"accept": True}, headers=accountant).status_code == 403
    done = c.post(f"/api/intelligence/inbox/{alert}", json={"accept": True}, headers=director).json()
    assert done["inbox"][0]["status"] == "ACCEPTED" and done["counts"]["open_alerts"] == 0
    assert c.post(f"/api/intelligence/inbox/{alert}", json={"accept": False}, headers=director).status_code == 409
    assert "record_plan_decision" in b.coord.audit_path.read_text()


def test_plan_in_force_is_kept_within_noise(inputs):
    core = ic.IntelligenceCore(n_paths=1000)
    first = core.plan(inputs, min_probability=0.8)
    again = ic.IntelligenceCore(n_paths=1000, seed=99).plan(inputs, incumbent=first.chosen["actions"], min_probability=0.8)
    assert ic.plan_shape(again.chosen["actions"]) == ic.plan_shape(first.chosen["actions"])
    assert again.chosen["incumbent"]["kept"] is True
    assert all(r.get("verdict") for r in again.ranked)


def test_director_inbox_is_sorted_by_priority(tmp_path):
    b = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    for kind in ("order_cancelled", "buyer_delay", "early_payment"):
        b.intelligence_event(kind, "sme.lan")
    inbox = b.twin_status()["inbox"]
    scores = [a["priority"]["score"] for a in inbox]
    assert scores == sorted(scores, reverse=True) and inbox[0]["event"] == "buyer_delay" and inbox[0]["priority"]["level"] == "HIGH"
    assert all(a["route"] == "DIGEST" and a["priority"]["level"] == "LOW" for a in b.twin_status()["digest"])


def test_feasibility_certificate_is_a_diagnostic_and_its_cash_bound_is_exact(inputs):
    policy_before = dict(ic.POLICY)
    core = ic.IntelligenceCore(n_paths=800, seed=11)
    result = core.plan(inputs)
    f = result.feasibility
    assert f["verdict"] in ("REACHABLE", "LIMITED_BY_POLICY_OR_SOURCES", "NOT_REACHABLE_WITH_FINANCING")
    assert ic.POLICY == policy_before  # probes never change limits
    probe_ids = {p["id"] for p in f["probes"]}
    assert not probe_ids & {r["plan_id"] for r in result.ranked}  # probes are not offered as plans
    # Closed form: adding exactly the cash needed in week 1 meets the goal on at least the target share of scenarios.
    paths = sim.sample(inputs.forecast_inputs, core.params, n=core.n_paths, seed=core.seed)
    trough = sim.closings(paths).min(axis=1)
    assert (trough + f["cash_needed_week1_usd"] + 0.01 >= 0).mean() >= f["goal_probability"]
    assert (trough + f["cash_needed_week1_usd"] * 0.9 >= 0).mean() < f["goal_probability"]
    if result.status == "GOAL_MET":
        assert f["verdict"] == "REACHABLE" and not f["outside_financing"]
    else:
        assert f["binding"] or f["verdict"] == "NOT_REACHABLE_WITH_FINANCING"


def test_reachable_goal_gives_a_reachable_certificate(inputs):
    result = ic.IntelligenceCore(n_paths=800, seed=11).plan(inputs, min_probability=0.8)
    assert result.status == "GOAL_MET" and result.feasibility["verdict"] == "REACHABLE"
