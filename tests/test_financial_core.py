"""
Financial core: cash flow geometry, APR comparability, ranking.

Expected figures come from tests/golden_values.py, which is derived by hand
from the product terms and imports nothing from core/.
"""

import pytest

from core.forecasting_engine import calculate_ccc, run_13_week_forecast, simulate_forecast
from core.funding_evaluator import (
    evaluate_liquidity_options,
    summarise_comparison,
    annualized_simple_cost,
    effective_apr,
    check_facility_compatibility,
    build_factoring_facility,
    build_early_discount_facility,
    build_bridge_facility,
)
from tests import golden_values as gv


# ─────────────────────────────────────────────────────────────────────────────
# Cash conversion cycle
# ─────────────────────────────────────────────────────────────────────────────

def test_ccc_matches_hand_calculation():
    assert calculate_ccc().ccc_days == gv.EXPECTED_CCC_DAYS


# ─────────────────────────────────────────────────────────────────────────────
# 13-week forecast
# ─────────────────────────────────────────────────────────────────────────────

def test_every_week_matches_hand_calculation():
    rows = {r.week: r.closing_cash for r in run_13_week_forecast().weekly_breakdown}
    for week, expected in gv.EXPECTED_CLOSING_CASH.items():
        assert rows[week] == pytest.approx(expected, abs=0.01), (
            f"Week {week}: engine {rows[week]}, hand calculation {expected}"
        )


def test_trough_is_week_8_not_week_6():
    """
    REGRESSION. The README, the module docstrings and the demo narrative all
    described "a Week 6 critical shortfall of $31,350" and sized the financing
    against it. Week 6 is only the first week below zero; the trough is week 8
    at -$56,350. Sizing to week 6 underfunds the business by $25,000.
    """
    f = run_13_week_forecast()
    assert f.first_shortfall_week == gv.EXPECTED_FIRST_SHORTFALL_WEEK
    assert f.lowest_cash_week == gv.EXPECTED_TROUGH_WEEK
    assert f.lowest_cash_balance == pytest.approx(gv.EXPECTED_TROUGH_BALANCE, abs=0.01)
    assert f.lowest_cash_week != f.first_shortfall_week


def test_deficit_duration_and_end_state_are_reported():
    f = run_13_week_forecast()
    assert f.weeks_in_deficit == gv.EXPECTED_WEEKS_IN_DEFICIT
    assert f.deficit_duration_weeks == len(gv.EXPECTED_WEEKS_IN_DEFICIT)
    # The horizon closes negative: the shortfall is structural, not a one-week dip.
    assert f.ends_period_in_deficit is gv.EXPECTED_ENDS_IN_DEFICIT


def test_peak_funding_need_includes_the_operating_buffer():
    f = run_13_week_forecast()
    assert f.peak_funding_need_usd == pytest.approx(gv.EXPECTED_PEAK_FUNDING_NEED, abs=0.01)
    # Financing sized to return the balance to exactly zero is not a fundable
    # plan; the need is measured against the buffer.
    assert f.peak_funding_need_usd > gv.EXPECTED_PEAK_DEFICIT_NO_BUFFER


def test_funding_must_arrive_before_the_first_dip():
    f = run_13_week_forecast()
    assert f.funding_needed_by_week is not None
    assert f.funding_needed_by_week < f.first_shortfall_week


def test_financing_inflow_actually_closes_the_gap():
    """An advance sized to the peak need must lift every week to the buffer."""
    f = run_13_week_forecast()
    financed = run_13_week_forecast(
        financed_invoice_id="INV-2026-103",
        financing_advance_usd=f.peak_funding_need_usd,
        financing_week=5,
    )
    assert financed.shortfall_detected is False
    assert all(r.closing_cash >= 0 for r in financed.weekly_breakdown)


def test_factoring_advance_alone_does_not_close_the_gap():
    """
    The demo claim under test: "$55,250 factoring advance covers the Week 6
    shortfall." Net of fees the advance releases $54,518.44 against a trough of
    -$56,350, so the business is still short.
    """
    financed = run_13_week_forecast(
        financed_invoice_id="INV-2026-103",
        financing_advance_usd=gv.FACTORING_CASH_IN_HAND,
        financing_week=5,
    )
    assert financed.shortfall_detected is True
    assert financed.lowest_cash_balance < 0


