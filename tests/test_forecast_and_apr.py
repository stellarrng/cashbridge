"""Forecasting engine and funding evaluator (Steps 1.2 and 1.3)."""

from decimal import Decimal

import pytest

from core.forecasting_engine import (
    compute_ccc,
    first_negative_week,
    forecast_13w,
    fx_exposure,
    simulate,
)
from core.funding_evaluator import (
    BridgeLoanTerms,
    EarlyDiscountTerms,
    FactoringTerms,
    FundingRequest,
    LenderCatalog,
    OverdraftTerms,
    calc_apr,
    early_discount_option,
    rank_options,
)
from schemas.document_schemas import Currency, Money
from schemas.forecast_schemas import LedgerSnapshot, ScenarioParams, to_contract
from tests.fixtures import base_forecast_inputs, receivable
from datetime import date


# ----------------------------------------------------------------- APR
def catalog(**overrides) -> LenderCatalog:
    data = dict(
        factoring=FactoringTerms(advance_pct=Decimal(80), fee_pct_of_invoice=Decimal("1.2"), interest_pa_pct=Decimal(8)),
        bridge_loan=BridgeLoanTerms(amount_usd=Decimal(46000), upfront_fee_pct=Decimal(1), interest_pa_pct=Decimal(14), days=90),
        early_discount=EarlyDiscountTerms(
            discount_pct=Decimal(2), discount_days=10, net_days=30, invoice_amount_usd=Decimal(46000)
        ),
        overdraft=None,
    )
    data.update(overrides)
    return LenderCatalog(**data)


def request(**overrides) -> FundingRequest:
    data = dict(invoice_id="INV-1030", invoice_amount_usd=Decimal(60000), days_outstanding=60)
    data.update(overrides)
    return FundingRequest(**data)


def test_apr_values_match_spec_table():
    menu = {o.id: o for o in rank_options(request(), catalog())}
    assert menu["factoring_inv1030"].apr_pct == pytest.approx(17.1, abs=0.1)
    assert menu["bridge_loan"].apr_pct == pytest.approx(18.2, abs=0.1)
    assert menu["early_discount"].apr_pct == pytest.approx(37.2, abs=0.1)


def test_two_ten_net_sixty_illustration():
    terms = EarlyDiscountTerms(discount_pct=Decimal(2), discount_days=10, net_days=60, invoice_amount_usd=Decimal(46000))
    assert early_discount_option(terms).apr_pct == pytest.approx(14.9, abs=0.1)


def test_ranking_order_and_overdraft_reason():
    menu = rank_options(request(), catalog())
    assert [o.id for o in menu] == ["factoring_inv1030", "bridge_loan", "early_discount", "overdraft"]
    assert [o.rank for o in menu] == [1, 2, 3, None]
    overdraft = menu[-1]
    assert overdraft.eligible is False and overdraft.ineligible_reason == "No overdraft facility on file"
    assert overdraft.apr_pct is None and overdraft.rank is None


def test_cost_breakdown_and_net_funds_rules():
    menu = {o.id: o for o in rank_options(request(), catalog())}
    factoring = menu["factoring_inv1030"]
    assert factoring.amount_usd == Decimal("48000.00")
    assert factoring.cost_breakdown == {
        "fee_usd": Decimal("720.00"), "interest_usd": Decimal("631.23"), "total_usd": Decimal("1351.23"),
    }
    bridge = menu["bridge_loan"]
    assert bridge.cost_breakdown["fee_usd"] == Decimal("460.00")  # deducted upfront
    assert menu["early_discount"].cost_breakdown["discount_usd"] == Decimal("920.00")
    assert factoring.formula == "APR = total cost / net funds x 365 / days"
    assert factoring.why_not_cheaper == "Cheapest eligible option."
    assert "1.1 points" in bridge.why_not_cheaper


def test_factoring_advance_covers_the_story_shortfall():
    advance = rank_options(request(), catalog())[0].amount_usd
    shortfall = forecast_13w(base_forecast_inputs()).shortfall_usd
    assert advance >= shortfall


