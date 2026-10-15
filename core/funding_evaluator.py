"""
Funding Evaluator — same-basis cost-of-capital comparison.

HISTORY OF WHAT WAS WRONG HERE
------------------------------
Round 1 (as submitted):

  1. `if invoice_id == "INV-2026-103": net_advance = 55250.00; total_fee =
     731.25` — a hard-coded override so the output matched a number in the
     spec. The engine was not computing, it was reciting. The spec figure was
     also wrong: 55,250 x 1.125% = 621.5625, plus 110 is 731.5625.
  2. Each product used a different denominator, so the three were not
     comparable even in principle.
  3. Ranking was `sort(key=apr)`. The cheapest option is not the best option
     if it does not close the cash gap.

Round 2 (this file's previous version), raised in review:

  4. The single formula `(cost / cash) x (365 / days)` was reported under the
     name `apr_pct`. It is a linear annualisation of cost over cash received —
     a reasonable same-basis comparison, and the convention behind the
     familiar "2/10 net 30 is about 36%" figure — but it is NOT an effective
     APR under any standard convention. It does not compound, and it flattens
     a product with payments at several dates into one term. Calling it a true
     APR overstated how standardised the comparison was.
  5. A combined package was presented as one product with one `provider`
     string, when it is two agreements with two counterparties who can each
     decline independently. The demo then wrote that package into the pledge
     registry as a single pledge, with a combined advance figure, against an
     invoice that only one of the two facilities actually takes security over.

WHAT THIS FILE DOES NOW
-----------------------
Each product is built as a `Facility` with an explicit DATED CASH FLOW
SCHEDULE from the borrower's point of view. Two cost measures are reported
for every facility and every package:

    annualized_simple_cost_pct  (cost / cash) x (365 / days) x 100
    effective_apr_pct           the annual rate that discounts the actual
                                dated flows to zero (an IRR)

Ranking uses the effective rate. Both are shown, because the simple figure is
what an SME owner can check on paper and the effective figure is what stands
up to a credit analyst.

A package carries its facilities separately, each with its own counterparty,
and only a facility that takes security over the receivable is registered as a
pledge.

ALL ARITHMETIC IS PURE PYTHON. No LLM performs any calculation in this module.
"""

from itertools import combinations
from typing import List, Optional, Dict, Any, Tuple

from schemas.forecast_schemas import CashFlowEvent, Facility, LiquidityOption
from config.settings import (
    PermissionLevel,
    FINANCING_PRODUCTS,
    DAYS_PER_YEAR,
    USD_VND_RATE,
    FX_CONVERSION_SPREAD_PCT,
)
from security.permission_gatekeeper import request_permission


# ─────────────────────────────────────────────────────────────────────────────
# The two cost measures
# ─────────────────────────────────────────────────────────────────────────────

def annualized_simple_cost(
    total_cost_usd: float, cash_in_hand_usd: float, days_financed: int
) -> float:
    """
    Linear annualisation of total cost over cash actually received.

        (total_cost / cash_in_hand) x (365 / days) x 100

    Simple to audit by hand and comparable across products as long as each
    one's cost and cash are measured consistently. It does not compound and
    assumes a single term, so it is an approximation for any product with
    payments at several dates. Reported alongside, never instead of,
    `effective_apr`.

    Args:
        total_cost_usd: Every fee, discount and interest charge.
        cash_in_hand_usd: Spendable cash at drawdown.
        days_financed: Days between drawdown and settlement.

    Returns:
        Percentage, rounded to 4dp.

    Raises:
        ValueError: On non-positive cash or days, or negative cost.
    """
    if cash_in_hand_usd <= 0:
        raise ValueError("cash_in_hand_usd must be positive.")
    if days_financed <= 0:
        raise ValueError("days_financed must be positive.")
    if total_cost_usd < 0:
        raise ValueError("total_cost_usd cannot be negative.")
    return round(
        (total_cost_usd / cash_in_hand_usd) * (DAYS_PER_YEAR / days_financed) * 100.0, 4
    )


def _npv(rate: float, flows: List[Tuple[int, float]]) -> float:
    """Net present value of dated flows at an annual rate, actual/365."""
    return sum(
        amount / ((1.0 + rate) ** (day / DAYS_PER_YEAR)) for day, amount in flows
    )


