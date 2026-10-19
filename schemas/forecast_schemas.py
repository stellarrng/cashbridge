"""Pydantic v2 models for forecasting, scenarios and the liquidity menu.

Money fields are ``Decimal`` in USD with cent precision. ``to_contract`` turns any
model into the plain JSON shape the UI contract uses (Decimals become numbers).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from config.settings import (
    FORECAST_WEEKS,
    MIN_CASH_BUFFER_USD,
    SCENARIO_TARIFF_RATE_PCT,
)
from schemas.document_schemas import Money

WeekStatus = Literal["ok", "at_risk", "shortfall"]


def to_contract(value: Any) -> Any:
    """Convert models, Decimals and dates into plain JSON-compatible values."""
    if isinstance(value, BaseModel):
        return {k: to_contract(v) for k, v in value.model_dump().items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_contract(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_contract(v) for v in value]
    return value


class CCCMetrics(BaseModel):
    """Cash conversion cycle components in days."""

    dio: float
    dso: float
    dpo: float
    ccc: float


class LedgerSnapshot(BaseModel):
    """Period totals from which DIO, DSO and DPO are computed."""

    period_days: int = Field(gt=0)
    revenue_usd: Decimal = Field(gt=0)
    cogs_usd: Decimal = Field(gt=0)
    avg_inventory_usd: Decimal = Field(ge=0)
    avg_receivables_usd: Decimal = Field(ge=0)
    avg_payables_usd: Decimal = Field(ge=0)


class OpenReceivable(BaseModel):
    """An unpaid export invoice with the probability it is paid on time."""

    invoice_id: str
    buyer_id: str
    buyer_name: str
    market: str
    amount: Money
    due_date: date
    p_on_time: float = Field(ge=0.0, le=1.0)
    promised_date: Optional[date] = Field(
        default=None, description="Buyer's dated promise to pay; the full amount lands on that date"
    )


class DepositPlan(BaseModel):
    """A supplier deposit: ``po_value_usd`` times ``pct`` paid in a given week."""

    ref: str
    week: int = Field(ge=1, le=FORECAST_WEEKS)
    po_value_usd: Decimal = Field(gt=0)
    pct: Decimal = Field(ge=0, le=100)
    adjustable: bool = Field(default=False, description="True if the deposit_pct what-if control applies")


class ScenarioParams(BaseModel):
    """What-if controls. Field names match the UI contract ``scenario_controls``."""

    dso_change_days: int = Field(default=0, ge=-30, le=30)
    deposit_pct: float = Field(default=30, ge=0, le=50)
    tariff_shared_pct: float = Field(default=0, ge=0, le=100)
    fx_change_pct: float = Field(default=0, ge=-5, le=5)


class ForecastInputs(BaseModel):
    """Everything the 13-week model needs. Scenario adjustments default to none."""

    start_date: date
    opening_cash_usd: Decimal
    buffer_usd: Decimal = MIN_CASH_BUFFER_USD
    receivables: List[OpenReceivable] = Field(default_factory=list)
    weekly_fixed_costs_usd: Decimal = Decimal("0")
    payroll_usd: Decimal = Decimal("0")
    deposits: List[DepositPlan] = Field(default_factory=list)
    # Scenario adjustments (set by simulate, zero in the base case)
    dso_shift_days: int = 0
    fx_change_pct: Decimal = Decimal("0")
    tariff_shared_pct: Decimal = Decimal("0")
    tariff_rate_pct: Decimal = SCENARIO_TARIFF_RATE_PCT


class WeeklyCashRow(BaseModel):
    """One forecast week. Names match the UI contract ``forecast.weeks``."""

    week: int
    start_date: date
    opening: Decimal
    inflows: Decimal
    outflows: Decimal
    closing: Decimal
    status: WeekStatus


class ShortfallAttribution(BaseModel):
    """One driver of the first shortfall. Amounts add up to the shortfall."""

    driver: str
    amount_usd: Decimal
    source_ref: str


class ForecastResult(BaseModel):
    """The 13-week forecast with its first shortfall and attribution."""

    buffer_usd: Decimal
    weeks: List[WeeklyCashRow]
    first_shortfall_week: Optional[int] = None
    shortfall_usd: Optional[Decimal] = None
    min_closing_usd: Decimal
    attribution: List[ShortfallAttribution] = Field(default_factory=list)


class ScenarioDelta(BaseModel):
    """Before/after comparison. Names match the UI contract ``simulate().delta``."""

    first_shortfall_week_before: Optional[int]
    first_shortfall_week_after: Optional[int]
    min_closing_before_usd: Decimal
    min_closing_after_usd: Decimal


class ScenarioResult(BaseModel):
    """Output of ``simulate``: the new forecast and how it differs from the base."""

    forecast: ForecastResult
    delta: ScenarioDelta


class FxExposure(BaseModel):
    """Foreign-currency inflow in a week and the effect of a rate move. Warning only."""

    week: int
    foreign_inflow_usd: Decimal
    impact_up_usd: Decimal
    impact_down_usd: Decimal
    impact_up_vnd: Decimal
    impact_down_vnd: Decimal


class LiquidityOption(BaseModel):
    """One funding option. Names match the UI contract ``funding_options``."""

    rank: Optional[int] = None
    id: str
    name: str
    type: Literal["factoring", "loan", "discount", "overdraft"]
    amount_usd: Optional[Decimal] = None
    apr_pct: Optional[float] = None
    eligible: bool
    ineligible_reason: Optional[str] = None
    cost_breakdown: Dict[str, Decimal] = Field(default_factory=dict)
    assumptions: Dict[str, Any] = Field(default_factory=dict)
    formula: Optional[str] = None
    why_not_cheaper: Optional[str] = None
