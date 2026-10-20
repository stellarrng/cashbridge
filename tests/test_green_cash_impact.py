"""T18: green investment effect on the 13-week cash buffer; estimate, never certification."""

import pytest

from core.green_finance import green_cash_impact

PROJECT = {"project_id": "G1", "activity_type": "rooftop_solar", "project_cost_usd": 100000, "requested_loan_usd": 80000,
           "baseline_kwh_year": 400000, "expected_generation_kwh_year": 200000}


def test_cash_vs_loan_funding_arithmetic():
    weeks = [50000.0] * 13
    r = green_cash_impact(weeks, 10000, PROJECT, capex_week=2, financed_pct=80, loan_apr_pct=12, tenor_months=36,
                          electricity_price_usd_per_kwh=0.12, annual_opex_usd=0)
    cash, loan = r["cash_funded"], r["loan_funded"]
    assert cash["closing_by_week"][0] == 50000 and cash["closing_by_week"][1] == 50000 - 100000
    assert loan["closing_by_week"][1] == 50000 - 20000
    assert loan["monthly_instalment_usd"] == pytest.approx(2657.14, abs=0.05)  # 80k, 1%/month, 36 months
    saving = 200000 * 0.12 / 52
    # savings and instalments start in week 6 (capex week 2 + 4 commissioning weeks), so week 7 has two of each
    assert loan["closing_by_week"][6] == pytest.approx(30000 + 2 * (saving - 2657.14 * 12 / 52), abs=0.1)
    assert cash["extra_funding_to_hold_buffer_usd"] == 60000 and loan["extra_funding_to_hold_buffer_usd"] == 0  # -50k vs 10k buffer
    assert r["green_certified"] is False and r["is_estimate"] is True


@pytest.mark.parametrize("kw", [{"capex_week": 0}, {"capex_week": 14}, {"financed_pct": 120}, {"tenor_months": 3}, {"loan_apr_pct": float("nan")}])
def test_bad_inputs_are_refused(kw):
    args = dict(capex_week=2, financed_pct=80, loan_apr_pct=12, tenor_months=36)
    args.update(kw)
    with pytest.raises(ValueError):
        green_cash_impact([1.0] * 13, 0, PROJECT, electricity_price_usd_per_kwh=0.1, **args)


def test_api_uses_live_forecast_and_loan_quote(tmp_path):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    backend = RealBackend(runtime_dir=tmp_path, clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    r = client.post("/api/green-finance/cash-impact", json={"project_id": "GREEN-SOLAR-001"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["without_project"]["min_closing_usd"] == pytest.approx(float(backend.coord.forecast.min_closing_usd), abs=0.01)
    assert "quote" in d["loan_apr_source"]
    assert d["cash_funded"]["min_closing_usd"] < d["loan_funded"]["min_closing_usd"] < d["without_project"]["min_closing_usd"]
    assert client.post("/api/green-finance/cash-impact", json={"project_id": "NOPE-1"}).status_code == 422
    assert client.post("/api/green-finance/cash-impact", json={"project_id": "GREEN-SOLAR-001"},
                       headers=client.header("bank.lihua")).status_code == 403