def effective_apr(flows: List[Tuple[int, float]], tolerance: float = 1e-10) -> float:
    """
    Annualised internal rate of return of a facility's dated cash flows.

    Solves for the annual rate r where the discounted flows net to zero,
    actual/365 day count, compounded annually. Positive flows are cash into
    the business, negative are cash out, so for a borrowing the result is the
    cost of the money.

    Bisection rather than Newton: the flows here are small and well behaved,
    and bisection cannot diverge or land on a spurious root, which matters
    more than speed for a figure that goes in front of a credit analyst.

    Args:
        flows: (day, amount) pairs from the borrower's point of view. Must
            contain at least one positive and one negative amount.
        tolerance: NPV convergence tolerance.

    Returns:
        The annual rate as a percentage, rounded to 4dp.

    Raises:
        ValueError: If the flows cannot define a rate (all one sign, or no
            sign change across the search range).
    """
    if not flows:
        raise ValueError("No cash flows supplied.")
    if not any(a > 0 for _, a in flows) or not any(a < 0 for _, a in flows):
        raise ValueError(
            "Cash flows must contain both an inflow and an outflow to define a rate."
        )

    low, high = -0.9999, 100.0
    npv_low, npv_high = _npv(low, flows), _npv(high, flows)
    if npv_low * npv_high > 0:
        raise ValueError(
            "No rate in the searched range (-99.99% to 10000%) zeroes these flows."
        )

    for _ in range(300):
        mid = (low + high) / 2.0
        npv_mid = _npv(mid, flows)
        if abs(npv_mid) < tolerance:
            break
        if npv_low * npv_mid < 0:
            high, npv_high = mid, npv_mid
        else:
            low, npv_low = mid, npv_mid

    return round(((low + high) / 2.0) * 100.0, 4)


def _both_measures(
    total_cost_usd: float,
    cash_in_hand_usd: float,
    days_financed: int,
    flows: List[CashFlowEvent],
) -> Tuple[float, Optional[float]]:
    """Return (simple annualised cost, effective APR) for one facility."""
    simple = annualized_simple_cost(total_cost_usd, cash_in_hand_usd, days_financed)
    try:
        eff = effective_apr([(f.day, f.amount_usd) for f in flows])
    except ValueError:
        eff = None
    return simple, eff


