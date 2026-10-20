"""Financial Accuracy Audit: every money formula re-computed by an INDEPENDENT oracle and compared to the engine.

The oracles below are written from the textbook definitions with exact rational arithmetic
(fractions.Fraction) and their own half-up rounding. They share no code with the engines, so a
wrong formula, a float rounding slip or a mis-scaled unit in the engine makes these tests fail.
Hand-calculated literals for the demo case are checked as well, so the oracle itself is anchored.

Conventions audited (and documented in docs/FINANCIAL_ACCURACY_AUDIT.md):
  * annualised cost = total cost / net funds received x 365 / days  (simple, Actual/365, no compounding)
  * early-payment discount APR = d / (1 - d) x 365 / (net days - discount days)
  * simple interest = principal x rate x days / 365, rounded half-up to the cent
  * FX: amount x VND-per-unit / VND-per-USD, half-up to the cent; minor units per currency (JPY, VND: 0)
  * CVaR95 = mean of the worst ceil(5% x n) shortfalls
"""

from __future__ import annotations

import math
import random
from decimal import Decimal
from fractions import Fraction as F

import numpy as np
import pytest

from config.settings import FX_VND_PER_UNIT, USD_VND
from core import funding_evaluator as fe
from core import scenario_simulator as sim
from core.forecasting_engine import compute_ccc, forecast_13w, _invoice_views
from schemas.document_schemas import Currency, Money

RNG = random.Random(20261020)


def half_up(x: F, places: int = 2) -> F:
    """Independent half-up rounding on exact rationals (never banker's rounding)."""
    q = F(10) ** places
    scaled = x * q
    sign = -1 if scaled < 0 else 1
    return F(sign * math.floor(abs(scaled) + F(1, 2)), 1) / q


def d(x) -> F:
    return F(str(x))


# --------------------------------------------------------------------------- 1. demo case, hand-calculated
def test_demo_case_quotes_match_hand_calculation(tmp_path):
    """INV-1030: USD 60,000 due in 60 days; factor 80% advance, 1.2% fee, 8% p.a.; bridge 46,000 / 1% / 14% / 90 d; 2/10 net 30."""
    from scripts.run_demo_story import StoryClock
    from ui.backend_real import RealBackend
    opts = {o.id: o for o in RealBackend(runtime_dir=tmp_path, clock=StoryClock()).coord.options}
    f = opts["factoring_inv1030"]
    # 48,000 = 60,000 x 80%; 720 = 60,000 x 1.2%; 631.23 = 48,000 x 8% x 60/365 = 631.2328...
    assert (f.amount_usd, f.cost_breakdown["fee_usd"], f.cost_breakdown["interest_usd"], f.cost_breakdown["total_usd"]) == \
           (Decimal("48000.00"), Decimal("720.00"), Decimal("631.23"), Decimal("1351.23"))
    assert f.apr_pct == 17.12  # 1,351.23 / 48,000 x 365/60 = 17.1250%  -> 17.12 (not 17.13: 17.12499...)
    b = opts["bridge_loan"]
    # fee 460 deducted upfront -> net 45,540; interest 46,000 x 14% x 90/365 = 1,587.945 -> 1,587.95
    assert (b.cost_breakdown["fee_usd"], b.cost_breakdown["interest_usd"], b.cost_breakdown["total_usd"]) == \
           (Decimal("460.00"), Decimal("1587.95"), Decimal("2047.95"))
    assert b.apr_pct == 18.24  # 2,047.95 / 45,540 x 365/90 = 18.238%
    e = opts["early_discount"]
    assert e.cost_breakdown["total_usd"] == Decimal("920.00") and e.apr_pct == 37.24  # 2/98 x 365/20 = 37.245%
    assert opts["overdraft"].eligible is False  # no facility on file: never invented


def test_annualised_cost_boundary_is_not_rounded_up_by_float_error():
    # 17.125% exactly would round half-up to 17.13; the engine must use the exact value, 17.12499...
    exact = d("1351.23") / d("48000") * 365 / 60 * 100
    assert exact < F(17125, 1000) and fe.calc_apr(Decimal("1351.23"), Decimal("48000"), 60) == float(half_up(exact))


