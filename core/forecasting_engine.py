"""
Forecasting Engine — Deterministic 13-Week Direct Cash Flow Model & CCC Calculator.

Rules:
 - All arithmetic is performed by this pure Python module only (NO LLM calculations).
 - Seed data produces a deterministic Week 6 critical shortfall of -$31,350.00.
 - What-If simulator allows toggling buyer delays (0–4 weeks) and financing.
"""

from typing import Optional
from datetime import date, timedelta

from config.settings import (
    DEFAULT_COMPANY,
    FORECAST_WEEKS,
    DEFAULT_WEEK_3_SUPPLIER_DEPOSIT,
    DEFAULT_WEEK_6_SUPPLIER_DEPOSIT,
)
from schemas.forecast_schemas import (
    CCCMetrics,
    WeeklyCashRow,
    ForecastSummary,
    SimulationScenario,
)

# ─────────────────────────────────────────────────────────────────────────────
# Default Seed Receivable Schedule
# AR inflow amounts and their nominal due week (before any buyer delay)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_AR_SCHEDULE = [
    # (invoice_id, due_week, usd_amount, buyer_name)
    # AR inflows are calibrated so Week 6 closing cash = exactly -$31,350 (deterministic spec)
    # W6: opening(36,150) - OPEX(12,500) - supplier_deposit(55,000) = -31,350
    # W5_close = W6_open = 36,150  =>  W4_close(24,000) + AR_W5(24,650) - OPEX(12,500) = 36,150
    ("INV-2026-101", 2,  20000.00, "Nordic Home Retail (US)"),
    ("INV-2026-102", 4,  30000.00, "Nordic Home Retail (US)"),
    ("INV-2026-JPY", 5,  24650.00, "Sakura Furniture Co. (JP)"),  # JPY partial — bridges W5→W6 opening
    ("INV-2026-103", 9,  65000.00, "Nordic Home Retail (US)"),  # Key 60-day DSO invoice
    ("INV-2026-104", 11, 42000.00, "Sakura Furniture Co. (JP)"),
]


def calculate_ccc(
    dio_days: float = DEFAULT_COMPANY["dio_days"],
    dso_days: float = DEFAULT_COMPANY["dso_days"],
    dpo_days: float = DEFAULT_COMPANY["dpo_days"],
) -> CCCMetrics:
    """
    Calculate the Cash Conversion Cycle.

    CCC = DIO + DSO - DPO
    Default: 38 + 68 - 24 = 82 days

    Args:
        dio_days: Days Inventory Outstanding (default 38).
        dso_days: Days Sales Outstanding (default 68).
        dpo_days: Days Payables Outstanding (default 24).

    Returns:
        CCCMetrics Pydantic model with all fields populated.
    """
    ccc = dio_days + dso_days - dpo_days
    drag = ccc - 65.0  # vs. industry benchmark of 65 days
    commentary = (
        f"CCC of {ccc:.0f} days is {drag:+.0f} days vs. the 65-day industry benchmark. "
        f"Cash is locked for ~{ccc:.0f} days before a sale becomes a cash receipt."
    )
    return CCCMetrics(
        dio_days=dio_days,
        dso_days=dso_days,
        dpo_days=dpo_days,
        ccc_days=ccc,
        industry_benchmark_days=65.0,
        liquidity_drag_commentary=commentary,
    )


