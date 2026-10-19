"""Deterministic capital allocation scenario analysis for synthetic SME planning.

This is not a lending decision, recommendation, or optimization solver. Assumes
immediate outflows, one cash reserve, no new inflows, and no interest accrual.
"""
from decimal import Decimal, InvalidOperation
from typing import Any, Dict


def _money(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not number.is_finite() or number < 0 or number > Decimal("1000000000"):
        raise ValueError(f"{name} must be between 0 and 1 billion")
    return number


def evaluate_allocation(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Scenario-only gap estimate. Never authorizes borrowing or spending."""
    cash = _money(payload.get("available_cash_usd", 0), "available_cash_usd")
    reserve = _money(payload.get("minimum_reserve_usd", 0), "minimum_reserve_usd")
    working = _money(payload.get("working_capital_usd", 0), "working_capital_usd")
    marketing = _money(payload.get("marketing_usd", 0), "marketing_usd")
    green = _money(payload.get("green_investment_usd", 0), "green_investment_usd")
    if reserve > cash:
        raise ValueError("minimum_reserve_usd cannot exceed available_cash_usd")
    spend = working + marketing + green
    deployable = cash - reserve
    gap = max(Decimal(0), spend - deployable)
    spare = max(Decimal(0), deployable - spend)
    # Alternative illustrating a marketing delay; not an unconditional recommendation.
    gap_if_marketing_deferred = max(Decimal(0), working + green - deployable)
    def amt(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01")))
    return {
        "synthetic": True,
        "available_cash_usd": amt(cash),
        "minimum_reserve_usd": amt(reserve),
        "deployable_cash_usd": amt(deployable),
        "planned_spend_usd": amt(spend),
        "funding_gap_usd": amt(gap),
        "remaining_headroom_usd": amt(spare),
        "gap_if_marketing_deferred_usd": amt(gap_if_marketing_deferred),
        "potential_gap_reduction_usd": amt(gap - gap_if_marketing_deferred),
        "breakdown_usd": {"working_capital": amt(working), "marketing": amt(marketing), "green_investment": amt(green)},
        "notes": [
            "Scenario assumes all planned spending occurs immediately and is cash-funded.",
            "Existing obligations, future receipts, loan repayments, interest and ROI are not modeled here.",
            "A positive gap is not an approved or recommended loan amount; review the 13-week forecast and lending terms.",
        ],
    }