def test_overdraft_is_eligible_only_with_a_facility():
    with_facility = catalog(overdraft=OverdraftTerms(facility_limit_usd=Decimal(20000), interest_pa_pct=Decimal(12)))
    menu = {o.id: o for o in rank_options(request(amount_needed_usd=Decimal(15000)), with_facility)}
    assert menu["overdraft"].eligible and menu["overdraft"].amount_usd == Decimal(15000)
    assert menu["overdraft"].apr_pct == pytest.approx(12.0, abs=0.01)


def test_flagged_invoice_makes_factoring_ineligible():
    menu = {
        o.id: o
        for o in rank_options(
            request(invoice_eligible=False, invoice_ineligible_reason="INV-1030 is FLAGGED"), catalog()
        )
    }
    option = menu["factoring_inv1030"]
    assert not option.eligible and option.ineligible_reason == "INV-1030 is FLAGGED"
    assert option.rank is None


def test_calc_apr_rejects_bad_input():
    with pytest.raises(ValueError):
        calc_apr(Decimal(1), Decimal(0), 30)


def test_option_output_has_contract_shape():
    first = to_contract(rank_options(request(), catalog())[0])
    assert first["cost_breakdown"]["total_usd"] == 1351.23
    assert set(first) == {
        "rank", "id", "name", "type", "amount_usd", "apr_pct", "eligible",
        "ineligible_reason", "cost_breakdown", "assumptions", "formula", "why_not_cheaper",
    }


# ----------------------------------------------------------------- CCC
def test_ccc_from_ledger():
    ledger = LedgerSnapshot(
        period_days=365,
        revenue_usd=Decimal(3_650_000),
        cogs_usd=Decimal(2_920_000),
        avg_inventory_usd=Decimal(280_000),  # DIO = 35.0
        avg_receivables_usd=Decimal(750_000),  # DSO = 75.0
        avg_payables_usd=Decimal(224_000),  # DPO = 28.0
    )
    ccc = compute_ccc(ledger)
    assert (ccc.dio, ccc.dso, ccc.dpo, ccc.ccc) == (35.0, 75.0, 28.0, 82.0)
    assert ccc.ccc == round(ccc.dio + ccc.dso - ccc.dpo, 1)


# ------------------------------------------------------------- forecast
def test_forecast_arithmetic_and_first_negative_week():
    result = forecast_13w(base_forecast_inputs())
    assert len(result.weeks) == 13
    for row in result.weeks:
        assert row.closing == row.opening + row.inflows - row.outflows
    for prev, nxt in zip(result.weeks, result.weeks[1:]):
        assert nxt.opening == prev.closing
    assert result.first_shortfall_week == 7 == first_negative_week(result.weeks)
    assert Decimal(40000) <= result.shortfall_usd <= Decimal(47000)
    assert result.weeks[6].status == "shortfall"
    assert all(row.status != "shortfall" for row in result.weeks[:6])


def test_status_uses_buffer():
    quiet = base_forecast_inputs(receivables=[], deposits=[], opening_cash_usd=Decimal("55000"))
    rows = forecast_13w(quiet).weeks
    assert [r.status for r in rows[:3]] == ["ok", "at_risk", "shortfall"]  # 35k, 0 (payroll week), -20k
    assert rows[0].closing == Decimal("35000")
    assert {r.status for r in forecast_13w(base_forecast_inputs()).weeks} <= {"ok", "at_risk", "shortfall"}


def test_late_remainder_arrives_four_weeks_after_due_week():
    inputs = base_forecast_inputs(
        receivables=[receivable("INV-9", Money.from_amount(Decimal(1000), Currency.USD), date(2026, 10, 19), 0.60)],
        deposits=[],
    )
    result = forecast_13w(inputs)
    assert result.weeks[0].inflows == Decimal("600.00")
    assert result.weeks[4].inflows == Decimal("400.00")


def test_attribution_sums_to_shortfall_exactly():
    result = forecast_13w(base_forecast_inputs())
    assert sum(item.amount_usd for item in result.attribution) == result.shortfall_usd
    drivers = {item.source_ref for item in result.attribution}
    assert {"doc:PO-2214", "inv:INV-1026", "ledger:baseline"} <= drivers
    deposit = next(i for i in result.attribution if i.source_ref == "doc:PO-2214")
    assert deposit.amount_usd == Decimal("27600.00")