def run_13_week_forecast(
    opening_cash: float = DEFAULT_COMPANY["opening_cash_week_1"],
    fixed_weekly_opex: float = DEFAULT_COMPANY["fixed_weekly_opex"],
    ar_schedule: Optional[list] = None,
    week_3_supplier_deposit: float = DEFAULT_WEEK_3_SUPPLIER_DEPOSIT,
    week_6_supplier_deposit: float = DEFAULT_WEEK_6_SUPPLIER_DEPOSIT,
    financed_invoice_id: Optional[str] = None,
    financing_advance_usd: float = 0.0,
    financing_week: int = 5,
) -> ForecastSummary:
    """
    Run the 13-week direct cash flow model for Pacific Timber & Garment Exports Ltd.

    Produces a deterministic Week 6 critical shortfall of -$31,350.00 under default
    parameters (before any financing is applied).

    Args:
        opening_cash: Starting cash balance in USD (default $42,000).
        fixed_weekly_opex: Fixed weekly operating expenses (default $12,500).
        ar_schedule: List of (invoice_id, due_week, amount, buyer) tuples.
                     Defaults to DEFAULT_AR_SCHEDULE.
        week_3_supplier_deposit: Supplier deposit outflow in Week 3 (default $18,000).
        week_6_supplier_deposit: Supplier deposit outflow in Week 6 (default $55,000).
        financed_invoice_id: If set, adds financing advance at financing_week.
        financing_advance_usd: Cash advance amount from financing.
        financing_week: Week the financing advance is received (default 5, before W6 outflow).

    Returns:
        ForecastSummary with the full 13-week breakdown.
    """
    schedule = ar_schedule if ar_schedule is not None else list(DEFAULT_AR_SCHEDULE)

    # Build AR inflow lookup: week -> (total_usd, [invoice_ids])
    ar_by_week: dict[int, dict] = {w: {"amount": 0.0, "invoices": []} for w in range(1, FORECAST_WEEKS + 1)}
    for inv_id, due_week, amount, buyer in schedule:
        if 1 <= due_week <= FORECAST_WEEKS:
            ar_by_week[due_week]["amount"] += amount
            ar_by_week[due_week]["invoices"].append(inv_id)

    # Add financing advance as an inflow at the specified week
    if financed_invoice_id and financing_advance_usd > 0 and 1 <= financing_week <= FORECAST_WEEKS:
        ar_by_week[financing_week]["amount"] += financing_advance_usd
        ar_by_week[financing_week]["invoices"].append(f"{financed_invoice_id}[FINANCED]")

    rows: list[WeeklyCashRow] = []
    current_cash = opening_cash
    start_date = date(2026, 10, 16)

    for week_num in range(1, FORECAST_WEEKS + 1):
        week_start = start_date + timedelta(weeks=week_num - 1)
        week_label = f"W{week_num} ({week_start.strftime('%b %d')})"

        ar_inflows = ar_by_week[week_num]["amount"]
        inflow_invoices = ar_by_week[week_num]["invoices"]

        # Supplier deposit outflows
        supplier_deposit = 0.0
        outflow_note = None
        if week_num == 3:
            supplier_deposit = week_3_supplier_deposit
            outflow_note = "Timber raw material supplier deposit (Week 3)"
        elif week_num == 6:
            supplier_deposit = week_6_supplier_deposit
            outflow_note = "Textile mill + timber bulk deposit (Week 6)"

        net_cash_flow = ar_inflows - fixed_weekly_opex - supplier_deposit
        closing_cash = current_cash + net_cash_flow
        is_critical = closing_cash < 0

        row = WeeklyCashRow(
            week=week_num,
            week_label=week_label,
            opening_cash=round(current_cash, 2),
            ar_inflows=round(ar_inflows, 2),
            fixed_opex=fixed_weekly_opex,
            supplier_deposits=supplier_deposit,
            net_cash_flow=round(net_cash_flow, 2),
            closing_cash=round(closing_cash, 2),
            is_critical_shortfall=is_critical,
            inflow_invoices=inflow_invoices,
            outflow_notes=outflow_note,
        )
        rows.append(row)
        current_cash = closing_cash

    # Summary metrics
    lowest_week = min(rows, key=lambda r: r.closing_cash)
    total_inflows = sum(r.ar_inflows for r in rows)
    total_outflows = sum(r.fixed_opex + r.supplier_deposits for r in rows)
    shortfall_detected = lowest_week.closing_cash < 0
    recommended_financing = abs(lowest_week.closing_cash) if shortfall_detected else 0.0

    return ForecastSummary(
        company_name=DEFAULT_COMPANY["name"],
        starting_cash=opening_cash,
        total_projected_inflows=round(total_inflows, 2),
        total_projected_outflows=round(total_outflows, 2),
        lowest_cash_week=lowest_week.week,
        lowest_cash_balance=lowest_week.closing_cash,
        shortfall_detected=shortfall_detected,
        recommended_financing_amount=round(recommended_financing, 2),
        weekly_breakdown=rows,
    )


def simulate_forecast(
    delay_buyer: Optional[str] = None,
    delay_weeks: int = 0,
    financed_invoice_id: Optional[str] = None,
    financing_advance_usd: float = 0.0,
    financing_week: int = 5,
) -> ForecastSummary:
    """
    What-If Scenario Simulator: re-run the 13-week forecast with buyer payment delays
    and/or invoice financing toggled on.

    Args:
        delay_buyer: Buyer name substring to delay (e.g. 'Nordic'). None = no delay.
        delay_weeks: Number of weeks to shift the buyer's invoice due dates (0–4).
        financed_invoice_id: Invoice ID receiving a financing advance (e.g. 'INV-2026-103').
        financing_advance_usd: USD advance amount from factoring.
        financing_week: Week the advance is deposited (default Week 5, before Week 6 crunch).

    Returns:
        Updated ForecastSummary reflecting the scenario changes.
    """
    schedule = list(DEFAULT_AR_SCHEDULE)

    if delay_buyer and delay_weeks > 0:
        updated_schedule = []
        for inv_id, due_week, amount, buyer in schedule:
            if delay_buyer.lower() in buyer.lower():
                new_week = min(due_week + delay_weeks, FORECAST_WEEKS)
                updated_schedule.append((inv_id, new_week, amount, buyer))
            else:
                updated_schedule.append((inv_id, due_week, amount, buyer))
        schedule = updated_schedule

    return run_13_week_forecast(
        ar_schedule=schedule,
        financed_invoice_id=financed_invoice_id,
        financing_advance_usd=financing_advance_usd,
        financing_week=financing_week,
    )
