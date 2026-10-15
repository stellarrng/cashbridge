"""
Pydantic v2 schemas for Cash Conversion Cycle (CCC), 13-week cash flow forecasts
and liquidity option comparison.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field

from config.settings import FORECAST_WEEKS


class CCCMetrics(BaseModel):
    dio_days: float = Field(..., description="Days Inventory Outstanding")
    dso_days: float = Field(..., description="Days Sales Outstanding")
    dpo_days: float = Field(..., description="Days Payables Outstanding")
    ccc_days: float = Field(..., description="Cash Conversion Cycle: DIO + DSO - DPO")
    industry_benchmark_days: float = 65.0
    liquidity_drag_commentary: str = ""


class WeeklyCashRow(BaseModel):
    week: int = Field(ge=1, le=FORECAST_WEEKS)
    week_label: str = Field(..., description="e.g. 'W1 (Oct 16)'")
    opening_cash: float
    ar_inflows: float = 0.0
    fixed_opex: float = 12500.0
    supplier_deposits: float = 0.0
    financing_inflows: float = 0.0
    financing_repayments: float = 0.0
    net_cash_flow: float
    closing_cash: float
    is_critical_shortfall: bool = Field(
        default=False, description="Closing cash below zero"
    )
    is_below_buffer: bool = Field(
        default=False, description="Closing cash below the minimum operating buffer"
    )
    inflow_invoices: List[str] = Field(default_factory=list)
    outflow_notes: Optional[str] = None


class ForecastSummary(BaseModel):
    company_name: str
    starting_cash: float
    total_projected_inflows: float
    total_projected_outflows: float

    # Deficit geometry. `lowest_cash_week` is the TROUGH of the cumulative cash
    # curve, which is the week that sizes the facility — not merely the first
    # week that happens to go negative.
    first_shortfall_week: Optional[int] = Field(
        default=None, description="First week closing cash goes below zero"
    )
    lowest_cash_week: Optional[int] = None
    lowest_cash_balance: float
    weeks_in_deficit: List[int] = Field(default_factory=list)
    deficit_duration_weeks: int = 0
    ends_period_in_deficit: bool = False

    shortfall_detected: bool = False
    minimum_cash_buffer: float = 0.0

    # Peak funding need = how much cash must be injected (and held) so that no
    # week in the horizon closes below the buffer. Sizing to the first dip only
    # underfunds a multi-week trough.
    peak_funding_need_usd: float = 0.0
    funding_needed_by_week: Optional[int] = None

    weekly_breakdown: List[WeeklyCashRow] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    data_provenance: str = "SYNTHETIC_SANDBOX"


class CashFlowEvent(BaseModel):
    """
    One dated cash movement, from the borrower's point of view.

    Positive is cash into the business, negative is cash out. `day` is days
    from drawdown. These are what `effective_apr_pct` is solved against, so
    a product with fees at several dates, a reserve released at maturity, or
    interest at a different time from principal is modelled rather than
    averaged.
    """

    day: int = Field(..., description="Days from drawdown (day 0)")
    amount_usd: float = Field(..., description="Positive = received, negative = paid")
    label: str = ""


class Facility(BaseModel):
    """
    A single funding line from a single counterparty.

    A combined package is two facilities, not one blended product: two
    agreements, two sets of conditions precedent, two counterparties who can
    each decline. The previous model collapsed a package into one `provider`
    string and one advance figure, which hid that — and caused the demo to
    register a two-funder package in the pledge registry as a single pledge.
    """

    facility_id: str
    provider: str
    option_type: str = Field(
        ..., description="'FACTORING' | 'EARLY_DISCOUNT' | 'UNSECURED_BRIDGE'"
    )
    pledges_receivable: bool = Field(
        ...,
        description="Whether this facility takes security over the invoice. Only "
        "a facility that does belongs in the anti-double-financing registry, "
        "and two such facilities on one invoice cannot be combined.",
    )
    gross_advance_usd: float
    upfront_fees_usd: float = 0.0
    cash_in_hand_usd: float
    deferred_cost_usd: float = 0.0
    total_cost_usd: float
    reserve_held_usd: float = 0.0
    days_financed: int
    cash_flows: List[CashFlowEvent] = Field(default_factory=list)
    annualized_simple_cost_pct: float
    effective_apr_pct: Optional[float] = None
    nominal_quoted_rate_pct: Optional[float] = None
    is_mock_partner: bool = False
    assumptions: List[str] = Field(default_factory=list)


class LiquidityOption(BaseModel):
    """
    One financing option, stated on a basis that is comparable across products.

    TWO COST MEASURES, both reported, because they answer different questions
    and conflating them is how a comparison table misleads:

      annualized_simple_cost_pct
          total cost / cash received, scaled to a year linearly:
              (total_cost / cash_in_hand) x (365 / days) x 100
          Simple to audit and the convention behind the familiar "2/10 net 30
          is about 36% a year" figure. It does NOT compound, and it collapses
          everything to a single term, so for a product with payments at
          several dates it is an approximation, not an APR.

      effective_apr_pct
          the annual rate that discounts the facility's actual dated cash
          flows to zero (an IRR). This is the measure that survives a product
          with staged fees, a reserve released at maturity, or interest paid
          on a different date from principal.

    Ranking uses the effective rate. An earlier version reported the simple
    figure under the name `apr_pct`, which overstates how standardised the
    comparison was.

    `cash_in_hand_usd` is cash the business can actually spend at drawdown —
    after upfront fees, discounts and holdbacks. Comparing a fee-inclusive
    product against a fee-exclusive one on headline rate alone is the single
    most common error in cost-of-capital comparisons.
    """

    option_id: str
    provider: str
    option_type: str = Field(
        ..., description="'FACTORING' | 'EARLY_DISCOUNT' | 'UNSECURED_BRIDGE' | 'COMBINATION'"
    )
    eligible_invoice_id: str
    invoice_gross_amount_usd: float
    facilities: List[Facility] = Field(
        default_factory=list,
        description="The individual funding lines. One for a single product, "
        "two or more for a package. Each has its own counterparty.",
    )

    # ── Same-basis economics ──────────────────────────────────────────────
    advance_rate_pct: float = Field(..., description="% of face value advanced")
    gross_advance_usd: float = Field(..., description="Advance before fees")
    upfront_fees_usd: float = 0.0
    cash_in_hand_usd: float = Field(..., description="Spendable cash at drawdown")
    deferred_cost_usd: float = Field(
        default=0.0, description="Cost paid at maturity rather than upfront"
    )
    total_cost_usd: float = Field(..., description="Upfront + deferred cost")
    reserve_held_usd: float = Field(
        default=0.0, description="Holdback returned only when the buyer pays"
    )
    days_financed: int
    cash_flows: List[CashFlowEvent] = Field(
        default_factory=list, description="Dated flows the effective APR is solved against"
    )
    annualized_simple_cost_pct: float = Field(
        ..., description="Linear annualisation of cost over cash received"
    )
    effective_apr_pct: Optional[float] = Field(
        default=None, description="IRR of the dated cash flows, annualised"
    )
    apr_basis: str = Field(
        default="EFFECTIVE_IRR",
        description="Which measure drives the ranking",
    )
    nominal_quoted_rate_pct: Optional[float] = Field(
        default=None, description="Lender's headline rate, for contrast"
    )

    # ── Fit against the actual cash need ──────────────────────────────────
    cash_need_usd: float = 0.0
    covers_need: bool = False
    coverage_pct: float = 0.0
    residual_gap_usd: float = 0.0

    # ── Optional settlement-currency view ─────────────────────────────────
    net_cash_realized_vnd: Optional[float] = None
    fx_cost_usd: Optional[float] = None

    rank: int = 0
    eligibility_status: str = Field(
        default="ELIGIBLE",
        description="'ELIGIBLE' | 'REVIEW_REQUIRED' | 'INELIGIBLE'",
    )
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    is_mock_partner: bool = Field(
        default=False, description="Terms are simulated; no signed funding partner"
    )
    recommendation_verdict: str = ""
    component_option_ids: List[str] = Field(
        default_factory=list, description="Populated for COMBINATION options"
    )


class SimulationScenario(BaseModel):
    delay_buyer: Optional[str] = None
    delay_weeks: int = Field(default=0, ge=0, le=4)
    financed_invoice_id: Optional[str] = None
    advance_rate_override: Optional[float] = None