def test_delayed_receipt_beyond_the_horizon_is_dropped_not_clamped():
    """
    The old simulator clamped a delayed invoice to week 13 (`min(due+delay,
    13)`), fabricating an inflow the scenario says has not arrived and making
    delays look less damaging than they are.
    """
    base = simulate_forecast()
    delayed = simulate_forecast(delay_buyer="Sakura", delay_weeks=4)
    base_total = sum(r.ar_inflows for r in base.weekly_breakdown)
    delayed_total = sum(r.ar_inflows for r in delayed.weekly_breakdown)
    # INV-2026-104 is due W11; +4 pushes it to W15, outside the horizon.
    assert delayed_total < base_total
    assert delayed.lowest_cash_balance <= base.lowest_cash_balance


# ─────────────────────────────────────────────────────────────────────────────
# APR primitive
# ─────────────────────────────────────────────────────────────────────────────

def test_simple_cost_matches_hand_calculation():
    assert annualized_simple_cost(731.56, 54_518.44, 45) == pytest.approx(
        gv.FACTORING_SIMPLE_COST, abs=0.01
    )
    assert annualized_simple_cost(1_300.00, 63_700.00, 45) == pytest.approx(
        gv.DISCOUNT_SIMPLE_COST, abs=0.01
    )


@pytest.mark.parametrize(
    "cost,cash,days",
    [(100, 0, 45), (100, -5_000, 45), (100, 10_000, 0), (-1, 10_000, 45)],
)
def test_simple_cost_refuses_undefined_inputs(cost, cash, days):
    with pytest.raises(ValueError):
        annualized_simple_cost(cost, cash, days)


def test_effective_apr_matches_hand_calculation():
    """Two-point flows reduce to (out/in)^(365/days) - 1, checkable by hand."""
    assert effective_apr([(0, 54_518.44), (45, -55_250.00)]) == pytest.approx(
        gv.FACTORING_EFFECTIVE_APR, abs=0.01
    )
    assert effective_apr([(0, 63_700.00), (45, -65_000.00)]) == pytest.approx(
        gv.DISCOUNT_EFFECTIVE_APR, abs=0.01
    )
    assert effective_apr([(0, 65_000.00), (45, -66_514.59)]) == pytest.approx(
        gv.BRIDGE_EFFECTIVE_APR, abs=0.01
    )


def test_effective_apr_exceeds_the_simple_measure():
    """
    The simple measure does not compound, so over a term shorter than a year
    it always understates the annual rate. Reporting it under the name "true
    APR", as an earlier version did, overstated how standardised it was.
    """
    simple = annualized_simple_cost(1_300.00, 63_700.00, 45)
    eff = effective_apr([(0, 63_700.00), (45, -65_000.00)])
    assert eff > simple


def test_effective_apr_handles_flows_at_several_dates():
    """
    The case the simple formula cannot express: a fee paid mid-term. The rate
    must sit above the same facility with no mid-term fee.
    """
    plain = effective_apr([(0, 100_000.0), (90, -103_000.0)])
    with_midterm_fee = effective_apr([(0, 100_000.0), (45, -500.0), (90, -103_000.0)])
    assert with_midterm_fee > plain


@pytest.mark.parametrize(
    "flows",
    [[], [(0, 100.0)], [(0, -100.0), (45, -50.0)], [(0, 100.0), (45, 50.0)]],
)
def test_effective_apr_refuses_flows_that_cannot_define_a_rate(flows):
    with pytest.raises(ValueError):
        effective_apr(flows)


# ─────────────────────────────────────────────────────────────────────────────
# Option construction
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def options():
    return evaluate_liquidity_options(
        invoice_id=gv.INVOICE_ID,
        invoice_amount_usd=gv.INVOICE_FACE_USD,
        days_until_due=gv.DAYS_UNTIL_DUE,
        cash_need_usd=gv.EXPECTED_PEAK_FUNDING_NEED,
    )


def _by_id(options, prefix):
    return next(o for o in options if o.option_id.startswith(prefix))


