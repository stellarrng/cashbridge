"""
Forecasting Engine — deterministic 13-week direct cash flow model and CCC.

WHAT CHANGED AND WHY
--------------------
The previous version computed the weekly rows correctly but then drew the wrong
conclusion from them, and the docstrings, README and demo narrative all
inherited that error.

Running the default seed schedule gives:

    W1  29,500   W2  37,000   W3   6,500   W4  24,000   W5  36,150
    W6 -31,350   W7 -43,850   W8 -56,350   W9  -3,850   W10 -16,350
    W11 13,150   W12    650   W13 -11,850

Week 6 is where the balance FIRST goes negative. The TROUGH is week 8 at
-$56,350, and the business is underwater for five consecutive weeks (6-10) and
again in week 13. The old code reported `recommended_financing_amount =
abs(lowest_cash_balance)`, which happened to read the right row, but every
docstring, the README and the funding narrative described "a Week 6 shortfall
of $31,350" and then proposed an $55,250 factoring advance to cover it.

That advance does not cover it. Net of fees it releases $54,518, against a
trough of $56,350 before any operating buffer. The headline demo claim was
arithmetically false.

This module now reports the deficit's full geometry — first week, trough week,
duration, whether the horizon ends in deficit — and sizes the facility against
the trough plus a minimum operating buffer, because financing calculated to
return the balance to exactly zero leaves a business with no float and is not
a fundable plan.

ALL ARITHMETIC IS PURE PYTHON. No LLM performs any calculation in this module.
"""

from typing import Optional, List, Tuple
from datetime import date, timedelta

from config.settings import (
    DEFAULT_COMPANY,
    FORECAST_WEEKS,
    DEFAULT_WEEK_3_SUPPLIER_DEPOSIT,
    DEFAULT_WEEK_6_SUPPLIER_DEPOSIT,
    MINIMUM_CASH_BUFFER_USD,
)
from schemas.forecast_schemas import (
    CCCMetrics,
    WeeklyCashRow,
    ForecastSummary,
)

# ─────────────────────────────────────────────────────────────────────────────
# Default seed receivable schedule (SYNTHETIC — not customer data)
# (invoice_id, due_week, usd_amount, buyer_name)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_AR_SCHEDULE = [
    ("INV-2026-101", 2, 20000.00, "Nordic Home Retail (US)"),
    ("INV-2026-102", 4, 30000.00, "Nordic Home Retail (US)"),
    ("INV-2026-JPY", 5, 24650.00, "Sakura Furniture Co. (JP)"),
    ("INV-2026-103", 9, 65000.00, "Nordic Home Retail (US)"),
    ("INV-2026-104", 11, 42000.00, "Sakura Furniture Co. (JP)"),
]

FORECAST_ASSUMPTIONS = [
    "SYNTHETIC DATA: figures describe a sandbox company, not a real customer.",
    "Every buyer pays in full on the scheduled week; no probability of late "
    "payment is applied. Use simulate_forecast() to test delay scenarios.",
    "Operating expenses are flat at the weekly figure; no seasonality, payroll "
    "cycles, tax payments or capex are modelled.",
    "FX is converted at frozen sandbox rates, not a live feed.",
    "No credit line, overdraft or existing debt service is included.",
    "This is a projection under stated assumptions, not a validated forecast: "
    "no out-of-sample error (MAE/WAPE) has been measured, because there is no "
    "historical payment data behind it.",
]


def calculate_ccc(
    dio_days: float = DEFAULT_COMPANY["dio_days"],
    dso_days: float = DEFAULT_COMPANY["dso_days"],
    dpo_days: float = DEFAULT_COMPANY["dpo_days"],
) -> CCCMetrics:
    """
    Calculate the Cash Conversion Cycle: CCC = DIO + DSO - DPO.

    Default sandbox company: 38 + 68 - 24 = 82 days.

    Args:
        dio_days: Days Inventory Outstanding.
        dso_days: Days Sales Outstanding.
        dpo_days: Days Payables Outstanding.

    Returns:
        CCCMetrics with the computed cycle and benchmark commentary.
    """
    ccc = dio_days + dso_days - dpo_days
    drag = ccc - 65.0
    commentary = (
        f"CCC of {ccc:.0f} days is {drag:+.0f} days against a 65-day reference. "
        f"Cash is locked for roughly {ccc:.0f} days between paying for inputs and "
        f"collecting on the sale. (Reference figure is an illustrative sector "
        f"benchmark, not a verified industry statistic.)"
    )
    return CCCMetrics(
        dio_days=dio_days,
        dso_days=dso_days,
        dpo_days=dpo_days,
        ccc_days=ccc,
        industry_benchmark_days=65.0,
        liquidity_drag_commentary=commentary,
    )