def test_no_shortfall_means_no_attribution():
    result = forecast_13w(base_forecast_inputs(opening_cash_usd=Decimal("500000")))
    assert result.first_shortfall_week is None and result.shortfall_usd is None
    assert result.attribution == []


@pytest.mark.parametrize(
    "params",
    [
        ScenarioParams(dso_change_days=15),
        ScenarioParams(deposit_pct=10),
        ScenarioParams(tariff_shared_pct=100),
        ScenarioParams(fx_change_pct=-5),
    ],
)
def test_every_scenario_parameter_changes_the_result(params):
    inputs = base_forecast_inputs(
        receivables=base_forecast_inputs().receivables
        + [receivable("INV-JPY", Money.from_amount(3_500_000, Currency.JPY), date(2026, 11, 10), 1.0, market="JP")]
    )
    base = forecast_13w(inputs)
    out = simulate(inputs, params)
    assert [r.closing for r in out.forecast.weeks] != [r.closing for r in base.weeks]
    assert out.delta.min_closing_before_usd == base.min_closing_usd
    assert out.delta.min_closing_after_usd == out.forecast.min_closing_usd


def test_default_params_leave_forecast_unchanged():
    inputs = base_forecast_inputs()
    out = simulate(inputs, ScenarioParams())
    assert [r.closing for r in out.forecast.weeks] == [r.closing for r in forecast_13w(inputs).weeks]
    assert out.delta.first_shortfall_week_before == out.delta.first_shortfall_week_after == 7


def test_dso_increase_moves_shortfall_earlier_or_deeper():
    out = simulate(base_forecast_inputs(), ScenarioParams(dso_change_days=15))
    assert out.delta.min_closing_after_usd < out.delta.min_closing_before_usd


def test_scenario_attribution_still_sums_to_shortfall():
    inputs = base_forecast_inputs()
    out = simulate(inputs, ScenarioParams(tariff_shared_pct=50, deposit_pct=40))
    forecast = out.forecast
    assert sum(i.amount_usd for i in forecast.attribution) == forecast.shortfall_usd
    assert any(i.source_ref == "scenario:tariff_shared_pct" for i in forecast.attribution)


def test_delta_has_exactly_the_contract_fields():
    out = simulate(base_forecast_inputs(), ScenarioParams(dso_change_days=5))
    assert set(to_contract(out.delta)) == {
        "first_shortfall_week_before", "first_shortfall_week_after",
        "min_closing_before_usd", "min_closing_after_usd",
    }


def test_fx_exposure_is_symmetric_and_in_vnd():
    inputs = base_forecast_inputs(
        receivables=[receivable("INV-JPY", Money.from_amount(3_500_000, Currency.JPY), date(2026, 11, 10), 1.0, market="JP")],
        deposits=[],
    )
    rows = fx_exposure(inputs)
    week4 = rows[3]
    assert week4.foreign_inflow_usd == Decimal("23557.69")
    assert week4.impact_up_usd == -week4.impact_down_usd == Decimal("471.15")
    assert week4.impact_up_vnd == Decimal("471.15") * 26000
    assert sum(r.foreign_inflow_usd for r in rows) == Decimal("23557.69")


# ------------------------------------------------------------- promises
def test_a_dated_promise_moves_the_whole_amount_to_the_promised_week():
    inputs = base_forecast_inputs()
    base = forecast_13w(inputs)
    promised = [
        r.model_copy(update={"promised_date": date(2026, 11, 20)}) if r.invoice_id == "INV-1026" else r
        for r in inputs.receivables
    ]
    out = forecast_13w(inputs.model_copy(update={"receivables": promised}))
    assert out.weeks[4].inflows - base.weeks[4].inflows == Decimal("31480.00")  # Nov 20 is week 5
    assert out.shortfall_usd < base.shortfall_usd
    assert sum(i.amount_usd for i in out.attribution) == out.shortfall_usd
    assert not any(i.source_ref == "inv:INV-1026" for i in out.attribution)