def _fx_view(cash_in_hand_usd: float) -> Dict[str, float]:
    """
    What the advance is worth in VND after the bank's conversion spread.

    An exporter's costs are largely in VND, so a USD advance is not the amount
    that reaches the operating account. Disclosed separately rather than folded
    into the rate, because it applies identically to every USD option here.
    """
    spread_cost_usd = round(cash_in_hand_usd * (FX_CONVERSION_SPREAD_PCT / 100.0), 2)
    return {
        "fx_cost_usd": spread_cost_usd,
        "net_cash_realized_vnd": round((cash_in_hand_usd - spread_cost_usd) * USD_VND_RATE, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Facilities
# ─────────────────────────────────────────────────────────────────────────────

def build_factoring_facility(invoice_amount_usd: float, days_until_due: int) -> Facility:
    """
    Invoice factoring: an advance against the receivable, fee netted at drawdown.

    Cash flows from the borrower's point of view:
        day 0   + gross advance - fees
        day N   - invoice face value (the factor collects it)
                + reserve released

    Modelling the reserve as a day-N inflow is what makes the effective rate
    correct: the holdback is not a cost, it is cash deferred, and treating it
    as either a fee or as nothing both give the wrong answer.
    """
    t = FINANCING_PRODUCTS["WEBANK_FACTORING"]

    gross_advance = round(invoice_amount_usd * t["advance_rate"], 2)
    reserve = round(invoice_amount_usd - gross_advance, 2)
    total_fee = round(gross_advance * t["fee_rate_on_advance"] + t["flat_fee_usd"], 2)

    if t["fee_deducted_upfront"]:
        upfront, deferred = total_fee, 0.0
        cash_in_hand = round(gross_advance - total_fee, 2)
    else:
        upfront, deferred = 0.0, total_fee
        cash_in_hand = gross_advance

    # The business forgoes the invoice at maturity and gets the reserve back.
    # Net obligation at day N is (face - reserve) = the gross advance, plus any
    # fee that was not taken upfront.
    flows = [
        CashFlowEvent(day=0, amount_usd=cash_in_hand, label="Advance net of fees"),
        CashFlowEvent(
            day=days_until_due,
            amount_usd=-round(gross_advance + deferred, 2),
            label="Invoice collected by factor, net of reserve released",
        ),
    ]
    simple, eff = _both_measures(total_fee, cash_in_hand, days_until_due, flows)

    return Facility(
        facility_id="FAC-A-WEBANK-FACTORING",
        provider=t["provider"],
        option_type=t["option_type"],
        pledges_receivable=True,
        gross_advance_usd=gross_advance,
        upfront_fees_usd=upfront,
        cash_in_hand_usd=cash_in_hand,
        deferred_cost_usd=deferred,
        total_cost_usd=total_fee,
        reserve_held_usd=reserve,
        days_financed=days_until_due,
        cash_flows=flows,
        annualized_simple_cost_pct=simple,
        effective_apr_pct=eff,
        nominal_quoted_rate_pct=round(t["fee_rate_on_advance"] * 100, 3),
        is_mock_partner=t["is_mock_partner"],
        assumptions=[
            "Fee is charged on the advance, not the invoice face value",
            "Fee is deducted at drawdown rather than billed at maturity",
            f"Reserve of ${reserve:,.2f} is released in full when the buyer pays "
            f"on time; a dispute or short payment reduces or eliminates it, and "
            f"the effective rate rises accordingly",
            "Non-recourse is assumed; with recourse the business also carries "
            "the buyer's credit risk, which this rate does not price",
            "SIMULATED TERMS — no signed factoring partner exists",
        ],
    )


def build_early_discount_facility(
    invoice_amount_usd: float, days_until_due: int
) -> Facility:
    """
    Buyer early-payment discount on "d/N net M" terms.

    The acceleration period is (net_terms - discount_period), derived from the
    terms. Using `days_until_due` instead is right only when the invoice
    happens to sit at exactly that point in its life.
    """
    t = FINANCING_PRODUCTS["EARLY_PAYMENT_DISCOUNT"]
    d = t["discount_rate_pct"]

    days_accelerated = min(t["net_terms_days"] - t["discount_period_days"], days_until_due)
    discount_cost = round(invoice_amount_usd * (d / 100.0), 2)
    cash_in_hand = round(invoice_amount_usd - discount_cost, 2)

    flows = [
        CashFlowEvent(day=0, amount_usd=cash_in_hand, label="Buyer settles early, net of discount"),
        CashFlowEvent(
            day=days_accelerated,
            amount_usd=-invoice_amount_usd,
            label="Face value forgone on the original due date",
        ),
    ]
    simple, eff = _both_measures(discount_cost, cash_in_hand, days_accelerated, flows)

    return Facility(
        facility_id="FAC-B-EARLY-DISCOUNT",
        provider=t["provider"],
        option_type=t["option_type"],
        # The buyer settles the invoice; no third party takes security over it.
        pledges_receivable=False,
        gross_advance_usd=invoice_amount_usd,
        upfront_fees_usd=discount_cost,
        cash_in_hand_usd=cash_in_hand,
        deferred_cost_usd=0.0,
        total_cost_usd=discount_cost,
        reserve_held_usd=0.0,
        days_financed=days_accelerated,
        cash_flows=flows,
        annualized_simple_cost_pct=simple,
        effective_apr_pct=eff,
        nominal_quoted_rate_pct=d,
        is_mock_partner=t["is_mock_partner"],
        assumptions=[
            f"Terms are {d:.0f}/{t['discount_period_days']} net {t['net_terms_days']}; "
            f"acceleration = {t['net_terms_days']} - {t['discount_period_days']} days",
            "Buyer pays on the discount date rather than the net date",
            "The buyer has not been asked; this option depends entirely on their "
            "agreement and CashBridge cannot compel it",
        ],
    )


def build_bridge_facility(
    invoice_amount_usd: float, days_until_due: int, cash_need_usd: float
) -> Facility:
    """
    Unsecured working capital bridge, sized to the cash need.

    Interest accrues on the drawn amount and settles at maturity, so the
    borrower holds the full principal throughout. Its SIMPLE annualised cost
    therefore equals the quoted rate — which is exactly why it must still be
    run through the same machinery rather than assumed: an origination fee or
    upfront interest deduction breaks that equality and the engine must catch
    it. Its EFFECTIVE rate is higher than the quote, because the quote does
    not compound.
    """
    t = FINANCING_PRODUCTS["UNSECURED_BRIDGE"]

    borrow = round(min(cash_need_usd if cash_need_usd > 0 else invoice_amount_usd,
                       invoice_amount_usd), 2)
    origination_fee = round(borrow * (t["origination_fee_pct"] / 100.0), 2)
    interest = round(borrow * (t["nominal_apr_pct"] / 100.0) * (days_until_due / DAYS_PER_YEAR), 2)

    cash_in_hand = round(borrow - origination_fee, 2)
    total_cost = round(interest + origination_fee, 2)

    flows = [
        CashFlowEvent(day=0, amount_usd=cash_in_hand, label="Drawdown net of any fee"),
        CashFlowEvent(
            day=days_until_due,
            amount_usd=-round(borrow + interest, 2),
            label="Principal and interest at maturity",
        ),
    ]
    simple, eff = _both_measures(total_cost, cash_in_hand, days_until_due, flows)

    return Facility(
        facility_id="FAC-C-UNSECURED-BRIDGE",
        provider=t["provider"],
        option_type=t["option_type"],
        pledges_receivable=False,
        gross_advance_usd=borrow,
        upfront_fees_usd=origination_fee,
        cash_in_hand_usd=cash_in_hand,
        deferred_cost_usd=interest,
        total_cost_usd=total_cost,
        reserve_held_usd=0.0,
        days_financed=days_until_due,
        cash_flows=flows,
        annualized_simple_cost_pct=simple,
        effective_apr_pct=eff,
        nominal_quoted_rate_pct=t["nominal_apr_pct"],
        is_mock_partner=t["is_mock_partner"],
        assumptions=[
            "Interest is simple, accrued on the drawn amount, settled at maturity",
            f"No origination fee was quoted (modelled at "
            f"{t['origination_fee_pct']:.2f}%); a real quote raises both rates",
            "Unsecured: the receivable stays unencumbered and can be financed "
            "separately",
            "SIMULATED TERMS — no signed lender exists",
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Wrapping facilities into comparable options
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate_flows(facilities: List[Facility]) -> List[CashFlowEvent]:
    """Merge the facilities' flows by day, so a package has one schedule."""
    by_day: Dict[int, float] = {}
    for f in facilities:
        for ev in f.cash_flows:
            by_day[ev.day] = round(by_day.get(ev.day, 0.0) + ev.amount_usd, 2)
    return [
        CashFlowEvent(day=d, amount_usd=by_day[d], label="Combined net flow")
        for d in sorted(by_day)
    ]


def _option_from_facilities(
    facilities: List[Facility],
    invoice_id: str,
    invoice_amount_usd: float,
    option_id: str,
    option_type: str,
) -> LiquidityOption:
    """Build a comparable option from one or more facilities."""
    total_cash = round(sum(f.cash_in_hand_usd for f in facilities), 2)
    total_cost = round(sum(f.total_cost_usd for f in facilities), 2)
    flows = _aggregate_flows(facilities)

    weighted_days = (
        sum(f.days_financed * f.cash_in_hand_usd for f in facilities) / total_cash
        if total_cash
        else 0
    )
    days = max(1, int(round(weighted_days)))

    simple, eff = _both_measures(total_cost, total_cash, days, flows)

    return LiquidityOption(
        option_id=option_id,
        provider=" + ".join(f.provider for f in facilities),
        option_type=option_type,
        eligible_invoice_id=invoice_id,
        invoice_gross_amount_usd=invoice_amount_usd,
        facilities=facilities,
        advance_rate_pct=round(total_cash / invoice_amount_usd * 100, 2),
        gross_advance_usd=round(sum(f.gross_advance_usd for f in facilities), 2),
        upfront_fees_usd=round(sum(f.upfront_fees_usd for f in facilities), 2),
        cash_in_hand_usd=total_cash,
        deferred_cost_usd=round(sum(f.deferred_cost_usd for f in facilities), 2),
        total_cost_usd=total_cost,
        reserve_held_usd=round(sum(f.reserve_held_usd for f in facilities), 2),
        days_financed=days,
        cash_flows=flows,
        annualized_simple_cost_pct=simple,
        effective_apr_pct=eff,
        nominal_quoted_rate_pct=(
            facilities[0].nominal_quoted_rate_pct if len(facilities) == 1 else None
        ),
        is_mock_partner=any(f.is_mock_partner for f in facilities),
        component_option_ids=[f.facility_id for f in facilities],
        assumptions=[a for f in facilities for a in f.assumptions],
        **_fx_view(total_cash),
    )


def _apply_coverage(opt: LiquidityOption, cash_need_usd: float) -> LiquidityOption:
    """Score an option against the cash gap it is supposed to close."""
    opt.cash_need_usd = round(cash_need_usd, 2)
    if cash_need_usd <= 0:
        opt.covers_need = True
        opt.coverage_pct = 100.0
        opt.residual_gap_usd = 0.0
        return opt
    opt.covers_need = opt.cash_in_hand_usd >= cash_need_usd
    opt.coverage_pct = round(min(opt.cash_in_hand_usd / cash_need_usd, 1.0) * 100, 2)
    opt.residual_gap_usd = round(max(0.0, cash_need_usd - opt.cash_in_hand_usd), 2)
    return opt


def _rank_key(opt: LiquidityOption) -> Tuple:
    """Fit first, then the effective rate, then the simple one as a tiebreak."""
    rate = opt.effective_apr_pct if opt.effective_apr_pct is not None else opt.annualized_simple_cost_pct
    return (not opt.covers_need, rate, opt.residual_gap_usd)


# ─────────────────────────────────────────────────────────────────────────────
# Compatibility and packages
# ─────────────────────────────────────────────────────────────────────────────

# Products whose drawn amount can be sized to the gap.
_FLEXIBLE_TYPES = {"UNSECURED_BRIDGE"}


def check_facility_compatibility(a: Facility, b: Facility) -> Tuple[bool, str]:
    """
    Whether two facilities can run alongside each other on the same invoice.

    Returns:
        (compatible, reason). The reason is carried into the option's cons so
        a rejected pairing is explainable rather than silently absent.

    Note the limit: this checks what CashBridge can see — that two facilities
    do not both take security over the same receivable, and that a buyer
    discount and a factoring assignment are not proposed on the same invoice.
    It does NOT verify either counterparty's actual contract terms. Real
    agreements carry exclusivity, negative pledge and cross-default clauses
    that can forbid a combination this function permits. A proposed package is
    a proposal, never an approved structure.
    """
    if a.pledges_receivable and b.pledges_receivable:
        return False, (
            "Both facilities take security over the same receivable; it can only "
            "be pledged once."
        )
    if {a.option_type, b.option_type} == {"FACTORING", "EARLY_DISCOUNT"}:
        return False, (
            "The buyer cannot settle the invoice early AND have it assigned to a "
            "factor; both consume the same receivable."
        )
    return True, "No conflict visible to CashBridge."


def _build_package(
    parts: List[Facility],
    cash_need_usd: float,
    invoice_id: str,
    invoice_amount_usd: float,
    days_until_due: int,
) -> Optional[LiquidityOption]:
    """
    Combine compatible facilities into a package sized to the gap.

    Fixed-amount products contribute whatever they release. Any flexible
    facility is then drawn for the RESIDUAL only — pooling both at full size
    had the business borrowing far more than the gap and paying for the
    excess. An earlier version offered $119,518 against a $66,350 need.
    """
    if len(parts) < 2:
        return None
    for a, b in combinations(parts, 2):
        ok, _ = check_facility_compatibility(a, b)
        if not ok:
            return None

    fixed = [p for p in parts if p.option_type not in _FLEXIBLE_TYPES]
    flexible = [p for p in parts if p.option_type in _FLEXIBLE_TYPES]

    residual = round(max(0.0, cash_need_usd - sum(p.cash_in_hand_usd for p in fixed)), 2)
    sized: List[Facility] = list(fixed)
    for _ in flexible:
        if residual <= 0:
            continue  # The fixed products already close the gap.
        resized = build_bridge_facility(invoice_amount_usd, days_until_due, residual)
        sized.append(resized)
        residual = round(max(0.0, residual - resized.cash_in_hand_usd), 2)

    if len(sized) < 2:
        return None

    option = _option_from_facilities(
        sized,
        invoice_id,
        invoice_amount_usd,
        option_id="PKG-" + "+".join(p.option_type[:4] for p in sized),
        option_type="COMBINATION",
    )
    option.pros = [
        f"Pooled cash of ${option.cash_in_hand_usd:,.2f} closes a gap no single "
        f"product covers",
        "The flexible facility is drawn only for the residual, so no interest is "
        "paid on cash the business does not need",
    ]
    option.cons = [
        f"{len(sized)} separate agreements with {len(set(p.provider for p in sized))} "
        f"counterparties; either can decline and leave the gap open",
        "Two sets of conditions precedent, covenants and drawdown timetables",
        "No counterparty has confirmed it will lend alongside the other",
    ]
    option.assumptions += [
        "Blended figures pool the facilities' dated cash flows; the effective "
        "rate is solved on the combined schedule",
        "Fixed-amount products contribute what they release; any flexible "
        "facility is sized to the residual gap only",
        "Compatibility is checked only for conflicts CashBridge can see. "
        "Exclusivity, negative-pledge and cross-default clauses in the real "
        "agreements have NOT been reviewed.",
    ]
    return _apply_coverage(option, cash_need_usd)


def _write_verdicts(options: List[LiquidityOption], cash_need_usd: float) -> None:
    """Attach a verdict naming the trade-off, not just the ranking position."""
    covering = [o for o in options if o.covers_need]
    for opt in options:
        rate = opt.effective_apr_pct or opt.annualized_simple_cost_pct
        if opt.rank == 1 and opt.covers_need:
            opt.recommendation_verdict = (
                f"RECOMMENDED: lowest effective rate ({rate:.2f}%) among the "
                f"options that close the ${cash_need_usd:,.2f} gap."
            )
        elif opt.covers_need:
            cheapest = covering[0]
            delta = opt.total_cost_usd - cheapest.total_cost_usd
            opt.recommendation_verdict = (
                f"VIABLE: closes the gap but costs ${delta:,.2f} more than "
                f"{cheapest.option_id} over a comparable term."
            )
        else:
            opt.recommendation_verdict = (
                f"INSUFFICIENT ALONE: releases ${opt.cash_in_hand_usd:,.2f} against "
                f"a ${cash_need_usd:,.2f} need, leaving ${opt.residual_gap_usd:,.2f} "
                f"uncovered. Cheap capital that does not close the gap does not "
                f"prevent the shortfall."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_liquidity_options(
    invoice_id: str,
    invoice_amount_usd: float,
    days_until_due: int,
    cash_need_usd: float = 0.0,
    include_combinations: bool = True,
) -> List[LiquidityOption]:
    """
    Evaluate every financing option for one verified invoice on a single basis.

    Args:
        invoice_id: Invoice offered for financing.
        invoice_amount_usd: Face value in USD.
        days_until_due: Days until the buyer's payment is due.
        cash_need_usd: The gap the financing must close. Take this from
            `ForecastSummary.peak_funding_need_usd` — the trough of the cash
            curve, not the first week that dips.
        include_combinations: Build packages when no single product closes it.

    Returns:
        Options ranked by (closes the need, then effective APR). Each carries
        its facilities, dated cash flows, both cost measures, its assumptions
        and whether its terms are simulated.

    Raises:
        ValueError: On non-positive invoice amount or days.
    """
    if invoice_amount_usd <= 0:
        raise ValueError("invoice_amount_usd must be positive.")
    if days_until_due <= 0:
        raise ValueError("days_until_due must be positive.")

    request_permission(
        PermissionLevel.L1_ANALYZE,
        "EVALUATE_LIQUIDITY_OPTIONS",
        invoice_id,
        details={
            "invoice_amount_usd": invoice_amount_usd,
            "days_until_due": days_until_due,
            "cash_need_usd": cash_need_usd,
        },
    )

    facilities = [
        build_factoring_facility(invoice_amount_usd, days_until_due),
        build_early_discount_facility(invoice_amount_usd, days_until_due),
        build_bridge_facility(invoice_amount_usd, days_until_due, cash_need_usd),
    ]

    singles = []
    for f, oid in zip(facilities, ("OPT-A-WEBANK-FACTORING", "OPT-B-EARLY-DISCOUNT",
                                   "OPT-C-UNSECURED-BRIDGE")):
        opt = _option_from_facilities(
            [f], invoice_id, invoice_amount_usd, oid, f.option_type
        )
        _apply_coverage(opt, cash_need_usd)
        singles.append(opt)

    _attach_single_commentary(singles)
    options = list(singles)

    if include_combinations and cash_need_usd > 0 and not any(o.covers_need for o in singles):
        for r in (2, 3):
            for parts in combinations(facilities, r):
                pkg = _build_package(
                    list(parts), cash_need_usd, invoice_id, invoice_amount_usd, days_until_due
                )
                if pkg is not None and pkg.covers_need:
                    options.append(pkg)

    options.sort(key=_rank_key)
    for idx, opt in enumerate(options, start=1):
        opt.rank = idx
    _write_verdicts(options, cash_need_usd)
    return options


def _attach_single_commentary(singles: List[LiquidityOption]) -> None:
    """Pros and cons for the single-product options."""
    for o in singles:
        f = o.facilities[0]
        if f.option_type == "FACTORING":
            o.pros = [
                "No real estate collateral required",
                "Advance typically available within 24-48 hours of approval",
            ]
            o.cons = [
                f"Only {f.gross_advance_usd / o.invoice_gross_amount_usd * 100:.0f}% of "
                f"face value is advanced; ${f.reserve_held_usd:,.2f} is held in reserve "
                f"until the buyer pays",
                f"Fees of ${f.total_cost_usd:,.2f} are deducted at drawdown, so cash "
                f"received is ${f.cash_in_hand_usd:,.2f}, not ${f.gross_advance_usd:,.2f}",
                "Buyer must be notified and approve the assignment",
            ]
        elif f.option_type == "EARLY_DISCOUNT":
            o.pros = [
                "No lender, no credit application, no new debt on the balance sheet",
                f"Releases ${f.cash_in_hand_usd:,.2f} — the largest cash amount of "
                f"the single-product options",
            ]
            o.cons = [
                f"A {f.nominal_quoted_rate_pct}% discount over {f.days_financed} days "
                f"is an effective {o.effective_apr_pct:.2f}% a year",
                "Depends entirely on the buyer agreeing",
                "Repeated use trains the buyer to expect the discount as standard",
            ]
        else:
            o.pros = [
                "Drawn amount is sized to the actual gap, not to an invoice value",
                "Receivable stays unencumbered and can still be factored",
            ]
            o.cons = [
                f"Highest effective rate of the single products at "
                f"{o.effective_apr_pct:.2f}%",
                "Adds a debt obligation and usually requires a credit decision",
            ]


def summarise_comparison(options: List[LiquidityOption]) -> Dict[str, Any]:
    """
    Machine-readable summary for the UI and the funding pack.

    Reports whether ANY option closes the gap. A comparison table that
    silently presents the cheapest of three insufficient options is how an SME
    ends up underfunded with a signed facility agreement.
    """
    covering = [o for o in options if o.covers_need]
    best = options[0] if options else None
    recommended = best if best and best.covers_need else None
    return {
        "options_evaluated": len(options),
        "options_that_close_the_gap": len(covering),
        "gap_can_be_closed": bool(covering),
        "recommended_option_id": recommended.option_id if recommended else None,
        "recommended_effective_apr_pct": recommended.effective_apr_pct if recommended else None,
        "recommended_simple_cost_pct": (
            recommended.annualized_simple_cost_pct if recommended else None
        ),
        "recommended_facility_count": len(recommended.facilities) if recommended else 0,
        "cash_need_usd": best.cash_need_usd if best else 0.0,
        "largest_single_advance_usd": max(
            (o.cash_in_hand_usd for o in options if o.option_type != "COMBINATION"),
            default=0.0,
        ),
        "contains_simulated_terms": any(o.is_mock_partner for o in options),
        "rate_basis_note": (
            "effective_apr_pct is the IRR of the facility's dated cash flows, "
            "actual/365, compounded annually. annualized_simple_cost_pct is "
            "cost over cash received scaled linearly to a year and does not "
            "compound. Both are reported; the ranking uses the effective rate."
        ),
        "disclaimer": (
            "Eligibility shown here is CashBridge's own pre-screen. It is not a "
            "credit decision: a funder may still decline on buyer, country, goods "
            "or contract grounds, and an accepted pack is not a disbursed facility. "
            "Package options are proposals; no counterparty has agreed to lend "
            "alongside another."
        ),
    }