# --------------------------------------------------------------------------- 2. randomised oracle comparison
def oracle_factoring(inv, adv_pct, fee_pct, rate, days):
    advance = half_up(inv * adv_pct / 100)
    fee = half_up(inv * fee_pct / 100)
    interest = half_up(advance * rate / 100 * days / 365)
    total = fee + interest
    return advance, fee, interest, total, half_up(total / advance * F(365, days) * 100)


def oracle_bridge(amount, fee_pct, rate, days):
    fee = half_up(amount * fee_pct / 100)
    interest = half_up(amount * rate / 100 * days / 365)
    total = fee + interest
    return fee, interest, total, half_up(total / (amount - fee) * F(365, days) * 100)


def oracle_discount(inv, disc_pct, disc_days, net_days):
    disc = half_up(inv * disc_pct / 100)
    return disc, half_up(disc / (inv - disc) * F(365, net_days - disc_days) * 100)


@pytest.mark.parametrize("trial", range(300))
def test_funding_options_match_exact_oracle(trial):
    r = random.Random(trial)
    inv = d(f"{r.randint(10_000, 2_000_000)}.{r.randint(0, 99):02d}")
    adv, fee_pct, rate = d(r.choice(["70", "75", "80", "85", "90"])), d(f"{r.randint(0, 300) / 100:.2f}"), d(f"{r.randint(100, 2400) / 100:.2f}")
    days = r.randint(1, 120)
    o = fe.factoring_option(fe.FactoringTerms(advance_pct=Decimal(str(adv)), fee_pct_of_invoice=Decimal(str(float(fee_pct))),
                                              interest_pa_pct=Decimal(str(float(rate))), max_days=120),
                            fe.FundingRequest(invoice_id="INV-X", invoice_amount_usd=Decimal(str(float(inv))), days_outstanding=days))
    a, f_, i, t, apr = oracle_factoring(inv, adv, fee_pct, rate, days)
    assert (d(o.amount_usd), d(o.cost_breakdown["fee_usd"]), d(o.cost_breakdown["interest_usd"]), d(o.cost_breakdown["total_usd"])) == (a, f_, i, t)
    assert d(o.apr_pct) == apr

    amt, bfee, brate, bdays = d(r.randint(5_000, 900_000)), d(f"{r.randint(0, 300) / 100:.2f}"), d(f"{r.randint(100, 3000) / 100:.2f}"), r.randint(7, 365)
    bo = fe.bridge_option(fe.BridgeLoanTerms(amount_usd=Decimal(str(amt)), upfront_fee_pct=Decimal(str(float(bfee))),
                                             interest_pa_pct=Decimal(str(float(brate))), days=bdays))
    of, oi, ot, oapr = oracle_bridge(amt, bfee, brate, bdays)
    assert (d(bo.cost_breakdown["fee_usd"]), d(bo.cost_breakdown["interest_usd"]), d(bo.cost_breakdown["total_usd"]), d(bo.apr_pct)) == (of, oi, ot, oapr)

    dd, nd = r.randint(1, 20), r.randint(21, 90)
    dp = d(f"{r.randint(10, 500) / 100:.2f}")
    eo = fe.early_discount_option(fe.EarlyDiscountTerms(discount_pct=Decimal(str(float(dp))), discount_days=dd, net_days=nd,
                                                        invoice_amount_usd=Decimal(str(float(inv)))))
    odisc, oeapr = oracle_discount(inv, dp, dd, nd)
    assert d(eo.cost_breakdown["total_usd"]) == odisc and d(eo.apr_pct) == oeapr


def test_half_up_rounding_at_exact_half_cent():
    # 182.50 x 1% x 1/365 x 365 ... construct interest of exactly 0.005: principal 182.5, 1% p.a., 1 day -> 0.005
    assert fe._simple_interest(Decimal("182.5"), Decimal("1"), 1) == Decimal("0.01")  # banker's rounding would give 0.00
    # 2.675 is the classic float trap: Decimal half-up must give 2.68
    assert fe._cents(Decimal("2.675")) == Decimal("2.68")


