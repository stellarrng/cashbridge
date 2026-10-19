import pytest
from core.capital_planning import evaluate_allocation

CASE = dict(available_cash_usd=100000, minimum_reserve_usd=20000, working_capital_usd=50000, marketing_usd=20000, green_investment_usd=60000)

def test_gap_and_deferred_marketing():
    result = evaluate_allocation(CASE)
    assert result["deployable_cash_usd"] == 80000
    assert result["funding_gap_usd"] == 50000
    assert result["gap_if_marketing_deferred_usd"] == 30000
    assert result["potential_gap_reduction_usd"] == 20000

def test_no_gap():
    assert evaluate_allocation({**CASE, "green_investment_usd": 0})["funding_gap_usd"] == 0

@pytest.mark.parametrize("value", [-1, "NaN", "not-a-number", float("inf"), True])
def test_rejects_bad_inputs(value):
    with pytest.raises(ValueError):
        evaluate_allocation({**CASE, "marketing_usd": value})

def test_reserve_cannot_exceed_cash():
    with pytest.raises(ValueError):
        evaluate_allocation({**CASE, "minimum_reserve_usd": 150000})