def test_no_hardcoded_override_for_the_demo_invoice():
    """
    REGRESSION. The engine contained
        if invoice_id == "INV-2026-103": net_advance = 55250; total_fee = 731.25
    so the demo invoice reproduced spec numbers instead of being computed.
    A different invoice ID with identical economics must produce identical
    output.
    """
    demo = evaluate_liquidity_options("INV-2026-103", 65_000.0, 45, 66_350.0)
    other = evaluate_liquidity_options("INV-9999-XXX", 65_000.0, 45, 66_350.0)
    for a, b in zip(demo, other):
        assert a.cash_in_hand_usd == b.cash_in_hand_usd
        assert a.total_cost_usd == b.total_cost_usd
        assert a.annualized_simple_cost_pct == b.annualized_simple_cost_pct
        assert a.effective_apr_pct == b.effective_apr_pct

    # And the derived fee is the correct 731.56, not the spec's 731.25.
    assert _by_id(demo, "OPT-A-").total_cost_usd == pytest.approx(
        gv.FACTORING_TOTAL_FEE, abs=0.01
    )


def test_factoring_economics(options):
    a = _by_id(options, "OPT-A-")
    assert a.gross_advance_usd == pytest.approx(gv.FACTORING_GROSS_ADVANCE, abs=0.01)
    assert a.reserve_held_usd == pytest.approx(gv.FACTORING_RESERVE, abs=0.01)
    assert a.total_cost_usd == pytest.approx(gv.FACTORING_TOTAL_FEE, abs=0.01)
    assert a.cash_in_hand_usd == pytest.approx(gv.FACTORING_CASH_IN_HAND, abs=0.01)
    assert a.annualized_simple_cost_pct == pytest.approx(gv.FACTORING_SIMPLE_COST, abs=0.01)
    assert a.effective_apr_pct == pytest.approx(gv.FACTORING_EFFECTIVE_APR, abs=0.01)


def test_factoring_apr_is_measured_on_cash_received_not_gross_advance(options):
    """
    The fee is deducted at drawdown, so the business never holds the gross
    advance. Taking the APR on the gross advance understates the cost.
    """
    a = _by_id(options, "OPT-A-")
    assert a.cash_in_hand_usd < a.gross_advance_usd
    understated = (a.total_cost_usd / a.gross_advance_usd) * (365 / 45) * 100
    assert a.annualized_simple_cost_pct > understated


def test_early_discount_term_derives_from_the_payment_terms(options):
    """
    "2/10 net 55" means 45 days of acceleration. The old code passed
    `days_until_due`, which is right only when the invoice happens to sit at
    exactly that point in its life.
    """
    b = _by_id(options, "OPT-B-")
    assert b.days_financed == gv.DISCOUNT_DAYS_ACCELERATED
    assert b.total_cost_usd == pytest.approx(gv.DISCOUNT_COST, abs=0.01)
    assert b.cash_in_hand_usd == pytest.approx(gv.DISCOUNT_CASH_IN_HAND, abs=0.01)
    assert b.annualized_simple_cost_pct == pytest.approx(gv.DISCOUNT_SIMPLE_COST, abs=0.01)
    assert b.effective_apr_pct == pytest.approx(gv.DISCOUNT_EFFECTIVE_APR, abs=0.01)


def test_early_discount_term_does_not_follow_days_until_due():
    """With 90 days left, the acceleration is still 45 — the terms decide it."""
    opts = evaluate_liquidity_options(gv.INVOICE_ID, 65_000.0, 90, 0.0)
    b = _by_id(opts, "OPT-B-")
    assert b.days_financed == gv.DISCOUNT_DAYS_ACCELERATED


def test_bridge_simple_cost_equals_its_quoted_rate_when_there_is_no_fee(options):
    """
    With simple interest settled at maturity and no origination fee, the
    SIMPLE measure must return the quoted rate exactly. If it does not, the
    formula is wrong. The EFFECTIVE rate is legitimately higher.
    """
    c = _by_id(options, "OPT-C-")
    assert c.annualized_simple_cost_pct == pytest.approx(gv.BRIDGE_NOMINAL_APR, abs=0.01)
    assert c.nominal_quoted_rate_pct == gv.BRIDGE_NOMINAL_APR
    assert c.effective_apr_pct == pytest.approx(gv.BRIDGE_EFFECTIVE_APR, abs=0.01)
    assert c.effective_apr_pct > c.nominal_quoted_rate_pct


