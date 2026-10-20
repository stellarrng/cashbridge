"""Does a funding option actually cover the forecast gap, week by week?

Pure Python, no LLM. The 13-week engine reports the *first* negative week; this module answers
the follow-up question a credit officer asks next: after the money arrives (and is repaid), does the
balance stay above zero for the rest of the horizon, and how much is still missing at the trough?

Assumptions (always returned with the result):
  * funds arrive in the first shortfall week;
  * factoring is settled when the pledged invoice is due: the SME gives up the advance plus the
    total cost from that week's balance (the invoice cash goes to the factor instead);
  * a bridge loan is repaid in one bullet after its term; if that is beyond the horizon, no
    repayment appears in the 13 weeks;
  * an early-payment discount is agreed with the buyer and is not a lender product, so no coverage
    is computed for it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence


def week_of(start: date, day: date, horizon: int) -> Optional[int]:
    """1-based forecast week containing ``day`` or None when outside the horizon."""
    index = (day - start).days // 7 + 1
    return index if 1 <= index <= horizon else None


def coverage(
    weeks: Sequence[Any],
    *,
    option: Any,
    funding_week: int,
    buffer_usd: Decimal,
    start_date: date,
    settle_on: Optional[date] = None,
    schedule: Any = None,
    invoice_receipts: Sequence[Any] = (),
) -> Optional[Dict[str, Any]]:
    """Closing balances with the option applied, plus the residual gap. None for non-lender options.

    With a ``schedule`` (core/funding_schedule.py) the dates come from it: money arrives in the drawdown
    week and, for factoring, each expected receipt of the pledged invoice is replaced by its share of
    the factor's rebate, so the invoice is never counted twice. ``funding_week`` is then ignored.
    """
    if option.type not in ("factoring", "loan") or option.amount_usd is None:
        return None
    if schedule is not None:
        return _scheduled(weeks, option, schedule, invoice_receipts, buffer_usd, start_date)
    horizon = len(weeks)
    amount = Decimal(option.amount_usd)
    total_cost = Decimal(option.cost_breakdown.get("total_usd", 0))
    fee_upfront = Decimal(option.cost_breakdown.get("fee_usd", 0)) if option.type == "loan" else Decimal(0)
    repay_week: Optional[int] = None
    repay_amount = Decimal(0)
    if option.type == "factoring" and settle_on is not None:
        repay_week = week_of(start_date, settle_on, horizon)
        repay_amount = amount + total_cost
    elif option.type == "loan":
        days = int(option.assumptions.get("days", 90))
        repay_week = funding_week + -(-days // 7)
        repay_week = repay_week if repay_week <= horizon else None
        repay_amount = amount + total_cost - fee_upfront
    adjustment = Decimal(0)
    rows: List[Dict[str, Any]] = []
    for row in weeks:
        week = int(row.week)
        if week == funding_week:
            adjustment += amount - fee_upfront
        if repay_week is not None and week == repay_week:
            adjustment -= repay_amount
        closing = Decimal(row.closing) + adjustment
        rows.append({"week": week, "closing_before": float(row.closing), "closing_after": float(closing),
                     "below_zero": closing < 0, "below_buffer": closing < buffer_usd})
    negative_after = [r["week"] for r in rows if r["below_zero"]]
    trough = min(rows, key=lambda r: r["closing_after"])
    residual = max(Decimal(0), Decimal(str(trough["closing_after"])) * -1)
    return {
        "option_id": option.id,
        "funding_week": funding_week,
        "settlement_week": repay_week,
        "settlement_usd": float(repay_amount) if repay_week else 0.0,
        "covers_first_gap": not rows[funding_week - 1]["below_zero"],
        "first_negative_week_after": negative_after[0] if negative_after else None,
        "negative_weeks_after": len(negative_after),
        "trough_week": trough["week"],
        "trough_closing_usd": trough["closing_after"],
        "residual_gap_usd": float(residual.quantize(Decimal("0.01"))),
        "residual_gap_with_buffer_usd": float(max(Decimal(0), buffer_usd - Decimal(str(trough["closing_after"]))).quantize(Decimal("0.01"))),
        "weeks": rows,
        "assumptions": [
            f"Funds arrive in week {funding_week} (the first shortfall week).",
            ("Factoring settles when the pledged invoice is due: advance plus total cost leaves the balance in week "
             f"{repay_week}." if option.type == "factoring" and repay_week else
             "Loan is a single bullet repayment after its term." if option.type == "loan" else ""),
            "The 13-week base forecast contains open invoices and confirmed orders (at shipment confidence); no unconfirmed sales.",
            ("Cost is quoted for drawdown today (interest to the due date); if the lender advances later, interest is lower, "
             "so the quoted cost is an upper bound." if option.type == "factoring" else ""),
        ],
    }


def _scheduled(weeks: Sequence[Any], option: Any, schedule: Any, invoice_receipts: Sequence[Any], buffer_usd: Decimal,
               start_date: date) -> Dict[str, Any]:
    horizon = len(weeks)
    by_week: Dict[int, Decimal] = {}
    outside = Decimal(0)
    for day, amount in schedule.cash_adjustments(invoice_receipts):
        w = week_of(start_date, day, horizon) if day >= start_date else 1
        if w is None:
            outside += amount
        else:
            by_week[w] = by_week.get(w, Decimal(0)) + amount
    funding_week = week_of(start_date, schedule.drawdown_date, horizon) or 1
    adjustment = Decimal(0)
    rows: List[Dict[str, Any]] = []
    for row in weeks:
        week = int(row.week)
        adjustment += by_week.get(week, Decimal(0))
        closing = Decimal(row.closing) + adjustment
        rows.append({"week": week, "closing_before": float(row.closing), "closing_after": float(closing),
                     "adjustment": float(by_week.get(week, Decimal(0))), "below_zero": closing < 0, "below_buffer": closing < buffer_usd})
    negative_after = [r["week"] for r in rows if r["below_zero"]]
    trough = min(rows, key=lambda r: r["closing_after"])
    residual = max(Decimal(0), Decimal(str(trough["closing_after"])) * -1)
    settle_weeks = [w for w in sorted(by_week) if w != funding_week or len(by_week) == 1]
    first_gap = next((int(r.week) for r in weeks if Decimal(r.closing) < 0), funding_week)
    return {
        "option_id": option.id, "funding_week": funding_week, "settlement_week": settle_weeks[-1] if settle_weeks else None,
        "settlement_usd": float(-sum((by_week[w] for w in settle_weeks if w != funding_week), Decimal(0))),
        "covers_first_gap": not rows[first_gap - 1]["below_zero"],
        "first_negative_week_after": negative_after[0] if negative_after else None, "negative_weeks_after": len(negative_after),
        "trough_week": trough["week"], "trough_closing_usd": trough["closing_after"],
        "residual_gap_usd": float(residual.quantize(Decimal("0.01"))),
        "residual_gap_with_buffer_usd": float(max(Decimal(0), buffer_usd - Decimal(str(trough["closing_after"]))).quantize(Decimal("0.01"))),
        "after_horizon_usd": float(outside), "expected_cost_usd": float(schedule.expected_cost_usd(invoice_receipts)),
        "weeks": rows, "schedule": schedule.as_dict(), "scenarios": schedule.scenarios(),
        "assumptions": [
            f"Funds arrive on {schedule.drawdown_date.isoformat()} (week {funding_week}): the pack is drawn down when it is released.",
            ("Each expected receipt of the pledged invoice is replaced by its share of the factor's rebate "
             "(invoice minus advance, fee and interest to that day), so nothing is counted twice." if option.type == "factoring" else
             f"Loan repaid in one bullet on {schedule.expected_settlement_date.isoformat()} with interest for {schedule.days_financed} days."),
            "Interest is charged for the days actually financed (Actual/365); the cost is CashBridge's internal annualised estimate, not a legal APR.",
            "The 13-week base forecast contains open invoices and confirmed orders (at shipment confidence); no unconfirmed sales.",
        ],
    }


def peak_need(weeks: Sequence[Any], buffer_usd: Decimal) -> Dict[str, Any]:
    """Cash needed to keep every week at or above zero / the buffer in the base forecast."""
    trough = min(weeks, key=lambda r: Decimal(r.closing))
    closing = Decimal(trough.closing)
    return {
        "trough_week": int(trough.week),
        "trough_closing_usd": float(closing),
        "need_to_zero_usd": float(max(Decimal(0), -closing)),
        "need_to_buffer_usd": float(max(Decimal(0), buffer_usd - closing)),
        "negative_weeks": sum(1 for r in weeks if Decimal(r.closing) < 0),
    }
