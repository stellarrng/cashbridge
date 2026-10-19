"""No green label or bank credit approval is inferred from provided evidence."""
import pytest
from core.green_finance import assess_green_project

BASE = {
    "project_id": "DEMO", "activity_type": "rooftop_solar",
    "project_cost_usd": 200000, "requested_loan_usd": 150000,
    "expected_generation_kwh_year": 200000,
    "illustrative_emission_factor_kg_per_kwh": 0.5,
    "evidence": {"equipment_quote": True, "site_assessment": True},
}

def test_green_screen_requires_human():
    result = assess_green_project(BASE)
    assert result["documentation_completeness_pct"] == 50
    assert result["illustrative_annual_impact_tco2e"] == 100.0
    assert result["status"] == "NEEDS_HUMAN_REVIEW"
    assert result["green_taxonomy_verified"] is False
    assert result["bank_credit_approved"] is False
    assert not result["impact_is_verified"]

def test_invalid_loan_is_incomplete():
    result = assess_green_project({**BASE, "requested_loan_usd": 250000})
    assert result["status"] == "INCOMPLETE"

def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        assess_green_project({**BASE, "illustrative_emission_factor_kg_per_kwh": "NaN"})
    with pytest.raises(ValueError):
        assess_green_project({**BASE, "activity_type": "fossil_fuel"})


def test_synthetic_projects_screen_without_green_certification():
    import json
    from config.settings import SANDBOX_INPUTS_DIR
    projects = json.loads((SANDBOX_INPUTS_DIR / "green_projects.json").read_text())
    results = [assess_green_project(p) for p in projects]
    assert len(results) == 2
    assert all(r["green_taxonomy_verified"] is False for r in results)
    assert all(r["bank_credit_approved"] is False for r in results)
