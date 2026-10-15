"""Pydantic schemas (Step 0.3)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.agent_schemas import (
    ALLOWED_TRANSITIONS,
    CaseFile,
    CaseState,
    IllegalTransition,
    assert_transition,
    can_transition,
)
from schemas.document_schemas import Currency, ExtractedField, Money
from schemas.forecast_schemas import LiquidityOption, ScenarioParams, to_contract
from tests.fixtures import make_invoice, usd


def test_money_is_integer_minor_units():
    m = Money.from_amount(Decimal("48620.00"), Currency.USD)
    assert m.minor_units == 4_862_000
    assert isinstance(m.minor_units, int)
    assert m.display() == "USD 48,620.00"
    assert Money.from_amount(1_520_000, Currency.JPY).display() == "JPY 1,520,000"


def test_money_rejects_float_and_negative():
    with pytest.raises(TypeError):
        Money.from_amount(10.5, Currency.USD)
    with pytest.raises(ValidationError):
        Money(minor_units=-1, currency=Currency.USD)


def test_money_usd_conversion_uses_demo_rates():
    assert Money.from_amount(Decimal("1750000"), Currency.JPY).to_usd() == Decimal("11778.85")
    assert usd("100").to_usd_cents() == 10_000


def test_invoice_valid_and_rejects_bad_amounts():
    assert make_invoice("INV-1", "100").amount.minor_units == 10_000
    with pytest.raises(ValidationError):
        make_invoice("INV-1", "0")
    with pytest.raises(ValidationError):
        make_invoice("INV-1", "100", currency=Currency.JPY)  # amount currency differs


def test_extracted_field_confidence_range():
    assert ExtractedField(value="x", confidence=0.9, page=2).page == 2
    with pytest.raises(ValidationError):
        ExtractedField(value="x", confidence=1.2)


def test_scenario_params_match_ui_contract_controls():
    p = ScenarioParams()
    assert (p.dso_change_days, p.deposit_pct, p.tariff_shared_pct, p.fx_change_pct) == (0, 30, 0, 0)
    with pytest.raises(ValidationError):
        ScenarioParams(dso_change_days=31)
    with pytest.raises(ValidationError):
        ScenarioParams(fx_change_pct=6)


def test_liquidity_option_field_names_match_contract():
    expected = {
        "rank", "id", "name", "type", "amount_usd", "apr_pct", "eligible",
        "ineligible_reason", "cost_breakdown", "assumptions", "formula", "why_not_cheaper",
    }
    assert set(LiquidityOption.model_fields) == expected


def test_to_contract_turns_decimals_and_dates_into_json_values():
    out = to_contract({"a": Decimal("1.50"), "d": date(2026, 10, 19), "l": [Decimal("2")]})
    assert out == {"a": 1.5, "d": "2026-10-19", "l": [2.0]}


def test_legal_transitions_pass():
    assert can_transition(CaseState.NEW, CaseState.RECONCILED)
    assert can_transition(CaseState.FORECASTED, CaseState.CLOSED)
    assert can_transition(CaseState.SUBMITTED, CaseState.FUNDED)
    assert can_transition(CaseState.PACK_DRAFTED, CaseState.NEEDS_HUMAN)


@pytest.mark.parametrize(
    "current,target",
    [
        (CaseState.NEW, CaseState.SUBMITTED),
        (CaseState.RECONCILED, CaseState.AWAITING_APPROVAL),
        (CaseState.AWAITING_APPROVAL, CaseState.FUNDED),
        (CaseState.BLOCKED, CaseState.RECONCILED),
        (CaseState.FUNDED, CaseState.NEW),
    ],
)
def test_illegal_transitions_are_rejected(current, target):
    with pytest.raises(IllegalTransition):
        assert_transition(current, target)


def test_every_state_has_a_transition_entry():
    assert set(ALLOWED_TRANSITIONS) == set(CaseState)


def test_case_file_remembers_where_to_resume():
    case = CaseFile(case_id="case-1")
    case.move_to(CaseState.RECONCILED)
    case.move_to(CaseState.NEEDS_HUMAN, "low confidence")
    assert case.resume_state is CaseState.RECONCILED
    assert case.needs_human_reason == "low confidence"
    with pytest.raises(IllegalTransition):
        case.move_to(CaseState.SUBMITTED)
