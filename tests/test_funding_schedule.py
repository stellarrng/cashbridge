"""FundingSchedule: one timeline for quote, 13-week cash and settlement; conservation to the cent; no double counting."""

import random
from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from core import funding_evaluator as fe
from core.funding_coverage import coverage
from core.funding_schedule import FundingSchedule, cents

Q = date(2026, 10, 19)


def factoring(drawdown=Q, due=Q + timedelta(days=60), recourse="recourse"):
    return FundingSchedule("f", "factoring", Q, drawdown, due, D("48000.00"), D("8"), settlement_fee_usd=D("720.00"),
                           invoice_usd=D("60000.00"), recourse=recourse)


@pytest.mark.parametrize("trial", range(150))
def test_schedule_reproduces_the_engine_quote_when_drawn_today(trial):
    r = random.Random(trial)
    inv = D(f"{r.randint(10_000, 900_000)}.{r.randint(0, 99):02d}")
    days = r.randint(7, 120)
    terms = fe.FactoringTerms(advance_pct=D(r.choice(["70", "80", "90"])), fee_pct_of_invoice=D(f"{r.randint(0, 300) / 100:.2f}"),
                              interest_pa_pct=D(f"{r.randint(100, 2400) / 100:.2f}"), max_days=120)
    opt = fe.factoring_option(terms, fe.FundingRequest(invoice_id="INV-T", invoice_amount_usd=inv, days_outstanding=days))
    s = fe.schedule_for(opt, quote_date=Q, drawdown_date=Q, due_date=Q + timedelta(days=days), invoice_usd=inv)
    assert s.total_cost_usd == opt.cost_breakdown["total_usd"] and s.annualised_cost_pct() == opt.apr_pct
    bridge = fe.bridge_option(fe.BridgeLoanTerms(amount_usd=D(r.randint(5000, 500000)), upfront_fee_pct=D("1.5"),
                                                 interest_pa_pct=D(f"{r.randint(100, 2400) / 100:.2f}"), days=r.randint(30, 365)))
    b = fe.schedule_for(bridge, quote_date=Q, drawdown_date=Q)
    assert b.total_cost_usd == bridge.cost_breakdown["total_usd"] and b.annualised_cost_pct() == bridge.apr_pct


def test_later_drawdown_reprices_interest_for_days_actually_financed():
    today, later = factoring(), factoring(drawdown=Q + timedelta(days=42))
    assert today.days_financed == 60 and later.days_financed == 18
    assert later.interest_usd == cents(D("48000") * D("0.08") * 18 / 365)  # 189.37
    assert later.total_cost_usd < today.total_cost_usd
    # the fixed fee spread over a shorter tenor raises the annualised figure: absolute cost is what to compare
    assert later.annualised_cost_pct() > today.annualised_cost_pct()


@pytest.mark.parametrize("split", [[D("60000")], [D("58200"), D("1800")], [D("20000.01"), D("19999.99"), D("20000")]])
def test_cash_adjustments_conserve_money_to_the_cent(split):
    s = factoring()
    receipts = [(Q + timedelta(days=60 + 28 * i), a) for i, a in enumerate(split)]
    adj = s.cash_adjustments(receipts)
    assert adj[0] == (Q, D("48000.00"))
    expected = s.settlement_fee_usd + sum(cents(a / sum(split) * s.interest_to(d)) for d, a in receipts)
    assert -sum(a for _, a in adj) == expected == s.expected_cost_usd(receipts)
    # each receipt is replaced, never added to: the repayment of advance + fee sums exactly to advance + fee
    repaid_base = sum(-a for _, a in adj[1:]) - sum(cents(a / sum(split) * s.interest_to(d)) for d, a in receipts)
    assert repaid_base == s.principal_usd + s.settlement_fee_usd


def test_settlement_scenarios_recourse_and_non_recourse():
    r = {x["scenario"]: x for x in factoring().scenarios()}
    assert r["on_time"]["total_cost_usd"] == 1351.23 and r["on_time"]["rebate_to_sme_usd"] == 10648.77  # 60,000-48,000-720-631.23
    assert r["late_30"]["interest_usd"] == float(cents(D("48000") * D("0.08") * 90 / 365))  # 30 more days of interest
    assert r["late_30"]["rebate_to_sme_usd"] < r["on_time"]["rebate_to_sme_usd"]
    assert r["default"]["sme_pays_factor_usd"] == float(D("48000") + D("720") + cents(D("48000") * D("0.08") * 150 / 365))
    nr = {x["scenario"]: x for x in factoring(recourse="non_recourse").scenarios()}
    assert nr["default"]["sme_pays_factor_usd"] == 0 and "factor" in nr["default"]["credit_loss_borne_by"]
    assert nr["default"]["total_cost_usd"] == 12000.0  # the forfeited reserve