def test_every_option_is_measured_by_the_same_two_formulas(options):
    for o in options:
        assert o.annualized_simple_cost_pct == pytest.approx(
            annualized_simple_cost(o.total_cost_usd, o.cash_in_hand_usd, o.days_financed),
            abs=0.01,
        ), f"{o.option_id} does not satisfy the common simple-cost definition"
        assert o.effective_apr_pct == pytest.approx(
            effective_apr([(f.day, f.amount_usd) for f in o.cash_flows]), abs=0.01
        ), f"{o.option_id}'s effective rate does not match its own cash flows"


def test_every_option_publishes_its_dated_cash_flows(options):
    """
    The reviewable artefact behind the rate. Without it a reader has to take
    the number on trust; with it they can re-derive it.
    """
    for o in options:
        assert len(o.cash_flows) >= 2
        assert o.cash_flows[0].day == 0
        assert o.cash_flows[0].amount_usd > 0
        assert any(f.amount_usd < 0 for f in o.cash_flows)
        assert o.apr_basis == "EFFECTIVE_IRR"


# ─────────────────────────────────────────────────────────────────────────────
# Coverage-aware ranking
# ─────────────────────────────────────────────────────────────────────────────

def test_no_single_product_closes_the_real_gap(options):
    singles = [o for o in options if o.option_type != "COMBINATION"]
    assert not any(o.covers_need for o in singles)
    assert _by_id(singles, "OPT-A-").residual_gap_usd == pytest.approx(
        gv.FACTORING_RESIDUAL_GAP, abs=0.01
    )
    assert _by_id(singles, "OPT-C-").residual_gap_usd == pytest.approx(
        gv.BRIDGE_RESIDUAL_GAP, abs=0.01
    )


def test_cheapest_option_is_not_ranked_first_when_it_leaves_a_hole(options):
    """
    The core ranking defect. Factoring has the lowest APR and the largest
    shortfall. An option that does not close the gap must never outrank one
    that does.
    """
    covering = [o for o in options if o.covers_need]
    assert covering, "A combination should have been constructed"
    assert options[0].covers_need is True
    cheapest = min(options, key=lambda o: o.effective_apr_pct)
    assert cheapest.option_id.startswith("OPT-A")
    assert cheapest.rank > 1


def test_combinations_are_built_only_from_compatible_products(options):
    combos = [o for o in options if o.option_type == "COMBINATION"]
    assert combos
    for c in combos:
        types = {f.option_type for f in c.facilities}
        for a, b in gv.INCOMPATIBLE_PAIRS:
            assert not {a, b}.issubset(types)


# ─────────────────────────────────────────────────────────────────────────────
# Facilities within a package
# ─────────────────────────────────────────────────────────────────────────────

def test_package_keeps_its_facilities_separate(options):
    """
    A package is two agreements with two counterparties, not one blended
    product. The previous model collapsed it into a single `provider` string
    and a single advance figure — which is how the demo came to write a
    two-funder package into the pledge registry as one pledge.
    """
    for c in [o for o in options if o.option_type == "COMBINATION"]:
        assert len(c.facilities) >= 2
        assert len({f.provider for f in c.facilities}) == len(c.facilities)
        for f in c.facilities:
            assert f.cash_in_hand_usd > 0
            assert f.cash_flows
        assert c.cash_in_hand_usd == pytest.approx(
            sum(f.cash_in_hand_usd for f in c.facilities), abs=0.01
        )


def test_only_the_secured_facility_pledges_the_receivable(options):
    """
    Factoring takes security over the invoice; a buyer discount settles it and
    an unsecured bridge touches it not at all. Registering any of the latter
    as a pledge would record security that does not exist.
    """
    for o in options:
        for f in o.facilities:
            expected = f.option_type in gv.FACILITIES_THAT_PLEDGE_THE_RECEIVABLE
            assert f.pledges_receivable is expected, f"{f.facility_id}"