def test_apr_refuses_impossible_inputs():
    for args in [(Decimal("1"), Decimal("0"), 30), (Decimal("1"), Decimal("100"), 0), (Decimal("1"), Decimal("-5"), 30)]:
        with pytest.raises(ValueError):
            fe.calc_apr(*args)


# --------------------------------------------------------------------------- 3. currency
@pytest.mark.parametrize("trial", range(200))
def test_fx_conversion_matches_oracle_and_minor_units(trial):
    r = random.Random(1000 + trial)
    cur = r.choice(["USD", "JPY", "CNY", "VND"])
    digits = {"USD": 2, "JPY": 0, "CNY": 2, "VND": 0}[cur]
    raw = F(r.randint(0, 10 ** 9), 10 ** r.randint(0, 3))
    m = Money.from_amount(Decimal(raw.numerator) / Decimal(raw.denominator), Currency(cur))
    assert d(m.amount) == half_up(raw, digits)  # minor units rounded half-up once, at entry
    expected = half_up(d(m.amount) * d(FX_VND_PER_UNIT[cur]) / USD_VND, 2)
    assert d(m.to_usd()) == expected
    assert m.to_usd_cents() == int(expected * 100)


def test_fx_rates_are_the_labelled_assumptions():
    # 26,000 VND/USD; JPY 175 VND -> 148.57 JPY/USD; CNY 3,650 VND -> 7.123 CNY/USD
    assert Money.from_amount("1520000", Currency.JPY).to_usd() == Decimal("10230.77")  # 1,520,000 x 175 / 26,000
    assert Money.from_amount("100000.00", Currency.CNY).to_usd() == Decimal("14038.46")
    assert Money.from_amount("26000", Currency.VND).to_usd() == Decimal("1.00")
    with pytest.raises(TypeError):
        Money.from_amount(1.1, Currency.USD)  # floats are refused at the boundary


# --------------------------------------------------------------------------- 4. forecast arithmetic
def _inputs(tmp_path):
    from scripts.run_demo_story import StoryClock
    from ui.backend_real import RealBackend
    return RealBackend(runtime_dir=tmp_path, clock=StoryClock()).coord.forecast_inputs


@pytest.mark.parametrize("dso,deposit,tariff,fx", [(0, 30, 0, 0), (15, 30, 0, 0), (-10, 15, 50, 3), (30, 45, 100, -5), (0, 0, 0, 5)])
def test_weekly_cash_identities_hold_exactly(tmp_path, dso, deposit, tariff, fx):
    from core.forecasting_engine import apply_params
    from schemas.forecast_schemas import ScenarioParams
    inputs = apply_params(_inputs(tmp_path), ScenarioParams(dso_change_days=dso, deposit_pct=deposit, tariff_shared_pct=tariff, fx_change_pct=fx))
    f = forecast_13w(inputs)
    assert d(f.weeks[0].opening) == d(inputs.opening_cash_usd)
    for prev, row in zip([None] + f.weeks[:-1], f.weeks):
        assert d(row.closing) == d(row.opening) + d(row.inflows) - d(row.outflows)  # exact, no drift
        if prev is not None:
            assert d(row.opening) == d(prev.closing)
        expected = "shortfall" if row.closing < 0 else "at_risk" if row.closing < inputs.buffer_usd else "ok"
        assert row.status == expected
    neg = [r.week for r in f.weeks if r.closing < 0]
    assert f.first_shortfall_week == (neg[0] if neg else None)
    assert d(f.min_closing_usd) == min(d(r.closing) for r in f.weeks)
    if neg:
        assert d(f.shortfall_usd) == -d(f.weeks[neg[0] - 1].closing)
        # The drivers explain the shortfall to the cent.
        assert sum(d(a.amount_usd) for a in f.attribution) == d(f.shortfall_usd)


