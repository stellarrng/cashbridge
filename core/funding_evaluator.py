"""Funding evaluator: true annualised cost of each liquidity option.

    APR = total_cost / net_funds_received x 365 / days_outstanding

Pure Python, no I/O, no LLM. Every option in the menu is computed here; nothing is
hard-coded. Lender terms come in through a ``LenderCatalog`` (read from
``data/sandbox_inputs/lender_catalog.json`` by the caller). All lenders are MOCK.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.forecast_schemas import LiquidityOption

APR_FORMULA = "APR = total cost / net funds x 365 / days"
DISCOUNT_FORMULA = "APR = d/(1-d) x 365 / (net days - discount days)"
_CENT = Decimal("0.01")


class FactoringTerms(BaseModel):
    """Terms of the mock partner factor."""

    recourse: str = Field(default="recourse", pattern="^(recourse|non_recourse)$")
    advance_pct: Decimal = Field(gt=0, le=100)
    fee_pct_of_invoice: Decimal = Field(ge=0)
    interest_pa_pct: Decimal = Field(ge=0)
    max_days: int = Field(default=120, gt=0)
    min_invoice_usd: Decimal = Field(default=Decimal("0"), ge=0)


class BridgeLoanTerms(BaseModel):
    """Terms of the mock working-capital bridge loan."""

    amount_usd: Decimal = Field(gt=0)
    upfront_fee_pct: Decimal = Field(ge=0)
    interest_pa_pct: Decimal = Field(ge=0)
    days: int = Field(gt=0)


class EarlyDiscountTerms(BaseModel):
    """An early-payment discount offered to a buyer, such as 2/10 net 30."""

    discount_pct: Decimal = Field(gt=0, lt=100)
    discount_days: int = Field(gt=0)
    net_days: int = Field(gt=0)
    invoice_amount_usd: Decimal = Field(gt=0)


class OverdraftTerms(BaseModel):
    """An existing overdraft facility."""

    facility_limit_usd: Decimal = Field(ge=0)
    interest_pa_pct: Decimal = Field(ge=0)


class LenderCatalog(BaseModel):
    """What the company can actually use. A missing section means not on offer."""

    factoring: Optional[FactoringTerms] = None
    bridge_loan: Optional[BridgeLoanTerms] = None
    early_discount: Optional[EarlyDiscountTerms] = None
    overdraft: Optional[OverdraftTerms] = None


class FundingRequest(BaseModel):
    """The invoice offered for factoring and the cash needed."""

    invoice_id: str
    invoice_amount_usd: Decimal = Field(gt=0)
    days_outstanding: int = Field(gt=0)
    invoice_eligible: bool = True
    invoice_ineligible_reason: Optional[str] = None
    amount_needed_usd: Decimal = Decimal("0")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def calc_apr(total_cost: Decimal, net_funds: Decimal, days: int) -> float:
    """Return the annualised cost as a percentage, rounded to 2 decimals."""
    if net_funds <= 0 or days <= 0:
        raise ValueError("net_funds and days must be positive")
    apr = total_cost / net_funds * Decimal(365) / Decimal(days) * 100
    return float(apr.quantize(_CENT, rounding=ROUND_HALF_UP))


def _simple_interest(principal: Decimal, rate_pa_pct: Decimal, days: int) -> Decimal:
    return _cents(principal * rate_pa_pct / 100 * Decimal(days) / Decimal(365))


def factoring_option(terms: FactoringTerms, request: FundingRequest) -> LiquidityOption:
    """Advance a share of the invoice; fee on invoice value; interest on the advance."""
    name = f"Factoring {request.invoice_id} (Partner Factor, MOCK)"
    base = dict(id="factoring_" + request.invoice_id.lower().replace("-", ""), name=name, type="factoring")
    assumptions = {
        "advance_pct": float(terms.advance_pct),
        "fee_pct_of_invoice": float(terms.fee_pct_of_invoice),
        "interest_pa_pct": float(terms.interest_pa_pct),
        "days": request.days_outstanding,
    }
    reason = None
    if not request.invoice_eligible:
        reason = request.invoice_ineligible_reason or f"{request.invoice_id} failed verification"
    elif request.days_outstanding > terms.max_days:
        reason = f"Invoice tenor {request.days_outstanding} days exceeds the {terms.max_days}-day limit"
    elif request.invoice_amount_usd < terms.min_invoice_usd:
        reason = f"Invoice is below the USD {terms.min_invoice_usd:,.0f} minimum"
    if reason:
        return LiquidityOption(
            eligible=False, ineligible_reason=reason, assumptions=assumptions, **base
        )

    advance = _cents(request.invoice_amount_usd * terms.advance_pct / 100)
    fee = _cents(request.invoice_amount_usd * terms.fee_pct_of_invoice / 100)
    interest = _simple_interest(advance, terms.interest_pa_pct, request.days_outstanding)
    total = fee + interest
    return LiquidityOption(
        eligible=True,
        amount_usd=advance,
        apr_pct=calc_apr(total, advance, request.days_outstanding),
        cost_breakdown={"fee_usd": fee, "interest_usd": interest, "total_usd": total},
        assumptions=assumptions,
        formula=APR_FORMULA,
        **base,
    )


def bridge_option(terms: BridgeLoanTerms) -> LiquidityOption:
    """Loan with the arrangement fee deducted upfront, so net funds are lower."""
    fee = _cents(terms.amount_usd * terms.upfront_fee_pct / 100)
    interest = _simple_interest(terms.amount_usd, terms.interest_pa_pct, terms.days)
    total = fee + interest
    net_funds = terms.amount_usd - fee
    return LiquidityOption(
        id="bridge_loan",
        name="Working-capital bridge loan (MOCK)",
        type="loan",
        eligible=True,
        amount_usd=terms.amount_usd,
        apr_pct=calc_apr(total, net_funds, terms.days),
        cost_breakdown={"fee_usd": fee, "interest_usd": interest, "total_usd": total},
        assumptions={
            "upfront_fee_pct": float(terms.upfront_fee_pct),
            "interest_pa_pct": float(terms.interest_pa_pct),
            "days": terms.days,
        },
        formula=APR_FORMULA,
    )


def early_discount_option(terms: EarlyDiscountTerms) -> LiquidityOption:
    """Giving up d% to be paid ``net - discount`` days sooner."""
    discount = _cents(terms.invoice_amount_usd * terms.discount_pct / 100)
    net_funds = terms.invoice_amount_usd - discount
    days = terms.net_days - terms.discount_days
    name = (
        f"Early-payment discount {terms.discount_pct.normalize():f}/{terms.discount_days} "
        f"net {terms.net_days}"
    )
    return LiquidityOption(
        id="early_discount",
        name=name,
        type="discount",
        eligible=True,
        amount_usd=terms.invoice_amount_usd,
        apr_pct=calc_apr(discount, net_funds, days),
        cost_breakdown={"discount_usd": discount, "total_usd": discount},
        assumptions={
            "discount_pct": float(terms.discount_pct),
            "discount_days": terms.discount_days,
            "net_days": terms.net_days,
        },
        formula=DISCOUNT_FORMULA,
    )


def overdraft_option(terms: Optional[OverdraftTerms], request: FundingRequest) -> LiquidityOption:
    """Eligible only when a facility with a positive limit exists in the catalog."""
    base = dict(id="overdraft", name="Overdraft", type="overdraft")
    if terms is None or terms.facility_limit_usd <= 0:
        return LiquidityOption(
            eligible=False, ineligible_reason="No overdraft facility on file", **base
        )
    amount = min(terms.facility_limit_usd, request.amount_needed_usd or terms.facility_limit_usd)
    interest = _simple_interest(amount, terms.interest_pa_pct, request.days_outstanding)
    return LiquidityOption(
        eligible=True,
        amount_usd=amount,
        apr_pct=calc_apr(interest, amount, request.days_outstanding),
        cost_breakdown={"interest_usd": interest, "total_usd": interest},
        assumptions={"interest_pa_pct": float(terms.interest_pa_pct), "days": request.days_outstanding},
        formula=APR_FORMULA,
        **base,
    )


def _why_not_cheaper(option: LiquidityOption, cheapest: LiquidityOption) -> str:
    if option is cheapest:
        return "Cheapest eligible option."
    gap = round((option.apr_pct or 0) - (cheapest.apr_pct or 0), 1)
    return f"About {gap:.1f} points a year more expensive than {cheapest.name}."


def rank_options(request: FundingRequest, catalog: LenderCatalog) -> List[LiquidityOption]:
    """Return eligible options by ascending APR, then ineligible options with reasons."""
    built: List[LiquidityOption] = []
    if catalog.factoring is not None:
        built.append(factoring_option(catalog.factoring, request))
    if catalog.bridge_loan is not None:
        built.append(bridge_option(catalog.bridge_loan))
    if catalog.early_discount is not None:
        built.append(early_discount_option(catalog.early_discount))
    built.append(overdraft_option(catalog.overdraft, request))

    eligible = sorted((o for o in built if o.eligible), key=lambda o: o.apr_pct or 0.0)
    ineligible = [o for o in built if not o.eligible]
    for position, option in enumerate(eligible, start=1):
        option.rank = position
        option.why_not_cheaper = _why_not_cheaper(option, eligible[0])
    return eligible + ineligible


def options_by_id(options: List[LiquidityOption]) -> Dict[str, LiquidityOption]:
    """Index a ranked menu by option id."""
    return {option.id: option for option in options}


def schedule_for(option: LiquidityOption, *, quote_date, drawdown_date, due_date=None, invoice_usd=None,
                 catalog: Optional[LenderCatalog] = None):
    """The FundingSchedule behind an eligible factoring or loan quote (core/funding_schedule.py).

    With drawdown on the quote date the schedule reproduces the quote exactly (tested); a later drawdown
    re-prices the interest for the days actually financed.
    """
    from datetime import timedelta
    from core.funding_schedule import FundingSchedule
    if not option.eligible or option.type not in ("factoring", "loan") or option.amount_usd is None:
        return None
    a = option.assumptions
    if option.type == "factoring":
        return FundingSchedule(option_id=option.id, option_type="factoring", quote_date=quote_date, drawdown_date=drawdown_date,
                               expected_settlement_date=due_date, principal_usd=Decimal(option.amount_usd),
                               rate_pa_pct=Decimal(str(a["interest_pa_pct"])), settlement_fee_usd=Decimal(option.cost_breakdown["fee_usd"]),
                               fee_basis="invoice", invoice_usd=Decimal(invoice_usd),
                               recourse=(catalog.factoring.recourse if catalog and catalog.factoring else "recourse"))
    return FundingSchedule(option_id=option.id, option_type="loan", quote_date=quote_date, drawdown_date=drawdown_date,
                           expected_settlement_date=drawdown_date + timedelta(days=int(a["days"])), principal_usd=Decimal(option.amount_usd),
                           rate_pa_pct=Decimal(str(a["interest_pa_pct"])), upfront_fee_usd=Decimal(option.cost_breakdown["fee_usd"]),
                           fee_basis="loan_amount")