def test_at_most_one_facility_per_package_pledges_the_receivable(options):
    for c in [o for o in options if o.option_type == "COMBINATION"]:
        assert sum(1 for f in c.facilities if f.pledges_receivable) <= 1


def test_two_secured_facilities_are_rejected_with_a_reason():
    a = build_factoring_facility(65_000.0, 45)
    b = build_factoring_facility(65_000.0, 45)
    ok, reason = check_facility_compatibility(a, b)
    assert ok is False
    assert "pledged once" in reason


def test_factoring_and_buyer_discount_are_rejected_with_a_reason():
    ok, reason = check_facility_compatibility(
        build_factoring_facility(65_000.0, 45),
        build_early_discount_facility(65_000.0, 45),
    )
    assert ok is False
    assert "same receivable" in reason


def test_a_permitted_pairing_still_says_what_was_not_checked():
    """
    CashBridge sees no conflict between factoring and an unsecured bridge. It
    has not read either contract, and exclusivity or negative-pledge clauses
    could still forbid the pairing. The package must not be presented as an
    approved structure.
    """
    ok, reason = check_facility_compatibility(
        build_factoring_facility(65_000.0, 45),
        build_bridge_facility(65_000.0, 45, 10_000.0),
    )
    assert ok is True
    assert "visible to CashBridge" in reason


def test_package_states_that_no_counterparty_has_agreed(options):
    for c in [o for o in options if o.option_type == "COMBINATION"]:
        assert any("decline" in con for con in c.cons)
        assert any("NOT been reviewed" in a for a in c.assumptions)


def test_combination_does_not_overdraw_beyond_the_need(options):
    """
    REGRESSION. Pooling both facilities at full size offered $119,518.44
    against a $66,350 need — the business would have paid interest on $53,000
    it did not require. Any amount-flexible facility is drawn for the residual
    only.
    """
    for c in [o for o in options if o.option_type == "COMBINATION"]:
        assert c.cash_in_hand_usd >= c.cash_need_usd
        assert c.cash_in_hand_usd == pytest.approx(c.cash_need_usd, abs=1.0), (
            f"{c.option_id} draws {c.cash_in_hand_usd} for a need of {c.cash_need_usd}"
        )


def test_combination_rate_is_solved_on_the_pooled_cash_flows(options):
    for c in [o for o in options if o.option_type == "COMBINATION"]:
        assert c.effective_apr_pct == pytest.approx(
            effective_apr([(f.day, f.amount_usd) for f in c.cash_flows]), abs=0.01
        )
        assert c.cash_in_hand_usd >= c.cash_need_usd


def test_cheapest_option_wins_when_it_does_cover_the_need():
    """Sanity check in the other direction: with a small gap, APR decides."""
    opts = evaluate_liquidity_options(gv.INVOICE_ID, 65_000.0, 45, 20_000.0)
    assert all(o.covers_need for o in opts)
    assert opts[0].option_id.startswith("OPT-A")
    assert opts[0].effective_apr_pct == min(o.effective_apr_pct for o in opts)


def test_summary_states_plainly_whether_the_gap_can_be_closed(options):
    s = summarise_comparison(options)
    assert s["gap_can_be_closed"] is True
    assert s["options_that_close_the_gap"] >= 1
    assert s["contains_simulated_terms"] is True
    assert "not a credit decision" in s["disclaimer"]
    # The summary must say which measure drove the ranking.
    assert "does not compound" in s["rate_basis_note"]


def test_summary_reports_an_unclosable_gap_honestly():
    opts = evaluate_liquidity_options(gv.INVOICE_ID, 65_000.0, 45, 500_000.0)
    s = summarise_comparison(opts)
    assert s["gap_can_be_closed"] is False
    assert s["recommended_option_id"] is None


def test_every_option_discloses_its_assumptions(options):
    for o in options:
        assert o.assumptions, f"{o.option_id} carries no assumptions"


@pytest.mark.parametrize("amount,days", [(0, 45), (-1, 45), (65_000, 0), (65_000, -5)])
def test_invalid_invoice_inputs_are_refused(amount, days):
    with pytest.raises(ValueError):
        evaluate_liquidity_options("INV-X", amount, days, 0.0)