def test_receivable_split_is_conserved(tmp_path):
    """Every invoice's final value = on-time part + late part; nothing is created or lost by rounding."""
    inputs = _inputs(tmp_path)
    for v in _invoice_views(inputs):
        assert d(v.on_time) + d(v.late) == d(v.final_usd)
        assert d(v.final_usd) == d(v.raw_usd) + d(v.fx_effect) + d(v.tariff_effect)
        assert d(v.late) >= 0 and d(v.on_time) >= 0


def test_total_horizon_inflows_equal_independent_receipt_schedule(tmp_path):
    from config.settings import FORECAST_WEEKS, LATE_PAYMENT_DELAY_WEEKS
    inputs = _inputs(tmp_path)
    f = forecast_13w(inputs)
    oracle = F(0)
    for v in _invoice_views(inputs):
        if v.due_week <= FORECAST_WEEKS:
            oracle += d(v.on_time)
        if v.due_week + LATE_PAYMENT_DELAY_WEEKS <= FORECAST_WEEKS:
            oracle += d(v.late)
    assert sum(d(r.inflows) for r in f.weeks) == oracle


def test_ccc_components_match_definition():
    from schemas.forecast_schemas import LedgerSnapshot
    led = LedgerSnapshot(revenue_usd=Decimal("4615385"), cogs_usd=Decimal("3600000"), avg_receivables_usd=Decimal("700000"),
                         avg_inventory_usd=Decimal("650000"), avg_payables_usd=Decimal("420000"), period_days=365)
    c = compute_ccc(led)
    assert c.dso == float(half_up(d(700000) / d(4615385) * 365, 1))
    assert c.dio == float(half_up(d(650000) / d(3600000) * 365, 1))
    assert c.dpo == float(half_up(d(420000) / d(3600000) * 365, 1))
    assert c.ccc == round(c.dio + c.dso - c.dpo, 1)


