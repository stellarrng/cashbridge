"""Locked-metric helpers for the funding pack: billing volatility, concentration, negative weeks.

Pure Python. Every number a funding pack or its cover letter states comes from here or from
the other engines in ``core/``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable, List, Sequence, Tuple

from schemas.forecast_schemas import OpenReceivable, WeeklyCashRow


def monthly_billing_volatility_pct(billings: Iterable[Tuple[date, Decimal]]) -> Decimal:
    """Coefficient of variation (stdev / mean, in %) of monthly billed USD, 1 decimal place.

    ``billings`` is (issue_date, usd_amount). Months with no billing are not counted.
    """
    totals: Dict[Tuple[int, int], Decimal] = defaultdict(Decimal)
    for issued, usd in billings:
        totals[(issued.year, issued.month)] += usd
    if len(totals) < 2:
        return Decimal("0.0")
    values = list(totals.values())
    mean = sum(values, Decimal(0)) / len(values)
    variance = sum(((v - mean) ** 2 for v in values), Decimal(0)) / len(values)
    cv = variance.sqrt() / mean * 100
    return cv.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def top_buyer_share_pct(receivables: Sequence[OpenReceivable]) -> Decimal:
    """Share of open receivables (USD) owed by the single largest buyer, 1 decimal place."""
    by_buyer: Dict[str, Decimal] = defaultdict(Decimal)
    for item in receivables:
        by_buyer[item.buyer_id] += item.amount.to_usd()
    total = sum(by_buyer.values(), Decimal(0))
    if total <= 0:
        return Decimal("0.0")
    return (max(by_buyer.values()) / total * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def negative_cash_weeks(rows: Sequence[WeeklyCashRow]) -> int:
    """Number of forecast weeks that close below zero."""
    return sum(1 for row in rows if row.closing < 0)


def late_exposure_by_buyer(receivables: Sequence[OpenReceivable]) -> List[Tuple[str, str, Decimal, Decimal]]:
    """(buyer_id, buyer_name, open_usd, expected_late_usd) per buyer, largest expected-late first.

    Expected late value is invoice value times (1 - p_on_time). A dated promise counts as on time.
    """
    open_usd: Dict[str, Decimal] = defaultdict(Decimal)
    late_usd: Dict[str, Decimal] = defaultdict(Decimal)
    names: Dict[str, str] = {}
    for item in receivables:
        usd = item.amount.to_usd()
        chance_late = Decimal(0) if item.promised_date else Decimal(1) - Decimal(str(item.p_on_time))
        open_usd[item.buyer_id] += usd
        late_usd[item.buyer_id] += usd * chance_late
        names[item.buyer_id] = item.buyer_name
    rows = [
        (buyer, names[buyer], open_usd[buyer].quantize(Decimal("0.01")), late_usd[buyer].quantize(Decimal("0.01")))
        for buyer in open_usd
    ]
    return sorted(rows, key=lambda r: (-r[3], r[0]))