def _deficit_geometry(
    rows: List[WeeklyCashRow], buffer_usd: float
) -> Tuple[Optional[int], Optional[int], List[int], float, Optional[int]]:
    """
    Describe the shape of the cash deficit, not just its first appearance.

    Returns:
        (first_shortfall_week, trough_week, weeks_in_deficit,
         peak_funding_need, funding_needed_by_week)

    `peak_funding_need` is the smallest one-off injection that, if received
    before the first shortfall and retained, keeps every remaining week at or
    above `buffer_usd`. Because a retained injection lifts every subsequent
    week equally, that is the maximum weekly gap against the buffer — not the
    gap in the first week that dips.
    """
    below_zero = [r.week for r in rows if r.closing_cash < 0]
    first_shortfall = min(below_zero) if below_zero else None

    trough_row = min(rows, key=lambda r: r.closing_cash)
    trough_week = trough_row.week if trough_row.closing_cash < buffer_usd else None

    gaps = [(r.week, buffer_usd - r.closing_cash) for r in rows if r.closing_cash < buffer_usd]
    if not gaps:
        return first_shortfall, None, [], 0.0, None

    peak_need = round(max(g for _, g in gaps), 2)
    # Cash must be in the account by the week before the first dip below buffer.
    first_gap_week = min(w for w, _ in gaps)
    needed_by = max(1, first_gap_week - 1)

    return first_shortfall, trough_week, below_zero, peak_need, needed_by


def run_13_week_forecast(
    opening_cash: float = DEFAULT_COMPANY["opening_cash_week_1"],
    fixed_weekly_opex: float = DEFAULT_COMPANY["fixed_weekly_opex"],
    ar_schedule: Optional[list] = None,
    week_3_supplier_deposit: float = DEFAULT_WEEK_3_SUPPLIER_DEPOSIT,
    week_6_supplier_deposit: float = DEFAULT_WEEK_6_SUPPLIER_DEPOSIT,
    financed_invoice_id: Optional[str] = None,
    financing_advance_usd: float = 0.0,
    financing_week: int = 5,
    financing_repayment_week: Optional[int] = None,
    financing_repayment_usd: float = 0.0,
    minimum_cash_buffer: float = MINIMUM_CASH_BUFFER_USD,
) -> ForecastSummary:
    """
    Run the 13-week direct cash flow model.

    Under the default seed schedule the balance first goes negative in week 6
    (-$31,350) and reaches its trough in week 8 (-$56,350), recovering only
    partially before closing week 13 at -$11,850. The facility must be sized
    against the trough, not the first dip.

    Args:
        opening_cash: Starting cash balance in USD.
        fixed_weekly_opex: Flat weekly operating outflow.
        ar_schedule: List of (invoice_id, due_week, amount, buyer) tuples.
        week_3_supplier_deposit: Supplier deposit outflow in week 3.
        week_6_supplier_deposit: Supplier deposit outflow in week 6.
        financed_invoice_id: Invoice backing a financing inflow, if any.
        financing_advance_usd: Cash received from financing (net of fees).
        financing_week: Week the advance lands.
        financing_repayment_week: Week the facility is settled, if modelled.
        financing_repayment_usd: Amount repaid at settlement.
        minimum_cash_buffer: Operating float the business must retain.

    Returns:
        ForecastSummary with weekly rows, deficit geometry and peak funding need.
    """
    schedule = ar_schedule if ar_schedule is not None else list(DEFAULT_AR_SCHEDULE)

    ar_by_week = {
        w: {"amount": 0.0, "invoices": []} for w in range(1, FORECAST_WEEKS + 1)
    }
    for inv_id, due_week, amount, _buyer in schedule:
        if 1 <= due_week <= FORECAST_WEEKS:
            ar_by_week[due_week]["amount"] += amount
            ar_by_week[due_week]["invoices"].append(inv_id)

    financing_by_week = {w: 0.0 for w in range(1, FORECAST_WEEKS + 1)}
    financing_labels = {w: [] for w in range(1, FORECAST_WEEKS + 1)}
    if financed_invoice_id and financing_advance_usd > 0:
        if 1 <= financing_week <= FORECAST_WEEKS:
            financing_by_week[financing_week] += financing_advance_usd
            financing_labels[financing_week].append(f"{financed_invoice_id}[FINANCED]")

    repayment_by_week = {w: 0.0 for w in range(1, FORECAST_WEEKS + 1)}
    if financing_repayment_week and financing_repayment_usd > 0:
        if 1 <= financing_repayment_week <= FORECAST_WEEKS:
            repayment_by_week[financing_repayment_week] += financing_repayment_usd

    rows: List[WeeklyCashRow] = []
    current_cash = opening_cash
    start_date = date(2026, 10, 16)

    for week_num in range(1, FORECAST_WEEKS + 1):
        week_start = start_date + timedelta(weeks=week_num - 1)
        week_label = f"W{week_num} ({week_start.strftime('%b %d')})"

        ar_inflows = ar_by_week[week_num]["amount"]
        inflow_invoices = list(ar_by_week[week_num]["invoices"]) + financing_labels[week_num]
        financing_in = financing_by_week[week_num]
        repayment_out = repayment_by_week[week_num]

        supplier_deposit = 0.0
        outflow_note = None
        if week_num == 3:
            supplier_deposit = week_3_supplier_deposit
            outflow_note = "Timber raw material supplier deposit"
        elif week_num == 6:
            supplier_deposit = week_6_supplier_deposit
            outflow_note = "Textile mill + timber bulk deposit"

        net_cash_flow = (
            ar_inflows + financing_in - fixed_weekly_opex - supplier_deposit - repayment_out
        )
        closing_cash = current_cash + net_cash_flow

        rows.append(
            WeeklyCashRow(
                week=week_num,
                week_label=week_label,
                opening_cash=round(current_cash, 2),
                ar_inflows=round(ar_inflows, 2),
                fixed_opex=fixed_weekly_opex,
                supplier_deposits=supplier_deposit,
                financing_inflows=round(financing_in, 2),
                financing_repayments=round(repayment_out, 2),
                net_cash_flow=round(net_cash_flow, 2),
                closing_cash=round(closing_cash, 2),
                is_critical_shortfall=closing_cash < 0,
                is_below_buffer=closing_cash < minimum_cash_buffer,
                inflow_invoices=inflow_invoices,
                outflow_notes=outflow_note,
            )
        )
        current_cash = closing_cash

    first_week, trough_week, deficit_weeks, peak_need, needed_by = _deficit_geometry(
        rows, minimum_cash_buffer
    )

    trough_row = min(rows, key=lambda r: r.closing_cash)
    total_inflows = sum(r.ar_inflows + r.financing_inflows for r in rows)
    total_outflows = sum(
        r.fixed_opex + r.supplier_deposits + r.financing_repayments for r in rows
    )

    return ForecastSummary(
        company_name=DEFAULT_COMPANY["name"],
        starting_cash=opening_cash,
        total_projected_inflows=round(total_inflows, 2),
        total_projected_outflows=round(total_outflows, 2),
        first_shortfall_week=first_week,
        lowest_cash_week=trough_row.week,
        lowest_cash_balance=trough_row.closing_cash,
        weeks_in_deficit=deficit_weeks,
        deficit_duration_weeks=len(deficit_weeks),
        ends_period_in_deficit=rows[-1].closing_cash < 0,
        shortfall_detected=bool(deficit_weeks),
        minimum_cash_buffer=minimum_cash_buffer,
        peak_funding_need_usd=peak_need,
        funding_needed_by_week=needed_by,
        weekly_breakdown=rows,
        assumptions=list(FORECAST_ASSUMPTIONS),
        data_provenance="SYNTHETIC_SANDBOX",
    )