# --------------------------------------------------------------------------- 5. risk measures
@pytest.mark.parametrize("n", [1, 7, 19, 20, 21, 999, 1000, 1001])
def test_cvar95_is_mean_of_worst_ceil_5pct(n):
    rng = np.random.default_rng(n)
    trough = rng.normal(-5_000, 20_000, size=n)
    trough[: n // 3] = -12_345.0  # ties at the boundary
    weeks = 13
    closing = np.repeat(trough[:, None], weeks, axis=1)

    class P:  # minimal stand-in exposing what summarize() reads
        buffer = 10_000.0
        params = sim.WorldParams()
        seed = 0
    P.n = n
    s = sim.summarize(P, closing)
    shortfalls = sorted((max(0.0, -t) for t in trough), reverse=True)
    k = max(1, math.ceil(0.05 * n))
    assert s["shortfall_cvar95_usd"] == pytest.approx(round(sum(shortfalls[:k]) / k, 2), abs=0.011)
    assert s["shortfall_cvar95_usd"] + 0.011 >= s["shortfall_p95_usd"]  # CVaR is never below VaR
    assert s["p_no_negative_week"] == pytest.approx(round(sum(t >= 0 for t in trough) / n, 4))


def test_wilson_interval_matches_published_values():
    from eval.ops_robustness import wilson
    # Reference: Wilson score interval, z = 1.96. 0/145 -> [0, 0.0258]; 35/145 -> [0.1790, 0.3171]
    assert wilson(0, 145) == [0.0, 0.0258]
    assert wilson(35, 145) == [0.179, 0.3171]


def test_baseline_brier_recomputed_from_raw_history():
    """Independent walk-forward of the historical-rate baseline straight from payment_history.json."""
    import json
    from config.settings import SANDBOX_INPUTS_DIR
    from eval.trust_scorecard import model_backtest
    recs = sorted(json.loads((SANDBOX_INPUTS_DIR / "payment_history.json").read_text())["records"], key=lambda r: r["issue_date"])
    scores = []
    for i in range(18, len(recs)):
        y = 1 if recs[i]["days_late"] <= 3 else 0
        p = F(sum(1 for r in recs[:i] if r["days_late"] <= 3), i)  # only earlier invoices: no look-ahead
        scores.append((p - y) ** 2)
    res = model_backtest()
    assert res["n_predictions"] == len(scores)
    assert res["brier_baseline"] == round(float(sum(scores) / len(scores)), 4)
    assert res["brier_model"] < res["brier_baseline"]


# --------------------------------------------------------------------------- 6. planner and green arithmetic
def test_planner_quotes_use_half_up_cents_like_the_engine():
    from datetime import date
    from agents import intelligence_core as ic
    p = ic.Pledgeable(ref="INV-T", buyer="B", buyer_id="B1", usd=182.5, due_date=date(2026, 10, 20), p_on_time=0.9)
    terms = {"advance_pct": 100.0, "fee_pct_of_invoice": 1.0, "interest_pa_pct": 1.0}
    a = ic.factor_action(p, terms, date(2026, 10, 19), 1)
    # fee = 1.825 -> 1.83 half-up (float round() would give 1.82); interest = 182.5 x 1% x 1/365 = 0.005 -> 0.01
    assert a["fee_usd"] == 1.83 and a["cost_usd"] == 1.84
    loan = ic.loan_action({"amount_usd": 182.5, "upfront_fee_pct": 1.0, "interest_pa_pct": 1.0, "days": 1}, 1)
    assert loan["fee_usd"] == 1.83 and loan["interest_usd"] == 0.01


def test_green_loan_instalment_is_a_standard_annuity():
    from core.green_finance import green_cash_impact
    project = {"project_id": "G", "activity_type": "rooftop_solar", "project_cost_usd": 150000,
               "baseline_kwh_year": 400000, "expected_generation_kwh_year": 200000}
    for apr, months in [(0.0, 12), (6.0, 36), (11.5, 60), (24.0, 120)]:
        r = green_cash_impact([0.0] * 13, 0, project, 1, 100, apr, months, 0.1, 0)
        loan = F(150000)
        i = d(apr) / 1200
        oracle = loan / months if i == 0 else loan * i / (1 - (1 + i) ** -months)
        assert r["loan_funded"]["monthly_instalment_usd"] == pytest.approx(float(oracle), abs=0.006)


def test_capital_plan_gap_arithmetic():
    from core.capital_planning import evaluate_allocation
    r = evaluate_allocation({"available_cash_usd": 100000, "minimum_reserve_usd": 15000, "working_capital_usd": 50000,
                             "marketing_usd": 30000, "green_investment_usd": 20000})
    assert (r["deployable_cash_usd"], r["planned_spend_usd"], r["funding_gap_usd"], r["remaining_headroom_usd"]) == (85000, 100000, 15000, 0)
    assert r["gap_if_marketing_deferred_usd"] == 0 and r["potential_gap_reduction_usd"] == 15000


@pytest.mark.parametrize("trial", range(200))
def test_planner_and_funding_engine_quote_the_same_cents(trial):
    """Same invoice, same terms, same days: the planner's quote must equal the funding engine's to the cent."""
    from datetime import date, timedelta
    from agents import intelligence_core as ic
    r = random.Random(5000 + trial)
    inv = round(r.uniform(10_000, 500_000), 2)
    terms = {"advance_pct": float(r.choice([70, 75, 80, 85, 90])), "fee_pct_of_invoice": r.randint(0, 300) / 100,
             "interest_pa_pct": r.randint(100, 2400) / 100}
    days = r.randint(7, 120)
    start = date(2026, 10, 19)
    a = ic.factor_action(ic.Pledgeable(ref="I", buyer_id="B", buyer="B", usd=inv, due_date=start + timedelta(days=days)), terms, start, 1)
    o = fe.factoring_option(fe.FactoringTerms(advance_pct=Decimal(str(terms["advance_pct"])), fee_pct_of_invoice=Decimal(str(terms["fee_pct_of_invoice"])),
                                              interest_pa_pct=Decimal(str(terms["interest_pa_pct"])), max_days=120),
                            fe.FundingRequest(invoice_id="I", invoice_amount_usd=Decimal(str(inv)), days_outstanding=days))
    assert (a["advance_usd"], a["fee_usd"], a["cost_usd"]) == (float(o.amount_usd), float(o.cost_breakdown["fee_usd"]), float(o.cost_breakdown["total_usd"]))
