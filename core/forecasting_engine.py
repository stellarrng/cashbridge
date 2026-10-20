"""Forecasting engine: cash conversion cycle and the 13-week direct cash forecast.

Pure Python, no I/O, no LLM. Money is Decimal USD at cent precision.

Direct method
  * Expected inflow = invoice value x p_on_time, placed in the invoice's due week.
  * The late remainder (value x (1 - p_on_time)) arrives LATE_PAYMENT_DELAY_WEEKS later.
  * A buyer's dated promise to pay overrides both: the full value lands in the promised week.
  * A confirmed, not-yet-invoiced order counts ship_confidence x its value, due on its planned
    invoice date + terms, and is then treated like an invoice. It is never a receivable.
  * Outflows = weekly fixed costs + month-end payroll + supplier deposits.
  * A week is "shortfall" below 0 and "at_risk" below the cash buffer.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, NamedTuple, Optional

from config.settings import (
    FORECAST_WEEKS,
    FX_STRESS_PCT,
    LATE_PAYMENT_DELAY_WEEKS,
    USD_VND,
)
from schemas.document_schemas import Money
from schemas.forecast_schemas import (
    CCCMetrics,
    ConfirmedOrder,
    DepositPlan,
    ForecastInputs,
    ForecastResult,
    FxExposure,
    LedgerSnapshot,
    OpenReceivable,
    ScenarioDelta,
    ScenarioParams,
    ScenarioResult,
    ShortfallAttribution,
    WeeklyCashRow,
)

_CENT = Decimal("0.01")
FX_EXPOSURE_NOTE = "Exposure estimate only. This is not a hedging recommendation."


def _cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _days(numerator: Decimal, denominator: Decimal, period_days: int) -> float:
    return float((numerator / denominator * period_days).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def compute_ccc(ledger: LedgerSnapshot) -> CCCMetrics:
    """CCC = DIO + DSO - DPO, each component computed from ledger averages.

    DIO = inventory / COGS x days, DSO = receivables / revenue x days,
    DPO = payables / COGS x days. Components are rounded to 0.1 day and CCC is the
    sum of the rounded components so the published numbers always add up.
    """
    dio = _days(ledger.avg_inventory_usd, ledger.cogs_usd, ledger.period_days)
    dso = _days(ledger.avg_receivables_usd, ledger.revenue_usd, ledger.period_days)
    dpo = _days(ledger.avg_payables_usd, ledger.cogs_usd, ledger.period_days)
    return CCCMetrics(dio=dio, dso=dso, dpo=dpo, ccc=round(dio + dso - dpo, 1))


# ------------------------------------------------------------------ receipts
class _Receipt(NamedTuple):
    invoice_id: str
    week: int
    amount: Decimal
    foreign: bool


class _InvoiceView(NamedTuple):
    receivable: OpenReceivable
    due_week: int
    raw_usd: Decimal
    fx_effect: Decimal  # change in USD value caused by the FX what-if
    tariff_effect: Decimal  # change in USD value caused by the tariff what-if (<= 0)
    final_usd: Decimal
    on_time: Decimal
    late: Decimal


def _week_of(start: date, day: date) -> int:
    """1-based forecast week containing ``day``; earlier dates count as week 1."""
    return max(1, (day - start).days // 7 + 1)


def order_as_receivable(order: ConfirmedOrder) -> OpenReceivable:
    """The expected (confidence-weighted) part of a confirmed order, in the shape the engine uses."""
    expected = Money.from_amount(order.amount.amount * Decimal(str(order.ship_confidence)), order.amount.currency)
    return OpenReceivable(
        invoice_id=order.order_ref,
        buyer_id=order.buyer_id,
        buyer_name=order.buyer_name,
        market=order.market,
        amount=expected,
        due_date=order.due_date,
        p_on_time=order.p_on_time,
    )


def _invoice_views(inputs: ForecastInputs) -> List[_InvoiceView]:
    views: List[_InvoiceView] = []
    fx_factor = Decimal(1) + inputs.fx_change_pct / 100
    tariff_cut = inputs.tariff_rate_pct * inputs.tariff_shared_pct / Decimal(10_000)
    for rec in list(inputs.receivables) + [order_as_receivable(o) for o in inputs.confirmed_orders]:
        raw = rec.amount.to_usd()
        after_fx = _cents(raw * fx_factor) if rec.amount.currency.value != "USD" else raw
        final = _cents(after_fx * (Decimal(1) - tariff_cut)) if rec.market == "US" else after_fx
        if rec.promised_date is not None:
            # A dated promise replaces the probability model: the full amount lands on that date.
            on_time = final
            due = rec.promised_date
        else:
            on_time = _cents(final * Decimal(str(rec.p_on_time)))
            due = rec.due_date + timedelta(days=inputs.dso_shift_days)
        views.append(
            _InvoiceView(
                receivable=rec,
                due_week=_week_of(inputs.start_date, due),
                raw_usd=raw,
                fx_effect=after_fx - raw,
                tariff_effect=final - after_fx,
                final_usd=final,
                on_time=on_time,
                late=final - on_time,
            )
        )
    return views


def _receipts(views: List[_InvoiceView]) -> List[_Receipt]:
    receipts: List[_Receipt] = []
    for view in views:
        foreign = view.receivable.amount.currency.value != "USD"
        invoice_id = view.receivable.invoice_id
        if view.on_time > 0 and view.due_week <= FORECAST_WEEKS:
            receipts.append(_Receipt(invoice_id, view.due_week, view.on_time, foreign))
        late_week = view.due_week + LATE_PAYMENT_DELAY_WEEKS
        if view.late > 0 and late_week <= FORECAST_WEEKS:
            receipts.append(_Receipt(invoice_id, late_week, view.late, foreign))
    return receipts


# ------------------------------------------------------------------- outflows
def _deposit_amount(deposit: DepositPlan) -> Decimal:
    return _cents(deposit.po_value_usd * deposit.pct / 100)


def _week_start(inputs: ForecastInputs, week: int) -> date:
    return inputs.start_date + timedelta(weeks=week - 1)


def _has_month_end(first_day: date) -> bool:
    return any((first_day + timedelta(days=i + 1)).day == 1 for i in range(7))


def _recurring_cost(inputs: ForecastInputs, week: int) -> Decimal:
    cost = inputs.weekly_fixed_costs_usd
    if _has_month_end(_week_start(inputs, week)):
        cost += inputs.payroll_usd
    return cost


# ------------------------------------------------------------------- forecast
def forecast_13w(inputs: ForecastInputs) -> ForecastResult:
    """Run the 13-week direct forecast and find the first shortfall and its drivers."""
    views = _invoice_views(inputs)
    receipts = _receipts(views)
    inflow_by_week: Dict[int, Decimal] = {w: Decimal(0) for w in range(1, FORECAST_WEEKS + 1)}
    for receipt in receipts:
        inflow_by_week[receipt.week] += receipt.amount
    deposit_by_week: Dict[int, Decimal] = {w: Decimal(0) for w in range(1, FORECAST_WEEKS + 1)}
    for deposit in inputs.deposits:
        deposit_by_week[deposit.week] += _deposit_amount(deposit)

    rows: List[WeeklyCashRow] = []
    cash = inputs.opening_cash_usd
    for week in range(1, FORECAST_WEEKS + 1):
        outflows = _recurring_cost(inputs, week) + deposit_by_week[week]
        closing = cash + inflow_by_week[week] - outflows
        if closing < 0:
            status = "shortfall"
        elif closing < inputs.buffer_usd:
            status = "at_risk"
        else:
            status = "ok"
        rows.append(
            WeeklyCashRow(
                week=week,
                start_date=_week_start(inputs, week),
                opening=cash,
                inflows=inflow_by_week[week],
                outflows=outflows,
                closing=closing,
                status=status,
            )
        )
        cash = closing

    first = first_negative_week(rows)
    shortfall = -rows[first - 1].closing if first else None
    return ForecastResult(
        buffer_usd=inputs.buffer_usd,
        weeks=rows,
        first_shortfall_week=first,
        shortfall_usd=shortfall,
        min_closing_usd=min(row.closing for row in rows),
        attribution=shortfall_attribution(inputs, views, first) if first else [],
    )


def first_negative_week(rows: List[WeeklyCashRow]) -> Optional[int]:
    """First week whose closing balance is below zero, or None."""
    return next((row.week for row in rows if row.closing < 0), None)


def shortfall_attribution(
    inputs: ForecastInputs, views: List[_InvoiceView], week: int
) -> List[ShortfallAttribution]:
    """Split the shortfall in ``week`` into drivers that add up to it exactly.

    shortfall = -(opening cash + inflows - outflows up to that week), rewritten as:
      deposits + late invoice value not yet received + tariff/FX changes
      - (opening cash + full-value scheduled inflows - recurring costs)
    The last term is the operating baseline; it is negative when the business would
    stay cash-positive without the stress drivers.
    """
    drivers: List[ShortfallAttribution] = []
    for deposit in inputs.deposits:
        if deposit.week <= week:
            drivers.append(
                ShortfallAttribution(
                    driver=f"{deposit.pct.normalize():f}% deposit on {deposit.ref}",
                    amount_usd=_deposit_amount(deposit),
                    source_ref=f"doc:{deposit.ref}",
                )
            )

    order_refs = {o.order_ref for o in inputs.confirmed_orders}
    baseline = inputs.opening_cash_usd
    fx_total = Decimal(0)
    tariff_total = Decimal(0)
    for view in views:
        if view.due_week > week:
            continue
        baseline += view.raw_usd
        fx_total -= view.fx_effect
        tariff_total -= view.tariff_effect
        late_week = view.due_week + LATE_PAYMENT_DELAY_WEEKS
        if view.late > 0 and late_week > week:
            rec = view.receivable
            is_order = rec.invoice_id in order_refs
            drivers.append(
                ShortfallAttribution(
                    driver=(f"Confirmed order {rec.invoice_id} ({rec.buyer_name}) is likely paid late"
                            if is_order else
                            f"{rec.invoice_id} ({rec.buyer_name}) is likely late: {round(rec.p_on_time * 100)}% chance of on-time payment"),
                    amount_usd=view.late,
                    source_ref=f"order:{rec.invoice_id}" if is_order else f"inv:{rec.invoice_id}",
                )
            )
    drivers = _fold_small_late_drivers(drivers)
    if tariff_total:
        drivers.append(
            ShortfallAttribution(
                driver="Tariff share conceded to US buyers",
                amount_usd=tariff_total,
                source_ref="scenario:tariff_shared_pct",
            )
        )
    if fx_total:
        drivers.append(
            ShortfallAttribution(
                driver="FX move on foreign-currency receivables",
                amount_usd=fx_total,
                source_ref="scenario:fx_change_pct",
            )
        )
    baseline -= sum((_recurring_cost(inputs, w) for w in range(1, week + 1)), Decimal(0))
    drivers.append(
        ShortfallAttribution(
            driver="Opening cash plus scheduled inflows (invoices and confirmed orders), net of fixed costs and payroll",
            amount_usd=-baseline,
            source_ref="ledger:baseline",
        )
    )
    return drivers


SMALL_DRIVER_USD = Decimal("2000")


def _fold_small_late_drivers(drivers: List[ShortfallAttribution]) -> List[ShortfallAttribution]:
    """Keep the attribution readable: late-payment drivers under SMALL_DRIVER_USD are summed into one line.

    The total is unchanged, so the drivers still add up to the shortfall exactly.
    """
    small = [d for d in drivers if d.source_ref.startswith(("inv:", "order:")) and d.amount_usd < SMALL_DRIVER_USD]
    if len(small) < 2:
        return drivers
    kept = [d for d in drivers if d not in small]
    kept.append(
        ShortfallAttribution(
            driver=f"{len(small)} other invoices/orders likely paid late (each under USD {SMALL_DRIVER_USD:,.0f})",
            amount_usd=sum((d.amount_usd for d in small), Decimal(0)),
            source_ref="inv:" + ",".join(d.source_ref.split(":", 1)[1] for d in small),
        )
    )
    return kept


# ------------------------------------------------------------------- what-if
def apply_params(inputs: ForecastInputs, params: ScenarioParams) -> ForecastInputs:
    """Return a copy of ``inputs`` with the what-if controls applied."""
    deposits = [
        deposit.model_copy(update={"pct": Decimal(str(params.deposit_pct))}) if deposit.adjustable else deposit
        for deposit in inputs.deposits
    ]
    return inputs.model_copy(
        update={
            "dso_shift_days": params.dso_change_days,
            "fx_change_pct": Decimal(str(params.fx_change_pct)),
            "tariff_shared_pct": Decimal(str(params.tariff_shared_pct)),
            "deposits": deposits,
        }
    )


def simulate(base_inputs: ForecastInputs, params: ScenarioParams) -> ScenarioResult:
    """Re-run the forecast under what-if controls and compare it with the base case."""
    base = forecast_13w(base_inputs)
    new = forecast_13w(apply_params(base_inputs, params))
    return ScenarioResult(
        forecast=new,
        delta=ScenarioDelta(
            first_shortfall_week_before=base.first_shortfall_week,
            first_shortfall_week_after=new.first_shortfall_week,
            min_closing_before_usd=base.min_closing_usd,
            min_closing_after_usd=new.min_closing_usd,
        ),
    )


# ---------------------------------------------------------------- FX exposure
def fx_exposure(inputs: ForecastInputs) -> List[FxExposure]:
    """Foreign-currency inflow per week and the effect of a +/-2% rate move."""
    foreign: Dict[int, Decimal] = {w: Decimal(0) for w in range(1, FORECAST_WEEKS + 1)}
    for receipt in _receipts(_invoice_views(inputs)):
        if receipt.foreign:
            foreign[receipt.week] += receipt.amount
    rows: List[FxExposure] = []
    for week, amount in foreign.items():
        move = _cents(amount * FX_STRESS_PCT / 100)
        rows.append(
            FxExposure(
                week=week,
                foreign_inflow_usd=amount,
                impact_up_usd=move,
                impact_down_usd=-move,
                impact_up_vnd=move * USD_VND,
                impact_down_vnd=-move * USD_VND,
            )
        )
    return rows
