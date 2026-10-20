"""Audit 2: buyer-payment model is explainable, calibrated per group, domain-aware; green finance never over-claims."""

import json

import pytest

from agents.buyer_risk_agent import MODEL_FEATURES, BuyerRiskAgent
from data import loader


@pytest.fixture(scope="module")
def agent():
    return BuyerRiskAgent(loader.read("payment_history.json")["records"])


def test_no_personal_or_protected_attributes_in_the_model(agent):
    banned = ("age", "gender", "sex", "ethnic", "religion", "nationality", "name", "address", "phone", "email", "owner", "director")
    names = list(agent.model.coefficients) + list(MODEL_FEATURES)
    assert not [n for n in names if any(b in n.lower() for b in banned)]


@pytest.mark.parametrize("buyer", ["B-US-01", "B-CN-01", "B-JP-01"])
def test_explanation_adds_up_exactly(agent, buyer):
    e = agent.explain(buyer, 60, agent.medians[buyer])
    assert e["log_odds"] == pytest.approx(e["intercept"] + sum(c["contribution_log_odds"] for c in e["contributions"]), abs=5e-4)
    import math
    p = 1 / (1 + math.exp(-e["log_odds"]))
    assert e["p_before_band"] == pytest.approx(p, abs=1e-3)
    assert e["p_on_time"] == round(min(0.98, max(0.02, p)), 2)
    assert e["not_a_credit_decision"] is True and e["uses_personal_or_protected_attributes"] is False


def test_out_of_domain_inputs_are_flagged_not_silently_scored(agent):
    lo, hi = agent.domain()["terms_days"]
    assert agent.explain("B-US-01", 60, agent.medians["B-US-01"])["out_of_domain"] == []
    assert agent.explain("B-US-01", hi + 120, agent.medians["B-US-01"])["out_of_domain"]
    assert agent.explain("B-US-01", 60, agent.medians["B-US-01"] * 50)["out_of_domain"]
    new = agent.explain("B-NEW-99", 60, 20000)
    assert new["has_history"] is False and "portfolio average" in new["method"]


def test_walk_forward_calibration_holds_in_every_market_and_size_band():
    from eval.model_fairness import run
    r = run()
    for g in r["by_market"] + r["by_size"] + r["by_terms"]:
        assert g["within_interval"], g
    assert r["overall"]["brier_full"] < r["overall"]["brier_without_buyer_identity"]
    assert abs(r["new_buyer"]["p_on_time"] - r["new_buyer"]["portfolio_mean_of_known"]) <= 0.006
    assert r["protected_or_personal_attributes"] == []


def test_lender_sees_the_explanation(tmp_path):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    client.post("/api/autopilot/run", json={"execute": True})
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    pack = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()["snapshot"]["pack"]["pack_id"]
    exp = client.get(f"/api/bank/cases/{pack}").json()["buyer_risk_explanation"]
    assert exp["contributions"] and exp["not_a_credit_decision"] is True


# --------------------------------------------------------------------------- green finance claims
GREEN_FULL = {"project_id": "G-FULL", "name": "Solar", "activity_type": "rooftop_solar", "project_cost_usd": 100000,
              "requested_loan_usd": 80000, "baseline_kwh_year": 400000, "expected_generation_kwh_year": 200000,
              "illustrative_emission_factor_kg_per_kwh": 0.5,
              "evidence": {"equipment_quote": True, "site_assessment": True, "electricity_baseline": True, "generation_estimate": True}}


def test_complete_evidence_still_never_means_eligible_or_certified():
    from core.green_finance import assess_green_project
    r = assess_green_project(GREEN_FULL)
    assert r["documentation_completeness_pct"] == 100
    assert r["green_taxonomy_verified"] is False and r["impact_is_verified"] is False and r["bank_credit_approved"] is False
    assert r["status"] == "NEEDS_HUMAN_REVIEW"
    assert all(e["status"] == "provided_unverified" for e in r["evidence"])  # provided, never "verified"
    assert any("taxonomy" in i for i in r["issues"])


def test_green_outputs_and_ui_copy_contain_no_eligibility_or_certification_claims(tmp_path):
    import re
    from pathlib import Path
    from scripts.run_demo_story import StoryClock
    from ui.backend_real import RealBackend
    b = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    blobs = [json.dumps(b.green_finance_view()), json.dumps(b.green_cash_impact("GREEN-SOLAR-001", 3, 80, 36, 0.12, 1500)),
             json.dumps(b.green_economics("GREEN-EFF-002", 0.12, 1500))]
    web = Path(__file__).resolve().parents[1] / "frontend" / "src"
    for lang in ("en", "vi", "zh"):  # every interface string of the green screen, in all three languages
        table = json.loads((web / "shared" / "i18n" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        blobs += [v for k, v in table.items() if k.startswith("grn.")]
    blobs += [(web / "features" / "green-finance" / name).read_text(encoding="utf-8") for name in ("GreenFinanceScreen.tsx", "api.ts")]
    affirmative = re.compile(r"(is green[- ]certified|qualifies for (a )?green loan|eligible for (a )?green loan|ESG[- ]certified|"
                             r"đạt chứng nhận xanh|đủ điều kiện vay xanh|获得绿色认证|符合绿色贷款)", re.I)
    hits = [b_[:120] for b_ in blobs if affirmative.search(b_) and not re.search(r"\b(not|never|no|without|không|不|非)\b", b_, re.I)]
    assert hits == [], hits