def simulate_forecast(
    delay_buyer: Optional[str] = None,
    delay_weeks: int = 0,
    financed_invoice_id: Optional[str] = None,
    financing_advance_usd: float = 0.0,
    financing_week: int = 5,
    financing_repayment_week: Optional[int] = None,
    financing_repayment_usd: float = 0.0,
) -> ForecastSummary:
    """
    What-if simulator: re-run the forecast with buyer delays and/or financing.

    Args:
        delay_buyer: Buyer name substring to delay (e.g. 'Nordic').
        delay_weeks: Weeks to shift that buyer's invoices (0-4).
        financed_invoice_id: Invoice receiving an advance.
        financing_advance_usd: Net cash from the advance (after fees).
        financing_week: Week the advance lands.
        financing_repayment_week: Week the facility settles, if modelled.
        financing_repayment_usd: Settlement amount.

    Returns:
        ForecastSummary for the scenario.

    Note:
        A delay pushed past week 13 is dropped from the horizon entirely rather
        than clamped to week 13, since clamping would fabricate an inflow that
        the scenario says has not arrived.
    """
    schedule = []
    for inv_id, due_week, amount, buyer in DEFAULT_AR_SCHEDULE:
        if delay_buyer and delay_weeks > 0 and delay_buyer.lower() in buyer.lower():
            new_week = due_week + delay_weeks
            if new_week > FORECAST_WEEKS:
                continue  # Receipt falls outside the horizon — do not clamp it in.
            schedule.append((inv_id, new_week, amount, buyer))
        else:
            schedule.append((inv_id, due_week, amount, buyer))

    return run_13_week_forecast(
        ar_schedule=schedule,
        financed_invoice_id=financed_invoice_id,
        financing_advance_usd=financing_advance_usd,
        financing_week=financing_week,
        financing_repayment_week=financing_repayment_week,
        financing_repayment_usd=financing_repayment_usd,
    )