def test_loan_schedule():
    loan = fe.schedule_for(fe.bridge_option(fe.BridgeLoanTerms(amount_usd=D("46000"), upfront_fee_pct=D("1"), interest_pa_pct=D("14"), days=90)),
                           quote_date=Q, drawdown_date=Q)
    adj = loan.cash_adjustments()
    assert adj == [(Q, D("45540.00")), (Q + timedelta(days=90), -(D("46000") + D("1587.95")))]
    assert -sum(a for _, a in adj) == loan.total_cost_usd == D("2047.95")


def test_invalid_timelines_are_refused():
    with pytest.raises(ValueError):
        factoring(drawdown=Q - timedelta(days=1))
    with pytest.raises(ValueError):
        FundingSchedule("f", "factoring", Q, Q, Q + timedelta(days=60), D("1"), D("1"), invoice_usd=D("2"), recourse="maybe")
    with pytest.raises(ValueError):
        FundingSchedule("f", "factoring", Q, Q + timedelta(days=10), Q + timedelta(days=5), D("1"), D("1"), invoice_usd=D("2"), recourse="recourse")


def test_live_coverage_uses_the_shared_timeline_and_conserves_cash(tmp_path):
    from agents.coordinator import nominee_receipts
    from scripts.run_demo_story import StoryClock
    from ui.backend_real import RealBackend
    c = RealBackend(runtime_dir=tmp_path, clock=StoryClock()).coord
    opt = next(o for o in c.options if o.id == "factoring_inv1030")
    s = c.schedules[opt.id]
    assert s.drawdown_date == c.as_of and s.total_cost_usd == opt.cost_breakdown["total_usd"]
    receipts = nominee_receipts(c)
    cov = coverage(c.forecast.weeks, option=opt, funding_week=7, buffer_usd=c.forecast.buffer_usd, start_date=c.forecast_inputs.start_date,
                   schedule=s, invoice_receipts=receipts)
    assert cov["funding_week"] == 1  # the same date the interest is charged from (not the chart's old week 7)
    total_adj = sum(D(str(r["adjustment"])) for r in cov["weeks"]) + D(str(cov["after_horizon_usd"]))
    assert total_adj == -D(str(cov["expected_cost_usd"]))
    last = cov["weeks"][-1]
    assert D(str(last["closing_after"])) - D(str(last["closing_before"])) == sum(D(str(r["adjustment"])) for r in cov["weeks"])
    assert {x["scenario"] for x in cov["scenarios"]} == {"on_time", "late_30", "default"}
    assert cov["covers_first_gap"] is True and cov["first_negative_week_after"] is None


def test_schedules_api_and_lender_view(tmp_path, monkeypatch):
    from api.main import create_app
    from scripts.run_demo_story import StoryClock
    from tests.authed import RoleClient
    from ui.backend_real import RealBackend
    monkeypatch.setenv("CASHBRIDGE_WORKSPACE_DB", str(tmp_path / "ws.db"))
    backend = RealBackend(runtime_dir=tmp_path / "rt", clock=StoryClock())
    client = RoleClient(create_app(lambda: backend, dist_dir=tmp_path / "none"))
    sc = client.get("/api/funding/schedules").json()
    assert set(sc) == {"factoring_inv1030", "bridge_loan"} and sc["factoring_inv1030"]["illustrative"] is True
    assert "not a lender offer" in sc["factoring_inv1030"]["label"]
    assert client.get("/api/funding/schedules", headers=client.header("bank.lihua")).status_code == 403
    client.post("/api/autopilot/run", json={"execute": True})
    client.post("/api/request_otp", headers=client.header("sme.minh"))
    pack = client.post("/api/approve", json={"code": backend.coord.otp.current_code()}).json()["snapshot"]["pack"]["pack_id"]
    fs = client.get(f"/api/bank/cases/{pack}").json()["funding_schedule"]
    assert fs["schedule"]["recourse"] == "recourse" and len(fs["scenarios"]) == 3
