"""Pack metric helpers."""

from datetime import date
from decimal import Decimal

from core.metrics import monthly_billing_volatility_pct, negative_cash_weeks, top_buyer_share_pct
from core.forecasting_engine import forecast_13w
from tests.fixtures import base_forecast_inputs, receivable, usd


def test_volatility_of_equal_months_is_zero_and_unequal_is_positive():
    equal = [(date(2026, m, 5), Decimal(1000)) for m in (1, 2, 3)]
    assert monthly_billing_volatility_pct(equal) == Decimal("0.0")
    uneven = [(date(2026, 1, 5), Decimal(1000)), (date(2026, 2, 5), Decimal(3000))]
    assert monthly_billing_volatility_pct(uneven) == Decimal("50.0")  # mean 2000, stdev 1000


def test_volatility_needs_two_months():
    assert monthly_billing_volatility_pct([(date(2026, 1, 5), Decimal(1))]) == Decimal("0.0")


def test_billings_in_the_same_month_are_summed():
    data = [(date(2026, 1, 2), Decimal(500)), (date(2026, 1, 20), Decimal(500)), (date(2026, 2, 2), Decimal(1000))]
    assert monthly_billing_volatility_pct(data) == Decimal("0.0")


def test_top_buyer_share():
    items = [
        receivable("A", usd("300"), date(2026, 11, 1), 1.0, buyer="B1"),
        receivable("B", usd("100"), date(2026, 11, 1), 1.0, buyer="B2"),
    ]
    assert top_buyer_share_pct(items) == Decimal("75.0")
    assert top_buyer_share_pct([]) == Decimal("0.0")


def test_negative_cash_weeks_counts_closing_below_zero():
    rows = forecast_13w(base_forecast_inputs()).weeks
    assert negative_cash_weeks(rows) == sum(1 for r in rows if r.closing < 0) > 0
