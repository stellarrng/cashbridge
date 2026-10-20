"""Scenario simulator: many possible 13-week paths instead of one expected path.

Pure Python + NumPy, no I/O, no LLM. Deterministic for a given seed.

The deterministic forecast (``forecasting_engine``) answers "what is the expected balance each week".
A lender and a Director also need "how often does this plan fail". The simulator draws ``n`` paths from
a *world model* and replays any funding plan on exactly the same paths (common random numbers), so
plans are compared on identical luck.

World model (all parameters in :class:`WorldParams`, every one documented and versioned):
  * every invoice is paid in its due week with probability ``p_on_time`` (from the buyer model, shifted
    by a per-buyer logit correction the learner may estimate); otherwise ``late_delay_weeks`` later;
  * each buyer can have a slowdown quarter (probability ``slowdown_prob``): all its invoices are less
    likely to be on time and arrive ``slowdown_extra_weeks`` later still. This is the correlated risk a
    single expected path hides;
  * a confirmed order ships on plan with probability ``ship_confidence x ship_scale``, otherwise
    ``order_slip_weeks`` later; an unshipped order is never cash inside the week it was planned;
  * one cost factor per path (lognormal, ``cost_sigma``) and one FX factor per path for foreign
    currency (normal, ``fx_sigma``).

Plans are lists of actions from a closed set: ``factor`` (one invoice), ``loan``, ``deposit_cut``.
Nothing here moves money; it only computes balances.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from config.settings import FORECAST_WEEKS, LATE_PAYMENT_DELAY_WEEKS
from schemas.forecast_schemas import ForecastInputs

ACTION_TYPES = ("factor", "loan", "deposit_cut")


@dataclass(frozen=True)
class WorldParams:
    """Parameters of the world model. ``version`` changes whenever a value changes."""

    late_delay_weeks: int = LATE_PAYMENT_DELAY_WEEKS
    buyer_logit_shift: Dict[str, float] = field(default_factory=dict)  # learned per-buyer correction
    slowdown_prob: float = 0.05  # no buyer-quarter in the 12-month history halves its on-time rate; 5% keeps the tail open
    slowdown_p_mult: float = 0.5
    slowdown_extra_weeks: int = 2
    ship_scale: float = 1.0  # learned calibration of the orders' stated ship confidence
    order_slip_weeks: int = 3
    cost_sigma: float = 0.04
    fx_sigma: float = 0.02
    deposit_cut_success: float = 0.6  # chance the supplier accepts a lower deposit
    label: str = "prior"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def version(self) -> str:
        body = {k: v for k, v in self.as_dict().items() if k != "label"}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:10]
        return f"wm-{digest}"

    def with_updates(self, **changes: Any) -> "WorldParams":
        data = self.as_dict()
        data.update(changes)
        return WorldParams(**data)


@dataclass(frozen=True)
class Item:
    """One expected receipt: an invoice or a confirmed order."""

    ref: str
    kind: str  # "invoice" | "order"
    buyer_id: str
    usd: float
    foreign: bool
    due_week: int  # 1-based; may exceed the horizon
    due_date: date
    p_on_time: float
    ship_confidence: float = 1.0
    promised_week: Optional[int] = None


@dataclass
class Paths:
    """Sampled world: when each item is paid on each path, and the base cash flows."""

    items: List[Item]
    pay_week: np.ndarray  # (n, items) 1-based week, may exceed horizon
    amount: np.ndarray  # (n, items) USD received
    outflow: np.ndarray  # (n, weeks) recurring costs + deposits
    inflow: np.ndarray  # (n, weeks)
    opening: float
    buffer: float
    start: date
    deposit_week: Dict[str, int]
    deposit_usd: Dict[str, float]
    deposit_po: Dict[str, float]
    deposit_ok: np.ndarray  # (n,) supplier accepts a deposit cut on this path
    params: WorldParams
    seed: int
    shipped: Optional[np.ndarray] = None  # (n, items) False when an order slipped; always True for invoices

    @property
    def n(self) -> int:
        return self.pay_week.shape[0]

    def index(self, ref: str) -> int:
        return next(i for i, item in enumerate(self.items) if item.ref == ref)


def _week(start: date, day: date) -> int:
    return max(1, (day - start).days // 7 + 1)


def items_from_inputs(inputs: ForecastInputs) -> List[Item]:
    """Invoices and confirmed orders as items, at full face value (USD at demo rates)."""
    out: List[Item] = []
    for rec in inputs.receivables:
        due = rec.promised_date or (rec.due_date + timedelta(days=inputs.dso_shift_days))
        out.append(Item(rec.invoice_id, "invoice", rec.buyer_id, float(rec.amount.to_usd()), rec.amount.currency.value != "USD",
                        _week(inputs.start_date, due), rec.due_date, 1.0 if rec.promised_date else float(rec.p_on_time),
                        promised_week=_week(inputs.start_date, rec.promised_date) if rec.promised_date else None))
    for order in inputs.confirmed_orders:
        due = order.due_date + timedelta(days=inputs.dso_shift_days)
        out.append(Item(order.order_ref, "order", order.buyer_id, float(order.amount.to_usd()), order.amount.currency.value != "USD",
                        _week(inputs.start_date, due), order.due_date, float(order.p_on_time), float(order.ship_confidence)))
    return out


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def recurring_outflows(inputs: ForecastInputs) -> np.ndarray:
    """Fixed costs and month-end payroll per week (deposits are separate so a plan can change them)."""
    out = np.zeros(FORECAST_WEEKS)
    for w in range(1, FORECAST_WEEKS + 1):
        first = inputs.start_date + timedelta(weeks=w - 1)
        cost = float(inputs.weekly_fixed_costs_usd)
        if any((first + timedelta(days=i + 1)).day == 1 for i in range(7)):
            cost += float(inputs.payroll_usd)
        out[w - 1] = cost
    return out


def sample(inputs: ForecastInputs, params: WorldParams = WorldParams(), n: int = 2000, seed: int = 20261019) -> Paths:
    """Draw ``n`` paths of the world model. Same inputs, params and seed: same paths."""
    rng = np.random.default_rng(seed)
    items = items_from_inputs(inputs)
    buyers = sorted({i.buyer_id for i in items})
    b_index = {b: k for k, b in enumerate(buyers)}
    m = len(items)
    slowdown = rng.random((n, len(buyers))) < params.slowdown_prob
    u_pay = rng.random((n, m))
    u_ship = rng.random((n, m))
    cost_factor = np.exp(rng.normal(0.0, params.cost_sigma, n) - params.cost_sigma ** 2 / 2)
    fx_factor = 1.0 + rng.normal(0.0, params.fx_sigma, n)
    deposit_ok = rng.random(n) < params.deposit_cut_success

    pay_week = np.zeros((n, m), dtype=int)
    amount = np.zeros((n, m))
    shipped_all = np.ones((n, m), dtype=bool)
    for j, item in enumerate(items):
        slow = slowdown[:, b_index[item.buyer_id]]
        if item.promised_week is not None:
            p = np.full(n, 1.0)
        else:
            p = _sigmoid(_logit(np.full(n, item.p_on_time)) + params.buyer_logit_shift.get(item.buyer_id, 0.0))
            p = np.where(slow, p * params.slowdown_p_mult, p)
        on_time = u_pay[:, j] < p
        week = np.where(on_time, item.due_week, item.due_week + params.late_delay_weeks + np.where(slow, params.slowdown_extra_weeks, 0))
        if item.kind == "order":
            shipped = u_ship[:, j] < min(1.0, item.ship_confidence * params.ship_scale)
            week = np.where(shipped, week, week + params.order_slip_weeks)
            shipped_all[:, j] = shipped
        pay_week[:, j] = week
        amount[:, j] = item.usd * (fx_factor if item.foreign else 1.0)

    inflow = np.zeros((n, FORECAST_WEEKS))
    rows = np.repeat(np.arange(n), m).reshape(n, m)
    inside = pay_week <= FORECAST_WEEKS
    np.add.at(inflow, (rows[inside], pay_week[inside] - 1), amount[inside])

    base_out = recurring_outflows(inputs)
    outflow = np.outer(cost_factor, base_out)
    deposit_week, deposit_usd, deposit_po = {}, {}, {}
    for d in inputs.deposits:
        usd = float(d.po_value_usd * d.pct / 100)
        outflow[:, d.week - 1] += usd
        deposit_week[d.ref], deposit_usd[d.ref], deposit_po[d.ref] = d.week, usd, float(d.po_value_usd)
    return Paths(items, pay_week, amount, outflow, inflow, float(inputs.opening_cash_usd), float(inputs.buffer_usd),
                 inputs.start_date, deposit_week, deposit_usd, deposit_po, deposit_ok, params, seed, shipped_all)


# ---------------------------------------------------------------- plans
def action_flows(paths: Paths, action: Dict[str, Any]) -> np.ndarray:
    """Extra cash flows of one action on every path, shape (n, weeks)."""
    n, flows = paths.n, np.zeros((paths.n, FORECAST_WEEKS))
    kind = action["type"]
    if kind not in ACTION_TYPES:
        raise ValueError(f"Unknown action type {kind!r}")
    draw = int(action.get("week", 1))
    if kind == "factor":
        advance = float(action["advance_usd"])
        flows[:, draw - 1] += advance
        settle, cost = factor_settlement(paths, action)
        inside = settle <= FORECAST_WEEKS
        # Settlement: the invoice cash goes to the factor; the SME gives up advance + fee + interest to the
        # week the buyer actually pays on that path (a late buyer makes factoring dearer).
        np.add.at(flows, (np.arange(n)[inside], settle[inside] - 1), -(advance + cost[inside]))
    elif kind == "loan":
        amount, fee, interest = float(action["amount_usd"]), float(action["fee_usd"]), float(action["interest_usd"])
        flows[:, draw - 1] += amount - fee
        repay = draw + math.ceil(int(action["days"]) / 7)
        if repay <= FORECAST_WEEKS:
            flows[:, repay - 1] -= amount + interest
    elif kind == "deposit_cut":
        ref = action["ref"]
        saving = paths.deposit_usd[ref] - paths.deposit_po[ref] * float(action["new_pct"]) / 100
        flows[paths.deposit_ok, paths.deposit_week[ref] - 1] += max(0.0, saving)
    return flows


def factor_settlement(paths: Paths, action: Dict[str, Any]) -> tuple:
    """Week the factor is repaid on each path and the fee + interest actually paid."""
    j = paths.index(action["ref"])
    draw = int(action.get("week", 1))
    settle = np.maximum(paths.pay_week[:, j], draw)
    days = np.maximum(7, (settle - draw) * 7 + 2)
    interest = float(action["advance_usd"]) * float(action["rate_pa_pct"]) / 100 * days / 365
    return settle, float(action["fee_usd"]) + interest


def expected_cost(paths: Paths, actions: Sequence[Dict[str, Any]]) -> float:
    """Mean financing cost over paths, including interest that accrues after the horizon."""
    total = np.zeros(paths.n)
    for a in actions:
        if a["type"] == "factor":
            total += factor_settlement(paths, a)[1]
        elif a["type"] == "loan":
            total += float(a["fee_usd"]) + float(a["interest_usd"])
    return round(float(total.mean()), 2)


def closings(paths: Paths, actions: Sequence[Dict[str, Any]] = ()) -> np.ndarray:
    """Closing balance per path and week with the plan applied, shape (n, weeks)."""
    net = paths.inflow - paths.outflow
    for action in actions:
        net = net + action_flows(paths, action)
    return paths.opening + np.cumsum(net, axis=1)


def summarize(paths: Paths, closing: np.ndarray) -> Dict[str, Any]:
    """What a credit officer reads: how often the plan keeps cash positive, and how bad the bad paths are."""
    trough = closing.min(axis=1)
    safe = trough >= 0
    above_buffer = trough >= paths.buffer
    neg = closing < 0
    first_neg = np.where(neg.any(axis=1), neg.argmax(axis=1) + 1, 0)
    shortfall = np.maximum(0, -trough)
    # CVaR 95%: average shortfall over the worst 5% of scenarios (always >= the p95 shortfall).
    tail = np.sort(shortfall)[::-1][: max(1, int(np.ceil(0.05 * shortfall.size)))]
    return {
        "paths": int(paths.n),
        "p_no_negative_week": round(float(safe.mean()), 4),
        "p_above_buffer_all_weeks": round(float(above_buffer.mean()), 4),
        "p_negative_by_week": [round(float(x), 4) for x in neg.mean(axis=0)],
        "trough_p5_usd": round(float(np.percentile(trough, 5)), 2),
        "trough_p50_usd": round(float(np.percentile(trough, 50)), 2),
        "expected_shortfall_usd": round(float(np.maximum(0, -trough).mean()), 2),
        "shortfall_p95_usd": round(float(np.percentile(shortfall, 95)), 2),
        "shortfall_cvar95_usd": round(float(tail.mean()), 2),
        "earliest_gap_week_p10": int(np.percentile(first_neg[first_neg > 0], 10)) if (first_neg > 0).any() else None,
        "closing_p10_by_week": [round(float(x), 2) for x in np.percentile(closing, 10, axis=0)],
        "closing_p50_by_week": [round(float(x), 2) for x in np.percentile(closing, 50, axis=0)],
        "closing_p90_by_week": [round(float(x), 2) for x in np.percentile(closing, 90, axis=0)],
        "world_model": paths.params.version,
        "seed": paths.seed,
    }


def evaluate(paths: Paths, actions: Sequence[Dict[str, Any]] = ()) -> Dict[str, Any]:
    return summarize(paths, closings(paths, actions))


# ------------------------------------------------------- one realised path
def realise(inputs: ForecastInputs, truth: WorldParams, seed: int) -> Paths:
    """One path drawn from a (possibly different) "true" world: used to create simulated outcomes."""
    return sample(inputs, truth, n=1, seed=seed)


def item_outcomes(paths: Paths, row: int = 0) -> List[Dict[str, Any]]:
    """Per-item outcome on one path, the raw material the learner compares with its predictions."""
    out = []
    for j, item in enumerate(paths.items):
        week = int(paths.pay_week[row, j])
        shipped = bool(paths.shipped[row, j]) if paths.shipped is not None else True
        delay = week - item.due_week - (0 if shipped else paths.params.order_slip_weeks)
        out.append({"ref": item.ref, "kind": item.kind, "buyer_id": item.buyer_id, "due_week": item.due_week,
                    "paid_week": week, "on_time": delay == 0, "shipped": shipped, "usd": round(float(item.usd), 2),
                    "p_on_time": item.p_on_time, "ship_confidence": item.ship_confidence})
    return out


def items_due_inside(items: Iterable[Item], horizon: int = FORECAST_WEEKS) -> List[Item]:
    return [i for i in items if i.due_week <= horizon]


def money(value: Decimal | float) -> float:
    return round(float(value), 2)
