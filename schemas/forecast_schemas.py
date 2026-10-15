"""
Pydantic v2 schemas for Cash Conversion Cycle (CCC), 13-Week Cash Flow Forecasts,
and Liquidity APR Rankings.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class CCCMetrics(BaseModel):
    dio_days: float = Field(..., description="Days Inventory Outstanding")
    dso_days: float = Field(..., description="Days Sales Outstanding")
    dpo_days: float = Field(..., description="Days Payables Outstanding")
    ccc_days: float = Field(..., description="Cash Conversion Cycle: DIO + DSO - DPO")
    industry_benchmark_days: float = 65.0
    liquidity_drag_commentary: str = ""


class WeeklyCashRow(BaseModel):
    week: int = Field(ge=1, le=13, description="Week number 1 to 13")
    week_label: str = Field(..., description="e.g. 'W1 (Oct 16)'")
    opening_cash: float
    ar_inflows: float = 0.0
    fixed_opex: float = 12500.0
    supplier_deposits: float = 0.0
    net_cash_flow: float
    closing_cash: float
    is_critical_shortfall: bool = False
    inflow_invoices: List[str] = Field(default_factory=list)
    outflow_notes: Optional[str] = None


class ForecastSummary(BaseModel):
    company_name: str
    starting_cash: float
    total_projected_inflows: float
    total_projected_outflows: float
    lowest_cash_week: int
    lowest_cash_balance: float
    shortfall_detected: bool
    recommended_financing_amount: float
    weekly_breakdown: List[WeeklyCashRow]


class LiquidityOption(BaseModel):
    option_id: str
    provider: str
    option_type: str = Field(..., description="'FACTORING' | 'EARLY_DISCOUNT' | 'UNSECURED_BRIDGE'")
    eligible_invoice_id: str
    invoice_gross_amount_usd: float
    advance_rate_pct: float
    immediate_cash_advance_usd: float
    total_fee_cost_usd: float
    net_cash_realized_usd: float
    days_accelerated: int
    apr_pct: float = Field(..., description="Deterministic True Annualized Percentage Rate")
    rank: int = 1
    covers_shortfall: bool = True
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    recommendation_verdict: str = ""


class SimulationScenario(BaseModel):
    delay_buyer: Optional[str] = None
    delay_weeks: int = Field(default=0, ge=0, le=4)
    financed_invoice_id: Optional[str] = None
    advance_rate_override: Optional[float] = None
