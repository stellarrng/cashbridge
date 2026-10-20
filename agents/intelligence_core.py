"""CashBridge Intelligence Core: a bounded planner that learns from outcomes, offline and under control.

It never talks to a user and never moves money. It reads structured state, ranks plans built from a
closed set of actions, and writes a plan for the governed Autopilot and the humans to act on.

Three layers, kept separate on purpose:
  A. Predictive: the buyer model (on-time probability) and the scenario simulator (many paths).
  B. Planning: :class:`IntelligenceCore` builds every plan the policy allows, scores all of them on the
     same simulated paths, and picks the cheapest plan that meets the goal's probability. If none does,
     it says so and returns the plan that comes closest.
  C. Governance: :func:`validate_plan` is a checker independent of the planner. Every plan, including the
     planner's own choice, passes through it. The planner cannot add action types, pledge an order or an
     unverified invoice, exceed the pack limit or over-borrow.

Learning (memory is not learning):
  * :class:`CaseMemory` stores what was predicted and, later, what happened (hash-chained JSONL).
  * :func:`attribute_outcome` explains a miss: collections timing, order slippage, cost overrun,
    funding too small, objective too narrow, or unexplained.
  * :class:`WorldModelLearner` proposes new world-model parameters from recorded outcomes and scores
    them leave-one-episode-out against the active ones. A proposal is only *pending*; it becomes active
    when a named person approves it (:class:`ModelRegistry`). Nothing updates itself after a real
    transaction.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from config.settings import FORECAST_WEEKS
from core import scenario_simulator as sim
from core.forecasting_engine import forecast_13w
from schemas.forecast_schemas import ForecastInputs

STATE_SCHEMA = "cb.state.v1"
DRAW_LEAD = 0  # extra candidate draw week this many weeks before the first risky week (0 = off)
PLANNER_ID = "intelligence-core-v1"

GOALS: Dict[str, Dict[str, Any]] = {
    "keep_cash_positive": {"label": "Keep every week at or above zero", "floor": "zero", "min_probability": 0.90},
    "keep_above_buffer": {"label": "Keep every week above the cash buffer", "floor": "buffer", "min_probability": 0.80},
}

ALLOWED_PROBABILITIES = (0.8, 0.85, 0.9, 0.95)

# Planner objectives. "cheapest" (default): among plans that reach the goal probability, the lowest expected
# cost. "risk_adjusted": the lowest expected cost + CVAR_WEIGHT x CVaR95 shortfall, so between two plans that
# both reach the goal the one with the smaller worst-5% gap wins unless it costs clearly more.
# CVAR_WEIGHT = 5% tail probability x 40% cost of emergency funding in that tail (late fees, penalty overdraft)
# = 0.02: pay up to USD 2 of expected cost to cut USD 100 of tail shortfall. A fixed policy value, not tuned on
# the benchmark, and never relaxed by the planner itself.
OBJECTIVES = ("cheapest", "risk_adjusted", "robust")
# Ambiguity set for the "robust" objective (finite-scenario distributionally robust choice, cf. Delage & Ye 2010,
# Mohajerin Esfahani & Kuhn 2018). Fixed policy values, never fitted to a benchmark: any single buyer's odds of paying
# on time may halve, all buyers' odds may drop by a third together, confirmed orders may ship at 85% of stated confidence.
AMBIGUITY = {"single_buyer_logit": math.log(0.5), "all_buyers_logit": math.log(2 / 3), "ship_scale": 0.85}
CVAR_WEIGHT = 0.02
DEFAULT_OBJECTIVE = "risk_adjusted"  # chosen after eval/risk_planner_benchmark.py: lower tail, same cost

# Policy limits the planner cannot change. They are read by validate_plan, not by the planner.
POLICY = {
    "allowed_actions": sim.ACTION_TYPES,
    "max_packs_per_plan": 3,  # each factoring or loan is one pack and one Director approval
    "over_borrowing_factor": 1.5,  # total funding <= 1.5 x the 95th-percentile shortfall without action
    "min_draw_week": 1,
    "min_days_to_due_after_draw": 14,  # no advance on an invoice about to be paid anyway
    "min_p_on_time_to_pledge": 0.5,  # no pledging receivables more likely late than not (adverse selection)
}


# ---------------------------------------------------------------- inputs
@dataclass
class Pledgeable:
    ref: str
    buyer_id: str
    buyer: str
    usd: float
    due_date: date
    p_on_time: float = 1.0


@dataclass
class CoreInputs:
    """Everything the Core needs, independent of the coordinator (the benchmark builds these directly)."""

    forecast_inputs: ForecastInputs
    pledgeable: List[Pledgeable]
    excluded: Dict[str, str]  # invoice -> why it may not back funding
    factoring: Dict[str, float]  # advance_pct, fee_pct_of_invoice, interest_pa_pct, max_days, min_invoice_usd
    loan: Optional[Dict[str, float]]  # amount_usd, upfront_fee_pct, interest_pa_pct, days
    as_of: date
    case_id: str = "CASE"

    @classmethod
    def from_coordinator(cls, c: Any) -> "CoreInputs":
        rows = c.verification
        invoices = {i.invoice_no: i for i in c.open_invoices()}
        p_map = {r.invoice_id: r.p_on_time for r in c.forecast_inputs.receivables}
        pledgeable, excluded = [], {}
        for r in rows:
            inv = invoices.get(r["invoice_id"])
            if inv is None:
                continue
            reasons = []
            if r["status"] != "ELIGIBLE":
                reasons.append(f"3-way match {r['status'].lower()}")
            if r["registry_status"] != "NOT_REGISTERED":
                reasons.append("already in the financing registry")
            if not r["tax_id_valid"]:
                reasons.append("seller tax ID invalid")
            if inv.currency.value != "USD":
                reasons.append(f"{inv.currency.value} invoice (factor takes USD only)")
            if inv.due_date <= c.as_of:
                reasons.append("already due")
            if c.scan_checks.get(inv.invoice_no):
                reasons.append("scan needs a person")
            p_on_time = p_map.get(inv.invoice_no, 1.0)
            if p_on_time < POLICY["min_p_on_time_to_pledge"]:
                reasons.append(f"buyer model gives {p_on_time:.0%} on-time: a lender would not advance on it")
            if reasons:
                excluded[inv.invoice_no] = "; ".join(reasons)
            else:
                pledgeable.append(Pledgeable(inv.invoice_no, inv.buyer_id, inv.buyer_name, float(inv.amount.to_usd()), inv.due_date, p_on_time))
        f = c.catalog.factoring
        loan = c.catalog.bridge_loan
        return cls(
            forecast_inputs=c.forecast_inputs,
            pledgeable=pledgeable,
            excluded=excluded,
            factoring={"advance_pct": float(f.advance_pct), "fee_pct_of_invoice": float(f.fee_pct_of_invoice),
                       "interest_pa_pct": float(f.interest_pa_pct), "max_days": float(f.max_days), "min_invoice_usd": float(f.min_invoice_usd)},
            loan={"amount_usd": float(loan.amount_usd), "upfront_fee_pct": float(loan.upfront_fee_pct),
                  "interest_pa_pct": float(loan.interest_pa_pct), "days": float(loan.days)} if loan else None,
            as_of=c.as_of,
            case_id=c.case.case_id,
        )


# ---------------------------------------------------------------- actions
def _week_start(start: date, week: int) -> date:
    return start + timedelta(weeks=week - 1)


def _dec(x: Any):
    from decimal import Decimal
    return Decimal(repr(float(x)))


def _cents(x: Any) -> float:
    """Half-up to the cent in Decimal, exactly like core/funding_evaluator.py (float round() is banker's and binary)."""
    from decimal import ROUND_HALF_UP, Decimal
    value = x if isinstance(x, Decimal) else _dec(x)
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def factor_action(p: Pledgeable, terms: Dict[str, float], start: date, week: int) -> Dict[str, Any]:
    from decimal import ROUND_HALF_UP, Decimal
    cent = lambda v: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # noqa: E731
    draw = _week_start(start, week)
    usd = _dec(p.usd)
    advance = cent(usd * _dec(terms["advance_pct"]) / 100)
    fee = cent(usd * _dec(terms["fee_pct_of_invoice"]) / 100)
    days = max(1, (p.due_date - draw).days)
    interest = cent(advance * _dec(terms["interest_pa_pct"]) / 100 * days / 365)
    return {"type": "factor", "ref": p.ref, "buyer_id": p.buyer_id, "week": week, "advance_usd": float(advance),
            "fee_usd": float(fee), "rate_pa_pct": terms["interest_pa_pct"], "cost_usd": float(fee + interest),
            "days": days, "invoice_usd": _cents(usd)}


def loan_action(terms: Dict[str, float], week: int) -> Dict[str, Any]:
    from decimal import ROUND_HALF_UP, Decimal
    cent = lambda v: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # noqa: E731
    amount = terms["amount_usd"]
    fee = cent(_dec(amount) * _dec(terms["upfront_fee_pct"]) / 100)
    interest = cent(_dec(amount) * _dec(terms["interest_pa_pct"]) / 100 * int(terms["days"]) / 365)
    return {"type": "loan", "ref": "bridge_loan", "week": week, "amount_usd": amount, "fee_usd": float(fee),
            "interest_usd": float(interest), "cost_usd": float(fee + interest), "days": int(terms["days"])}


def plan_cost(actions: Sequence[Dict[str, Any]]) -> float:
    return _cents(sum(float(a.get("cost_usd", 0)) for a in actions))


def plan_funding(actions: Sequence[Dict[str, Any]]) -> float:
    return _cents(sum(float(a.get("advance_usd", a.get("amount_usd", 0))) for a in actions if a["type"] in ("factor", "loan")))


def plan_packs(actions: Sequence[Dict[str, Any]]) -> int:
    return sum(1 for a in actions if a["type"] in ("factor", "loan"))


def plan_id(actions: Sequence[Dict[str, Any]]) -> str:
    if not actions:
        return "no_action"
    parts = []
    for a in actions:
        parts.append(f"{a['type']}:{a.get('ref')}@w{a.get('week')}" + (f":{a['new_pct']}%" if a["type"] == "deposit_cut" else ""))
    return "+".join(sorted(parts))


def describe(actions: Sequence[Dict[str, Any]]) -> str:
    if not actions:
        return "Do nothing"
    out = []
    for a in actions:
        if a["type"] == "factor":
            out.append(f"Factor {a['ref']} (advance USD {a['advance_usd']:,.0f}, week {a['week']})")
        elif a["type"] == "loan":
            out.append(f"Bridge loan USD {a['amount_usd']:,.0f} (week {a['week']})")
        elif a["type"] == "deposit_cut":
            out.append(f"Ask supplier to cut {a['ref']} deposit to {a['new_pct']}%")
    return " + ".join(out)


# ------------------------------------------------------------- governance
def validate_plan(actions: Sequence[Dict[str, Any]], inputs: CoreInputs, need_p95_usd: float) -> List[str]:
    """Independent policy check. Returns the list of violations (empty = allowed)."""
    problems: List[str] = []
    allowed = {p.ref: p for p in inputs.pledgeable}
    orders = {o.order_ref for o in inputs.forecast_inputs.confirmed_orders}
    seen = set()
    for a in actions:
        kind = a.get("type")
        if kind not in POLICY["allowed_actions"]:
            problems.append(f"action type {kind!r} is not allowed")
            continue
        week = int(a.get("week", 0))
        if not POLICY["min_draw_week"] <= week <= FORECAST_WEEKS:
            problems.append(f"{kind} week {week} outside the horizon")
        if kind == "factor":
            ref = a.get("ref")
            if ref in orders:
                problems.append(f"{ref} is an order, not an invoice: it cannot be pledged")
            elif ref not in allowed:
                problems.append(f"{ref} may not back funding ({inputs.excluded.get(ref, 'not a verified, unpledged invoice')})")
            else:
                p = allowed[ref]
                terms = inputs.factoring
                if p.usd < terms["min_invoice_usd"]:
                    problems.append(f"{ref} below the factor's minimum")
                if (p.due_date - inputs.as_of).days > terms["max_days"]:
                    problems.append(f"{ref} tenor exceeds {terms['max_days']:.0f} days")
                expected = round(p.usd * terms["advance_pct"] / 100, 2)
                if abs(float(a.get("advance_usd", 0)) - expected) > 0.01:
                    problems.append(f"{ref} advance differs from the lender's advance rate")
                if p.p_on_time < POLICY["min_p_on_time_to_pledge"]:
                    problems.append(f"{ref} is more likely late than not ({p.p_on_time:.0%}): not pledgeable")
                draw_day = _week_start(inputs.forecast_inputs.start_date, week)
                if (p.due_date - draw_day).days < POLICY["min_days_to_due_after_draw"]:
                    problems.append(f"{ref} is due within {POLICY['min_days_to_due_after_draw']} days of the draw")
            if ref in seen:
                problems.append(f"{ref} pledged twice in one plan")
            seen.add(ref)
        if kind == "loan" and inputs.loan is None:
            problems.append("no bridge loan in the catalogue")
        if kind == "deposit_cut" and a.get("ref") not in {d.ref for d in inputs.forecast_inputs.deposits}:
            problems.append(f"unknown deposit {a.get('ref')}")
    if plan_packs(actions) > POLICY["max_packs_per_plan"]:
        problems.append(f"{plan_packs(actions)} packs exceed the limit of {POLICY['max_packs_per_plan']}")
    cap = POLICY["over_borrowing_factor"] * max(need_p95_usd, 1.0)
    if plan_funding(actions) > cap:
        problems.append(f"funding USD {plan_funding(actions):,.0f} exceeds the over-borrowing cap USD {cap:,.0f}")
    return problems


# ---------------------------------------------------------------- planner
@dataclass
class CoreResult:
    state: Dict[str, Any]
    chosen: Dict[str, Any]
    ranked: List[Dict[str, Any]]
    rejected: List[Dict[str, Any]]
    baseline: Dict[str, Any]
    goal: Dict[str, Any]
    status: str
    world_model: Dict[str, Any]
    memory: List[Dict[str, Any]] = field(default_factory=list)
    feasibility: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"planner": PLANNER_ID, "status": self.status, "goal": self.goal, "state": self.state, "chosen": self.chosen,
                "feasibility": self.feasibility,
                "ranked": self.ranked, "rejected": self.rejected, "fixed_workflow_plan": self.baseline,
                "world_model": self.world_model, "similar_cases": self.memory, "synthetic": True}


def ambiguity_worlds(params: "sim.WorldParams", buyers: Sequence[str]) -> List["sim.WorldParams"]:
    """The nominal world plus plausible adverse variants (labels say which)."""
    worlds = [params]
    for b in buyers:
        shift = dict(params.buyer_logit_shift)
        shift[b] = shift.get(b, 0.0) + AMBIGUITY["single_buyer_logit"]
        worlds.append(params.with_updates(buyer_logit_shift=shift, label=f"{b} pays on time half as often"))
    joint = {b: params.buyer_logit_shift.get(b, 0.0) + AMBIGUITY["all_buyers_logit"] for b in buyers}
    worlds.append(params.with_updates(buyer_logit_shift=joint, label="all buyers a third less punctual"))
    worlds.append(params.with_updates(ship_scale=params.ship_scale * AMBIGUITY["ship_scale"], label="orders ship at 85% of stated confidence"))
    return worlds


class IntelligenceCore:
    """Builds state, enumerates allowed plans, scores them on shared paths, chooses under the goal."""

    def __init__(self, params: Optional[sim.WorldParams] = None, n_paths: int = 2000, seed: int = 20261019,
                 top_invoices: int = 8) -> None:
        self.params = params or sim.WorldParams()
        self.n_paths = n_paths
        self.seed = seed
        self.top_invoices = top_invoices

    # ------------------------------------------------------------ state
    def build_state(self, inputs: CoreInputs, paths: sim.Paths, no_action: Dict[str, Any], goal_id: str) -> Dict[str, Any]:
        f = forecast_13w(inputs.forecast_inputs)
        recv = inputs.forecast_inputs.receivables
        total = sum(float(r.amount.to_usd()) for r in recv) or 1.0
        by_buyer: Dict[str, float] = {}
        for r in recv:
            by_buyer[r.buyer_name] = by_buyer.get(r.buyer_name, 0.0) + float(r.amount.to_usd())
        top_buyer, top_usd = max(by_buyer.items(), key=lambda kv: kv[1]) if by_buyer else ("-", 0.0)
        return {
            "schema": STATE_SCHEMA,
            "case_id": inputs.case_id,
            "as_of": inputs.as_of.isoformat(),
            "goal": goal_id,
            "cash_today_usd": float(inputs.forecast_inputs.opening_cash_usd),
            "buffer_usd": float(inputs.forecast_inputs.buffer_usd),
            "base_case": {"first_negative_week": f.first_shortfall_week,
                          "shortfall_usd": float(f.shortfall_usd) if f.shortfall_usd is not None else 0.0,
                          "min_closing_usd": float(f.min_closing_usd),
                          "closing_by_week": [float(w.closing) for w in f.weeks]},
            "risk_without_action": {k: no_action[k] for k in ("p_no_negative_week", "p_negative_by_week", "expected_shortfall_usd",
                                                              "shortfall_p95_usd", "shortfall_cvar95_usd", "trough_p5_usd", "earliest_gap_week_p10",
                                                              "closing_p10_by_week", "closing_p50_by_week", "closing_p90_by_week")},
            "receivables": {"open_usd": round(total, 2), "count": len(recv), "top_buyer": top_buyer,
                            "top_buyer_share_pct": round(top_usd / total * 100, 1),
                            "pledgeable": [{"ref": p.ref, "buyer": p.buyer, "usd": round(p.usd, 2), "due_date": p.due_date.isoformat()}
                                           for p in sorted(inputs.pledgeable, key=lambda p: -p.usd)],
                            "excluded": inputs.excluded},
            "confirmed_orders": {"count": len(inputs.forecast_inputs.confirmed_orders),
                                 "usd": round(sum(float(o.amount.to_usd()) for o in inputs.forecast_inputs.confirmed_orders), 2),
                                 "pledgeable": False},
            "constraints": {"allowed_actions": list(POLICY["allowed_actions"]), "max_packs_per_plan": POLICY["max_packs_per_plan"],
                            "over_borrowing_cap_usd": round(POLICY["over_borrowing_factor"] * max(no_action["shortfall_p95_usd"], 1.0), 2),
                            "every_pack_needs": "Director OTP; the Core cannot submit, pay or change payees"},
            "world_model": paths.params.version,
        }

    # -------------------------------------------------------- candidates
    def candidates(self, inputs: CoreInputs, draw_weeks: Sequence[int]) -> List[List[Dict[str, Any]]]:
        start = inputs.forecast_inputs.start_date
        plans: List[List[Dict[str, Any]]] = [[]]
        deposit = next((d for d in inputs.forecast_inputs.deposits if d.adjustable), None)
        cut = [{"type": "deposit_cut", "ref": deposit.ref, "week": deposit.week, "new_pct": 15}] if deposit and float(deposit.pct) > 15 else []
        for week in draw_weeks:
            draw_day = _week_start(start, week)
            usable = [p for p in sorted(inputs.pledgeable, key=lambda p: -p.usd)
                      if (p.due_date - draw_day).days >= POLICY["min_days_to_due_after_draw"]
                      and p.usd >= inputs.factoring["min_invoice_usd"]
                      and p.p_on_time >= POLICY["min_p_on_time_to_pledge"]][: self.top_invoices]
            funding: List[List[Dict[str, Any]]] = []
            for k in (1, 2, 3):
                for combo in itertools.combinations(usable[: (len(usable) if k < 3 else 5)], k):
                    funding.append([factor_action(p, inputs.factoring, start, week) for p in combo])
            if inputs.loan:
                funding.append([loan_action(inputs.loan, week)])
                for k in (1, 2):
                    for combo in itertools.combinations(usable[:5], k):
                        funding.append([loan_action(inputs.loan, week)] + [factor_action(p, inputs.factoring, start, week) for p in combo])
            for f in funding:
                plans.append(f)
                if cut:
                    plans.append(f + cut)
        if cut:
            plans.append(cut)
        unique, seen = [], set()
        for p in plans:
            key = plan_id(p)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    # ------------------------------------------------------------ choose
    def plan(self, inputs: CoreInputs, goal_id: str = "keep_cash_positive",
             baseline_actions: Optional[List[Dict[str, Any]]] = None,
             extra_proposals: Sequence[List[Dict[str, Any]]] = (),
             memory: Optional["CaseMemory"] = None, min_probability: Optional[float] = None,
             incumbent: Optional[List[Dict[str, Any]]] = None, objective: str = DEFAULT_OBJECTIVE) -> CoreResult:
        """Rank every allowed plan and choose one. ``incumbent`` is the plan already in force: it is kept
        when the new best is better only by simulation noise, so the SME is not asked to switch plans for nothing."""
        if goal_id not in GOALS:
            raise ValueError(f"unknown goal {goal_id!r}; goals are fixed templates: {sorted(GOALS)}")
        if objective not in OBJECTIVES:
            raise ValueError(f"objective must be one of {OBJECTIVES}")
        goal = dict(GOALS[goal_id], id=goal_id, objective=objective)
        if min_probability is not None:
            if min_probability not in ALLOWED_PROBABILITIES:
                raise ValueError(f"min_probability must be one of {ALLOWED_PROBABILITIES}")
            goal["min_probability"] = min_probability
        paths = sim.sample(inputs.forecast_inputs, self.params, n=self.n_paths, seed=self.seed)
        no_action = sim.evaluate(paths)
        robust_paths: List[Any] = []
        if objective == "robust":
            buyers = sorted({i.buyer_id for i in sim.items_from_inputs(inputs.forecast_inputs)})
            # common random numbers: same seed in every world, so differences come from the world, not the draw
            robust_paths = [(w.label, sim.sample(inputs.forecast_inputs, w, n=self.n_paths, seed=self.seed))
                            for w in ambiguity_worlds(self.params, buyers)[1:]]
        state = self.build_state(inputs, paths, no_action, goal_id)
        base_week = state["base_case"]["first_negative_week"]
        risk_week = next((i + 1 for i, p in enumerate(no_action["p_negative_by_week"]) if p >= 0.10), None)
        draw_weeks = sorted({w for w in (risk_week, base_week) if w} | ({max(1, risk_week - DRAW_LEAD)} if risk_week and DRAW_LEAD else set()))
        floor = 0.0 if goal["floor"] == "zero" else float(inputs.forecast_inputs.buffer_usd)

        def score(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
            closing = sim.closings(paths, actions)
            summary = sim.summarize(paths, closing)
            p_goal = float((closing.min(axis=1) >= floor).mean())
            worst, worst_label = p_goal, "nominal"
            for label, wp in robust_paths:
                pw = float((sim.closings(wp, actions).min(axis=1) >= floor).mean())
                if pw < worst:
                    worst, worst_label = pw, label
            return {"plan_id": plan_id(actions), "description": describe(actions), "actions": actions,
                    "p_goal": round(p_goal, 4), "p_goal_worst_case": round(worst, 4), "worst_world": worst_label, "p_no_negative_week": summary["p_no_negative_week"],
                    "expected_shortfall_usd": summary["expected_shortfall_usd"], "trough_p5_usd": summary["trough_p5_usd"],
                    "shortfall_cvar95_usd": summary["shortfall_cvar95_usd"],
                    "p_shortfall": round(1 - summary["p_no_negative_week"], 4),
                    "risk_adjusted_cost_usd": round(sim.expected_cost(paths, actions) + CVAR_WEIGHT * summary["shortfall_cvar95_usd"], 2),
                    "cost_usd": sim.expected_cost(paths, actions), "quoted_cost_usd": plan_cost(actions), "funding_usd": plan_funding(actions), "packs": plan_packs(actions),
                    "needs_supplier_agreement": any(a["type"] == "deposit_cut" for a in actions),
                    "closing_p10_by_week": summary["closing_p10_by_week"], "closing_p50_by_week": summary["closing_p50_by_week"],
                    "p_negative_by_week": summary["p_negative_by_week"]}

        ranked, rejected = [], []
        for actions in list(self.candidates(inputs, draw_weeks)) + [list(p) for p in extra_proposals]:
            problems = validate_plan(actions, inputs, no_action["shortfall_p95_usd"])
            if problems:
                rejected.append({"plan_id": plan_id(actions), "description": describe(actions), "violations": problems})
                continue
            ranked.append(score(actions))
        target = goal["min_probability"]
        pkey = "p_goal_worst_case" if objective == "robust" else "p_goal"
        meets = [r for r in ranked if r[pkey] >= target]
        money = "risk_adjusted_cost_usd" if objective in ("risk_adjusted", "robust") else "cost_usd"
        key_cost = lambda r: (r[money], r["packs"], r["needs_supplier_agreement"], r["plan_id"])
        best_p = max(r[pkey] for r in ranked)
        # Differences inside two standard errors of the simulation are noise: do not pay for them.
        tolerance = 2 * math.sqrt(max(best_p * (1 - best_p), 1e-6) / self.n_paths)
        if meets:
            chosen = min(meets, key=key_cost)
            status = "GOAL_MET"
        else:
            chosen = min((r for r in ranked if r[pkey] >= best_p - tolerance), key=key_cost)
            status = "GOAL_NOT_REACHABLE"
        kept = None
        if incumbent:
            current = rebuild_actions(incumbent, inputs)
            if current is not None and not validate_plan(current, inputs, no_action["shortfall_p95_usd"]):
                inc = next((r for r in ranked if r["plan_id"] == plan_id(current)), None) or score(current)
                same_status = (inc["p_goal"] >= target) == (status == "GOAL_MET")
                if inc["plan_id"] != chosen["plan_id"] and same_status and inc["p_goal"] >= chosen["p_goal"] - tolerance \
                        and inc["cost_usd"] <= chosen["cost_usd"] * 1.10 + 50:
                    kept = {"kept": True, "instead_of": chosen["description"],
                            "reason": f"The plan in force is within simulation noise ({tolerance:.1%}) of the new best and costs at most 10% more; "
                                      "switching would create new packs and approvals for no measurable gain."}
                    if inc not in ranked:
                        ranked.append(inc)
                    chosen = inc
                elif inc["plan_id"] == chosen["plan_id"]:
                    kept = {"kept": True, "instead_of": None, "reason": "The plan in force is still the best allowed plan."}
                else:
                    kept = {"kept": False, "reason": f"The plan in force reaches {inc['p_goal']:.0%}; the new plan reaches {chosen['p_goal']:.0%}."}
        for r in ranked:
            r["verdict"] = self._verdict(r, chosen, target)
        ranked.sort(key=lambda r: (-(r["p_goal"] >= target), key_cost(r)) if r["p_goal"] >= target else (1, -r["p_goal"], r["cost_usd"]))
        baseline = score(baseline_actions) if baseline_actions is not None else {}
        chosen = dict(chosen, why=self._why(chosen, baseline, goal, status, ranked, no_action), incumbent=kept)
        similar = memory.similar(self.features(state)) if memory else []
        state["considered"] = {"plans_scored": len(ranked), "plans_refused": len(rejected), "plans_meeting_goal": len(meets),
                               "draw_weeks": draw_weeks, "noise_tolerance": round(tolerance, 4)}
        feasibility = self.feasibility(inputs, paths, no_action, chosen, floor, target, draw_weeks)
        return CoreResult(state=state, chosen=chosen, ranked=ranked[:12], rejected=rejected[:20], baseline=baseline, goal=goal,
                          feasibility=feasibility, status=status, world_model={"version": self.params.version, "label": self.params.label,
                                                      "params": self.params.as_dict(), "paths": self.n_paths, "seed": self.seed},
                          memory=similar)

    def stress_test(self, inputs: CoreInputs, actions: List[Dict[str, Any]], goal_id: str = "keep_cash_positive") -> List[Dict[str, Any]]:
        """P(goal) of one plan in the nominal world and in each adverse world of the ambiguity set (same random numbers)."""
        floor = 0.0 if GOALS[goal_id]["floor"] == "zero" else float(inputs.forecast_inputs.buffer_usd)
        buyers = sorted({i.buyer_id for i in sim.items_from_inputs(inputs.forecast_inputs)})
        out = []
        for w in ambiguity_worlds(self.params, buyers):
            paths = sim.sample(inputs.forecast_inputs, w, n=self.n_paths, seed=self.seed)
            out.append({"world": "nominal" if w is self.params else w.label,
                        "p_goal": round(float((sim.closings(paths, actions).min(axis=1) >= floor).mean()), 4)})
        return out

    def feasibility(self, inputs: CoreInputs, paths: sim.Paths, no_action: Dict[str, Any], chosen: Dict[str, Any],
                    floor: float, target: float, draw_weeks: Sequence[int]) -> Dict[str, Any]:
        """Why the goal is or is not reachable. Probes relax one limit at a time on the same scenarios; they are
        diagnostics only, never offered as plans, and the policy limits themselves do not change.

        The key bound is closed-form: free cash X added in week 1 lifts every week of every scenario by X, so the
        least X that reaches the goal is the goal-quantile of (floor - lowest balance without action). No financing
        that arrives later, costs money or is repaid inside the horizon can do better with the same amount."""
        trough = sim.closings(paths).min(axis=1)
        need = float(np.quantile(np.maximum(0.0, floor - trough), target))
        cap = POLICY["over_borrowing_factor"] * max(no_action["shortfall_p95_usd"], 1.0)
        p_free_cap = float((trough + cap >= floor).mean())
        start = inputs.forecast_inputs.start_date
        week = min(draw_weeks) if draw_weeks else 1
        usable = [p for p in inputs.pledgeable
                  if (p.due_date - _week_start(start, week)).days >= POLICY["min_days_to_due_after_draw"]
                  and p.usd >= inputs.factoring["min_invoice_usd"] and p.p_on_time >= POLICY["min_p_on_time_to_pledge"]]
        everything = [factor_action(p, inputs.factoring, start, week) for p in usable] + ([loan_action(inputs.loan, week)] if inputs.loan else [])
        eligible_usd = plan_funding(everything)

        def p_of(actions: Sequence[Dict[str, Any]]) -> float:
            return round(float((sim.closings(paths, actions).min(axis=1) >= floor).mean()), 4)

        # Same chosen plan drawn in week 1 (only actions still valid that early).
        early = []
        for a in chosen["actions"]:
            if a["type"] == "factor":
                p = next((x for x in inputs.pledgeable if x.ref == a["ref"]), None)
                if p is not None:
                    early.append(factor_action(p, inputs.factoring, start, 1))
            elif a["type"] == "loan" and inputs.loan:
                early.append(loan_action(inputs.loan, 1))
            else:
                early.append(a)
        # More packs, same cap: the loan first, then the safest larger invoices until the cap is reached.
        within: List[Dict[str, Any]] = [loan_action(inputs.loan, week)] if inputs.loan else []
        for p in sorted(usable, key=lambda x: (-x.p_on_time, -x.usd)):
            a = factor_action(p, inputs.factoring, start, week)
            if plan_funding(within + [a]) <= cap:
                within.append(a)
        same_cash = plan_funding(chosen["actions"])
        p_free_same = float((trough + same_cash >= floor).mean())
        probes = [
            {"id": "more_packs_within_cap", "limit": "packs per plan",
             "change": f"{plan_packs(within)} packs (USD {plan_funding(within):,.0f}) in week {week}, still inside the cap",
             "p_goal": p_of(within) if within else None, "packs": plan_packs(within)},
            {"id": "free_cash_at_cap", "limit": "upper bound within the over-borrowing cap",
             "change": f"USD {cap:,.0f} of free cash in week 1, never repaid", "p_goal": round(p_free_cap, 4)},
            {"id": "all_sources", "limit": "packs per plan and over-borrowing cap",
             "change": f"every eligible source at once ({len(everything)} packs, USD {eligible_usd:,.0f}) in week {week}",
             "p_goal": p_of(everything) if everything else None},
            {"id": "draw_week_1", "limit": "timing of the draw",
             "change": "the recommended plan drawn in week 1", "p_goal": p_of(early) if early else None},
        ]
        # Timing: on scenarios that still fail, does cash go negative before any funding arrives?
        closing = sim.closings(paths, chosen["actions"])
        fails = closing.min(axis=1) < floor
        first_draw = min((int(a["week"]) for a in chosen["actions"] if a["type"] in ("factor", "loan")), default=None)
        breach_week = np.argmax(closing < floor, axis=1) + 1
        before_draw = float((breach_week[fails] < first_draw).mean()) if first_draw and fails.any() else 0.0
        binding: List[Dict[str, str]] = []
        if need > cap:
            binding.append({"limit": "over_borrowing_cap", "text": f"Reaching {target:.0%} needs about USD {need:,.0f} of cash from week 1; "
                            f"the policy caps total funding at USD {cap:,.0f} (1.5 x the 95th-percentile shortfall)."})
        if need > eligible_usd:
            binding.append({"limit": "eligible_sources", "text": f"All eligible invoices and the bridge loan together give USD {eligible_usd:,.0f}, "
                            f"less than the USD {need:,.0f} needed."})
        more = probes[0]
        if more["p_goal"] is not None and more["packs"] > POLICY["max_packs_per_plan"] and more["p_goal"] >= target > chosen["p_goal"]:
            binding.append({"limit": "packs_per_plan", "text": f"With {more['packs']} packs inside the same cap the goal would be reached "
                            f"({more['p_goal']:.0%}); the policy allows {POLICY['max_packs_per_plan']} packs, each a separate approval."})
        if before_draw >= 0.25:
            binding.append({"limit": "timing", "text": f"On {before_draw:.0%} of the scenarios that still fail, cash goes negative before the first "
                            f"draw (week {first_draw})."})
        if same_cash > 0 and p_free_same - chosen["p_goal"] >= 0.05:
            binding.append({"limit": "repayment_inside_horizon", "text": f"The same USD {same_cash:,.0f} as free cash from week 1 would reach "
                            f"{p_free_same:.0%}, not {chosen['p_goal']:.0%}: factored invoices pay the factor and the loan falls due inside "
                            "the 13 weeks, so part of the cash leaves again before the low point."})
        if chosen["p_goal"] < target and p_free_cap >= target and not binding:
            allp = probes[2]["p_goal"]
            binding.append({"limit": "combined_limits", "text": "No single limit explains it on its own: only relaxing several together "
                            f"(more packs and more funding at once{f', {allp:.0%} with every eligible source' if allp is not None else ''}) reaches the goal."})
        if chosen["p_goal"] >= target:
            verdict = "REACHABLE"
        elif p_free_cap < target:
            verdict = "NOT_REACHABLE_WITH_FINANCING"
        else:
            verdict = "LIMITED_BY_POLICY_OR_SOURCES"
        outside = [] if verdict == "REACHABLE" else [
            "Ask the slowest buyers to pay on time or earlier (collections; needs the buyer to agree).",
            "Defer or cut spending that is not committed (needs the Director).",
            "Arrange longer-term funding than a 13-week bridge (needs a lender's credit decision).",
        ]
        return {"verdict": verdict, "goal_probability": target, "best_allowed_p_goal": chosen["p_goal"],
                "cash_needed_week1_usd": round(need, 2), "over_borrowing_cap_usd": round(cap, 2), "eligible_sources_usd": round(eligible_usd, 2),
                "failing_paths_negative_before_first_draw": round(before_draw, 4), "same_cash_free_p_goal": round(p_free_same, 4), "binding": binding, "probes": probes,
                "outside_financing": outside,
                "note": "Probes relax one limit on the same scenarios to find what binds. They are diagnostics, not plans: the limits stay."}

    @staticmethod
    def _verdict(r: Dict[str, Any], chosen: Dict[str, Any], target: float) -> str:
        """One line on why this plan was or was not chosen."""
        if r["plan_id"] == chosen["plan_id"]:
            return "Chosen."
        dp = (r["p_goal"] - chosen["p_goal"]) * 100
        dc = r["cost_usd"] - chosen["cost_usd"]
        if r["plan_id"] == "no_action":
            return f"Doing nothing keeps the goal on only {r['p_goal']:.0%} of paths."
        if r["p_goal"] < target and dp < -0.5:
            return (f"Short of the {target:.0%} goal ({r['p_goal']:.0%}); "
                    + (f"USD {-dc:,.0f} cheaper, but {-dp:.0f} points less safe." if dc < -0.5 else
                       f"same cost, {-dp:.0f} points less safe." if dc <= 0.5 else f"{-dp:.0f} points less safe and USD {dc:,.0f} dearer."))
        if dc > 0.5:
            return f"About as safe ({dp:+.0f} points) but USD {dc:,.0f} dearer."
        if r["packs"] > chosen["packs"]:
            return "Same cost and safety, more packs to approve."
        if r["needs_supplier_agreement"] and not chosen["needs_supplier_agreement"]:
            return "Same result, but depends on the supplier agreeing."
        return "Equivalent within simulation noise; the chosen plan wins the tie-break (cost, packs, supplier)."

    @staticmethod
    def features(state: Dict[str, Any]) -> Dict[str, float]:
        return {"shortfall_usd": state["base_case"]["shortfall_usd"],
                "first_negative_week": float(state["base_case"]["first_negative_week"] or 14),
                "p_no_negative_week": state["risk_without_action"]["p_no_negative_week"],
                "shortfall_p95_usd": state["risk_without_action"]["shortfall_p95_usd"],
                "top_buyer_share_pct": state["receivables"]["top_buyer_share_pct"],
                "pledgeable_usd": sum(p["usd"] for p in state["receivables"]["pledgeable"])}

    @staticmethod
    def _why(chosen: Dict[str, Any], baseline: Dict[str, Any], goal: Dict[str, Any], status: str,
             ranked: List[Dict[str, Any]], no_action: Dict[str, Any]) -> List[str]:
        target = goal["min_probability"]
        lines = [f"Without action, {no_action['p_no_negative_week']:.0%} of simulated paths keep every week at or above zero."]
        if status == "GOAL_MET":
            lines.append(f"Cheapest allowed plan that reaches the goal ({goal['label'].lower()} in at least {target:.0%} of paths): "
                         f"{chosen['description']}, {chosen['p_goal']:.0%} of paths, expected cost USD {chosen['cost_usd']:,.2f}.")
        else:
            lines.append(f"No allowed plan reaches {target:.0%}. The closest is {chosen['description']} at {chosen['p_goal']:.0%}; "
                         "the rest needs a decision outside financing (costs, sales, longer-term funding).")
        if baseline:
            lines.append(f"The fixed workflow ({baseline['description']}) reaches {baseline['p_goal']:.0%} at USD {baseline['cost_usd']:,.2f}: "
                         "it is sized for the expected path only.")
        cheaper = [r for r in ranked if r["cost_usd"] < chosen["cost_usd"] and r["plan_id"] != "no_action"]
        if cheaper and status == "GOAL_MET":
            c = min(cheaper, key=lambda r: -r["p_goal"])
            lines.append(f"Cheaper plans fall short: best of them is {c['description']} at {c['p_goal']:.0%}.")
        if chosen.get("needs_supplier_agreement"):
            lines.append("Part of the plan needs the supplier to agree; the simulation assumes it succeeds on some paths only.")
        return lines


def rebuild_actions(actions: Sequence[Dict[str, Any]], inputs: CoreInputs) -> Optional[List[Dict[str, Any]]]:
    """Re-price a plan's actions on new inputs (same invoices, weeks and levers). None if an invoice is gone."""
    by_ref = {p.ref: p for p in inputs.pledgeable}
    out: List[Dict[str, Any]] = []
    for a in actions:
        if a["type"] == "factor":
            if a["ref"] not in by_ref:
                return None
            out.append(factor_action(by_ref[a["ref"]], inputs.factoring, inputs.forecast_inputs.start_date, int(a["week"])))
        elif a["type"] == "loan":
            if inputs.loan is None:
                return None
            out.append(loan_action(inputs.loan, int(a["week"])))
        else:
            out.append(dict(a))
    return out


# ---------------------------------------------------------- fixed workflow
def fixed_workflow_actions(inputs: CoreInputs) -> List[Dict[str, Any]]:
    """What the original Autopilot does: factor the largest eligible invoice in the first base-case gap week."""
    f = forecast_13w(inputs.forecast_inputs)
    if not f.first_shortfall_week or not inputs.pledgeable:
        return []
    nominee = max(inputs.pledgeable, key=lambda p: p.usd)
    return [factor_action(nominee, inputs.factoring, inputs.forecast_inputs.start_date, f.first_shortfall_week)]


# ---------------------------------------------------------------- memory
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CaseMemory:
    """Append-only, hash-chained JSONL of plans (with predictions) and outcomes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def records(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, record: Dict[str, Any]) -> Dict[str, Any]:
        rows = self.records()
        prev = rows[-1]["hash"] if rows else "0" * 64
        body = dict(record, prev_hash=prev)
        body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, sort_keys=True, default=str) + "\n")
        return body

    def verify(self) -> bool:
        prev = "0" * 64
        for row in self.records():
            claimed = row.get("hash")
            body = {k: v for k, v in row.items() if k != "hash"}
            if body.get("prev_hash") != prev or hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest() != claimed:
                return False
            prev = claimed
        return True

    def remember_plan(self, run_id: str, result: CoreResult, source: str = "LIVE") -> Dict[str, Any]:
        c = result.chosen
        return self._append({"type": "plan", "run_id": run_id, "ts": _now(), "source": source, "case_id": result.state["case_id"],
                             "features": IntelligenceCore.features(result.state), "plan_id": c["plan_id"], "description": c["description"],
                             "actions": c["actions"], "predicted": {"p_goal": c["p_goal"], "cost_usd": c["cost_usd"],
                                                                   "expected_shortfall_usd": c["expected_shortfall_usd"]},
                             "goal": result.goal["id"], "world_model": result.world_model["version"], "status": result.status})

    def remember_outcome(self, run_id: str, outcome: Dict[str, Any], source: str = "SIMULATED") -> Dict[str, Any]:
        return self._append({"type": "outcome", "run_id": run_id, "ts": _now(), "source": source, **outcome})

    def episodes(self) -> List[Dict[str, Any]]:
        """Plans joined with their outcomes."""
        rows = self.records()
        outcomes = {r["run_id"]: r for r in rows if r["type"] == "outcome"}
        return [dict(p, outcome=outcomes[p["run_id"]]) for p in rows if p["type"] == "plan" and p["run_id"] in outcomes]

    def similar(self, features: Dict[str, float], k: int = 3) -> List[Dict[str, Any]]:
        eps = self.episodes()
        if not eps:
            return []
        keys = sorted(features)
        mat = np.array([[e["features"].get(key, 0.0) for key in keys] for e in eps], dtype=float)
        scale = mat.std(axis=0)
        scale[scale == 0] = 1.0
        target = np.array([features[key] for key in keys], dtype=float)
        dist = np.sqrt((((mat - target) / scale) ** 2).sum(axis=1))
        out = []
        for i in np.argsort(dist)[:k]:
            e = eps[int(i)]
            o = e["outcome"]
            out.append({"run_id": e["run_id"], "source": e["source"], "distance": round(float(dist[i]), 2), "plan": e["description"],
                        "predicted_p_goal": e["predicted"]["p_goal"], "goal_met": o["goal_met"], "trough_usd": o["trough_usd"],
                        "primary_cause": o["attribution"]["primary_cause"], "lesson": o["attribution"]["lesson"]})
        return out


# ------------------------------------------------------------ attribution
CAUSES = {
    "collections_timing": "Buyers paid later than the model expected",
    "order_slippage": "Confirmed orders shipped later than planned",
    "cost_overrun": "Costs were higher than planned",
    "funding_too_small": "The plan's funding was smaller than the gap that occurred",
    "objective_too_narrow": "The plan was sized for the first gap only; a later week went negative",
    "none": "Outcome within plan",
}


def attribute_outcome(inputs: CoreInputs, actions: Sequence[Dict[str, Any]], realised: sim.Paths, goal_floor: float = 0.0) -> Dict[str, Any]:
    """Explain one realised path against the expected path. Contributions are in USD at the trough week."""
    expected = forecast_13w(inputs.forecast_inputs)
    exp_close = np.array([float(w.closing) for w in expected.weeks])
    closing = sim.closings(realised, actions)[0]
    trough_week = int(closing.argmin()) + 1
    t = trough_week
    # Expected cumulative inflow to the trough week, split invoices / orders, from the deterministic view.
    exp_items = {}
    for item in realised.items:
        if item.kind == "order":
            exp = item.usd * item.ship_confidence
        else:
            exp = item.usd
        on = exp * item.p_on_time if item.promised_week is None else exp
        late = exp - on
        exp_items[item.ref] = (on if item.due_week <= t else 0.0) + (late if item.due_week + sim.LATE_PAYMENT_DELAY_WEEKS <= t else 0.0)
    real_items = {item.ref: float(realised.amount[0, j]) if realised.pay_week[0, j] <= t else 0.0 for j, item in enumerate(realised.items)}
    inv_gap = sum(real_items[i.ref] - exp_items[i.ref] for i in realised.items if i.kind == "invoice")
    ord_gap = sum(real_items[i.ref] - exp_items[i.ref] for i in realised.items if i.kind == "order")
    base_out = sim.recurring_outflows(inputs.forecast_inputs)
    exp_out = base_out[:t].sum() + sum(realised.deposit_usd[r] for r, w in realised.deposit_week.items() if w <= t)
    cost_gap = -(float(realised.outflow[0, :t].sum()) - exp_out)
    contributions = {"collections_timing": round(inv_gap, 2), "order_slippage": round(ord_gap, 2), "cost_overrun": round(cost_gap, 2)}
    goal_met = bool(closing.min() >= goal_floor)
    funded_weeks = [a["week"] for a in actions if a["type"] in ("factor", "loan")]
    primary = "none"
    if not goal_met:
        worst = min(contributions, key=contributions.get)
        if contributions[worst] < 0 and -contributions[worst] >= 0.25 * abs(float(closing.min())):
            primary = worst
        elif funded_weeks and trough_week > max(funded_weeks) + 1 and exp_close[trough_week - 1] < 0:
            primary = "objective_too_narrow"
        else:
            primary = "funding_too_small"
        if primary in ("collections_timing", "order_slippage", "cost_overrun") and plan_funding(actions) < -float(closing.min()) * 0.5:
            pass  # the shock dominates; funding size is secondary
    lessons = {
        "collections_timing": "Treat this buyer mix as slower: the learner should lower on-time probabilities, then re-plan.",
        "order_slippage": "Count confirmed orders at a lower shipment confidence until they ship.",
        "cost_overrun": "Hold a larger buffer or plan the cost line with a margin.",
        "funding_too_small": "Size funding for bad paths (the 90th percentile), not for the expected path.",
        "objective_too_narrow": "Judge plans on all 13 weeks, not on the first negative week.",
        "none": "No change needed.",
    }
    return {"goal_met": goal_met, "trough_usd": round(float(closing.min()), 2), "trough_week": trough_week,
            "closing_by_week": [round(float(x), 2) for x in closing], "contributions_usd": contributions,
            "attribution": {"primary_cause": primary, "label": CAUSES[primary], "lesson": lessons[primary]}}


# --------------------------------------------------------------- learner
def _loglik_items(items: Sequence[Dict[str, Any]], params: sim.WorldParams) -> float:
    """Mean log-likelihood of observed on-time and shipped outcomes under ``params`` (slowdowns marginalised)."""
    total, n = 0.0, 0
    for it in items:
        if it["kind"] == "invoice" or it.get("ship_observed"):  # payment timing is observed only once shipped
            base = float(sim._sigmoid(sim._logit(np.array([it["p_on_time"]])) + params.buyer_logit_shift.get(it["buyer_id"], 0.0))[0])
            p = (1 - params.slowdown_prob) * base + params.slowdown_prob * base * params.slowdown_p_mult
            p = min(max(p, 1e-4), 1 - 1e-4)
            y = it["on_time"]
            total += math.log(p if y else 1 - p)
            n += 1
        if it["kind"] == "order" and it.get("ship_observed") is not None:
            q = min(max(it["ship_confidence"] * params.ship_scale, 1e-4), 1 - 1e-4)
            total += math.log(q if it["ship_observed"] else 1 - q)
            n += 1
    return total / max(n, 1)


class WorldModelLearner:
    """Estimates world-model corrections from outcomes. Offline only; the result is a proposal."""

    MIN_ITEMS = 60
    MIN_GAIN = 0.002  # mean log-likelihood per observation, leave-one-episode-out

    def __init__(self, prior: sim.WorldParams, shrinkage: float = 1.0) -> None:
        self.prior = prior
        self.shrinkage = shrinkage  # Gaussian prior precision on each buyer's logit shift

    def fit(self, episodes: Sequence[Sequence[Dict[str, Any]]]) -> sim.WorldParams:
        items = [it for ep in episodes for it in ep]
        shifts: Dict[str, float] = {}
        for buyer in sorted({it["buyer_id"] for it in items}):
            obs = [it for it in items if it["buyer_id"] == buyer and (it["kind"] == "invoice" or it.get("ship_observed"))]
            if len(obs) < 8:
                continue
            s = self.prior.buyer_logit_shift.get(buyer, 0.0)
            for _ in range(50):  # Newton on the penalised log-likelihood of the marginal on-time probability
                g, h = -self.shrinkage * s, -self.shrinkage
                for it in obs:
                    z = float(sim._logit(np.array([it["p_on_time"]]))[0]) + s
                    b = 1 / (1 + math.exp(-z))
                    m = (1 - self.prior.slowdown_prob) + self.prior.slowdown_prob * self.prior.slowdown_p_mult
                    p = min(max(m * b, 1e-6), 1 - 1e-6)
                    dp = m * b * (1 - b)
                    d2p = m * b * (1 - b) * (1 - 2 * b)
                    y = 1.0 if it["on_time"] else 0.0
                    g += y * dp / p - (1 - y) * dp / (1 - p)
                    h += y * (d2p * p - dp * dp) / p ** 2 - (1 - y) * (d2p * (1 - p) + dp * dp) / (1 - p) ** 2
                step = g / h if h < 0 else 0.0
                s -= step
                if abs(step) < 1e-6:
                    break
            shifts[buyer] = round(max(-3.0, min(3.0, s)), 3)
        orders = [it for it in items if it["kind"] == "order" and it.get("ship_observed") is not None]
        ship_scale = self.prior.ship_scale
        if len(orders) >= 8:
            prior_n = 10.0
            shipped = sum(1 for it in orders if it["ship_observed"])
            expected = sum(it["ship_confidence"] for it in orders)
            ship_scale = round((shipped + prior_n * self.prior.ship_scale) / (expected + prior_n), 3)
        return self.prior.with_updates(buyer_logit_shift=shifts, ship_scale=ship_scale, label="learned (pending review)")

    def evaluate(self, episodes: Sequence[Sequence[Dict[str, Any]]], current: sim.WorldParams) -> Dict[str, Any]:
        """Leave-one-episode-out: fit on the others, score the held-out episode, for both parameter sets."""
        n_items = sum(len(ep) for ep in episodes)
        if len(episodes) < 3 or n_items < self.MIN_ITEMS:
            return {"accepted": False, "reason": f"Not enough outcomes ({len(episodes)} episodes, {n_items} observations)",
                    "episodes": len(episodes), "observations": n_items}
        cur, cand = [], []
        for k in range(len(episodes)):
            train = [ep for i, ep in enumerate(episodes) if i != k]
            fitted = WorldModelLearner(current, self.shrinkage).fit(train)
            cur.append(_loglik_items(episodes[k], current))
            cand.append(_loglik_items(episodes[k], fitted))
        gain = float(np.mean(cand) - np.mean(cur))
        wins = sum(1 for a, b in zip(cand, cur) if a > b)
        accepted = gain >= self.MIN_GAIN and wins >= math.ceil(len(episodes) / 2)
        return {"accepted": accepted, "episodes": len(episodes), "observations": n_items,
                "loglik_current": round(float(np.mean(cur)), 4), "loglik_candidate": round(float(np.mean(cand)), 4),
                "gain_per_observation": round(gain, 4), "held_out_wins": wins,
                "reason": ("Candidate predicts held-out outcomes better" if accepted else
                           "Candidate does not beat the active model on held-out episodes")}


class ModelRegistry:
    """Active world-model parameters, the pending proposal, and who approved what."""

    def __init__(self, path: Path, default: Optional[sim.WorldParams] = None) -> None:
        self.path = Path(path)
        self.default = default or sim.WorldParams()

    def _read(self) -> Dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"active": self.default.as_dict(), "pending": None, "history": [
            {"version": self.default.version, "label": self.default.label, "ts": None, "approved_by": "default prior", "metrics": None}]}

    def _write(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def active(self) -> sim.WorldParams:
        return sim.WorldParams(**self._read()["active"])

    def status(self) -> Dict[str, Any]:
        data = self._read()
        active = sim.WorldParams(**data["active"])
        return {"active_version": active.version, "active": data["active"], "pending": data["pending"], "history": data["history"]}

    def propose(self, candidate: sim.WorldParams, metrics: Dict[str, Any], proposed_by: str) -> Dict[str, Any]:
        data = self._read()
        data["pending"] = {"params": candidate.as_dict(), "version": candidate.version, "metrics": metrics,
                           "proposed_by": proposed_by, "ts": _now()}
        self._write(data)
        return data["pending"]

    def decide(self, approve: bool, reviewer: str, note: str = "") -> Dict[str, Any]:
        data = self._read()
        pending = data.get("pending")
        if not pending:
            raise ValueError("No pending model update")
        if approve and not pending["metrics"].get("accepted"):
            raise PermissionError("The offline evaluation did not accept this candidate; it cannot be activated")
        if approve and reviewer == pending.get("proposed_by"):
            raise PermissionError("Segregation of duties: the proposer cannot approve the model update")
        entry = {"version": pending["version"], "label": "learned" if approve else "rejected", "ts": _now(),
                 "approved_by" if approve else "rejected_by": reviewer, "metrics": pending["metrics"], "note": note}
        if approve:
            params = dict(pending["params"], label="learned")
            data["active"] = params
        data["history"].append(entry)
        data["pending"] = None
        self._write(data)
        return entry


# ------------------------------------------------------- simulated episodes
HIDDEN_TEST_WORLD = sim.WorldParams(
    buyer_logit_shift={"B-US-01": -1.2, "B-US-02": -0.4},
    ship_scale=0.8,
    label="hidden test world (simulated): Oakline pays later, orders slip more than stated",
)


def perturb_inputs(inputs: ForecastInputs, rng: np.random.Generator, noise: float = 0.15) -> ForecastInputs:
    """A different but similar quarter: amounts, timing and opening cash vary, structure stays."""
    from schemas.document_schemas import Money

    receivables = []
    for r in inputs.receivables:
        scale = Decimal(str(round(float(np.clip(rng.normal(1.0, noise), 0.6, 1.4)), 3)))
        days = max(0, round(7 * noise / 0.15))  # +/-7 days at the default 15% noise, +/-1 day at 3%
        shift = int(rng.integers(-days, days + 1))
        receivables.append(r.model_copy(update={"amount": Money.from_amount(r.amount.amount * scale, r.amount.currency),
                                                "due_date": r.due_date + timedelta(days=shift)}))
    orders = []
    for o in inputs.confirmed_orders:
        scale = Decimal(str(round(float(np.clip(rng.normal(1.0, noise), 0.6, 1.4)), 3)))
        orders.append(o.model_copy(update={"amount": Money.from_amount(o.amount.amount * scale, o.amount.currency)}))
    opening = (inputs.opening_cash_usd * Decimal(str(round(float(np.clip(rng.normal(1.0, noise), 0.5, 1.5)), 3)))).quantize(Decimal("0.01"))
    deposits = [d.model_copy(update={"po_value_usd": (d.po_value_usd * Decimal(str(round(float(np.clip(rng.normal(1.0, noise), 0.6, 1.6)), 3)))).quantize(Decimal("0.01"))})
                for d in inputs.deposits]
    return inputs.model_copy(update={"receivables": receivables, "confirmed_orders": orders, "opening_cash_usd": opening, "deposits": deposits})


def perturb_core_inputs(inputs: CoreInputs, rng: np.random.Generator, noise: float = 0.15) -> CoreInputs:
    fi = perturb_inputs(inputs.forecast_inputs, rng, noise)
    by_ref = {r.invoice_id: r for r in fi.receivables}
    pledgeable = [Pledgeable(p.ref, p.buyer_id, p.buyer, float(by_ref[p.ref].amount.to_usd()), by_ref[p.ref].due_date, p.p_on_time)
                  for p in inputs.pledgeable if p.ref in by_ref and by_ref[p.ref].due_date > inputs.as_of]
    return CoreInputs(fi, pledgeable, dict(inputs.excluded), dict(inputs.factoring), dict(inputs.loan) if inputs.loan else None,
                      inputs.as_of, inputs.case_id)


def observed_items(realised: sim.Paths) -> List[Dict[str, Any]]:
    """Per-item outcomes in the form the learner reads. An order's shipment is observable once due."""
    out = []
    for row in sim.item_outcomes(realised):
        if row["due_week"] > FORECAST_WEEKS:
            continue  # outcome not observed inside the quarter
        if row["kind"] == "order":
            row["ship_observed"] = row["shipped"]
        out.append(row)
    return out


def seed_memory(memory: CaseMemory, inputs: CoreInputs, core: IntelligenceCore, episodes: int = 8, seed: int = 7,
                truth: sim.WorldParams = HIDDEN_TEST_WORLD) -> List[List[Dict[str, Any]]]:
    """Fill an empty memory with SIMULATED past quarters: plan with ``core``, realise in ``truth``, attribute."""
    rng = np.random.default_rng(seed)
    observed = []
    for k in range(episodes):
        past = perturb_core_inputs(inputs, rng)
        result = core.plan(past, baseline_actions=None)
        run_id = f"SIM-Q{k + 1:02d}"
        memory.remember_plan(run_id, result, source="SIMULATED")
        realised = sim.realise(past.forecast_inputs, truth, seed=seed * 1000 + k)
        outcome = attribute_outcome(past, result.chosen["actions"], realised)
        items = observed_items(realised)
        memory.remember_outcome(run_id, dict(outcome, items=items, truth_world=truth.label))
        observed.append(items)
    return observed


# --------------------------------------------------- events (financial twin)
# A fixed catalogue: in production these arrive from the bank feed, ERP or inbox parser; in the demo they are
# buttons. Free text never becomes an event.
EVENTS: Dict[str, Dict[str, Any]] = {
    "buyer_delay": {"label": "Oakline Home will pay every open invoice 30 days late", "source": "buyer email / collections agent", "certainty": 0.7},
    "order_cancelled": {"label": "Harbor Living cancels confirmed order SO-2303 (USD 61,000)", "source": "ERP order book", "certainty": 0.9},
    "deposit_up": {"label": "Mekong Timber asks for a 40% deposit on PO-2214 instead of 30%", "source": "supplier email", "certainty": 0.7},
    "early_payment": {"label": "Kyoto Interiors pays INV-1033 (USD 28,000) today, before its due date", "source": "bank feed", "certainty": 0.95},
}

ALERT_POLICY = (
    "Director inbox only when a decision is needed: (1) the plan in force got worse (more than 5 points) or can no longer be used, and the recommended plan changes; "
    "(2) the plan in force falls more than 5 points below the goal and no allowed plan restores it; or "
    "(3) the base-case first negative week moves earlier. Everything else goes to the daily digest."
)


def apply_event(inputs: CoreInputs, kind: str) -> CoreInputs:
    """Return new inputs with one catalogue event applied. Pure: the live case is not touched."""
    if kind not in EVENTS:
        raise ValueError(f"unknown event {kind!r}; events are a fixed catalogue: {sorted(EVENTS)}")
    fi = inputs.forecast_inputs
    pledgeable = list(inputs.pledgeable)
    if kind == "buyer_delay":
        shift = timedelta(days=30)
        fi = fi.model_copy(update={"receivables": [r.model_copy(update={"due_date": r.due_date + shift}) if r.buyer_id == "B-US-01" else r
                                                   for r in fi.receivables]})
        pledgeable = [Pledgeable(p.ref, p.buyer_id, p.buyer, p.usd, p.due_date + shift, p.p_on_time) if p.buyer_id == "B-US-01" else p
                      for p in pledgeable]
    elif kind == "order_cancelled":
        fi = fi.model_copy(update={"confirmed_orders": [o for o in fi.confirmed_orders if o.order_ref != "SO-2303"]})
    elif kind == "deposit_up":
        fi = fi.model_copy(update={"deposits": [d.model_copy(update={"pct": Decimal("40")}) if d.ref == "PO-2214" else d for d in fi.deposits]})
    elif kind == "early_payment":
        paid = next((r for r in fi.receivables if r.invoice_id == "INV-1033"), None)
        if paid is not None:
            fi = fi.model_copy(update={"receivables": [r for r in fi.receivables if r.invoice_id != "INV-1033"],
                                       "opening_cash_usd": fi.opening_cash_usd + paid.amount.to_usd()})
            pledgeable = [p for p in pledgeable if p.ref != "INV-1033"]
    return CoreInputs(fi, pledgeable, dict(inputs.excluded), dict(inputs.factoring), dict(inputs.loan) if inputs.loan else None,
                      inputs.as_of, inputs.case_id)


def plan_shape(actions: Sequence[Dict[str, Any]]) -> List[Tuple[Any, ...]]:
    return sorted((a["type"], a.get("ref"), int(a.get("week", 0)), a.get("new_pct")) for a in actions)


def assess_event(core: "IntelligenceCore", before_inputs: CoreInputs, after_inputs: CoreInputs, kind: str,
                 current: Optional[Dict[str, Any]], goal_id: str = "keep_cash_positive") -> Dict[str, Any]:
    """Re-plan after an event and decide whether the Director must be disturbed."""
    before_base = forecast_13w(before_inputs.forecast_inputs)
    after_base = forecast_13w(after_inputs.forecast_inputs)
    incumbent = current["actions"] if current else None
    result = core.plan(after_inputs, goal_id, incumbent=incumbent)
    target = result.goal["min_probability"]
    chosen = result.chosen
    reasons: List[str] = []
    notes: List[str] = []
    p_current_before = current["p_goal"] if current else None
    rebuilt = None
    p_current_after = None
    if current:
        rebuilt = rebuild_actions(current["actions"], after_inputs)
        if rebuilt is None:
            reasons.append("An invoice in the plan in force is no longer available to pledge.")
        else:
            paths = sim.sample(after_inputs.forecast_inputs, core.params, n=core.n_paths, seed=core.seed)
            p_current_after = round(float((sim.closings(paths, rebuilt).min(axis=1) >= 0).mean()), 4)
        changed = plan_shape(chosen["actions"]) != plan_shape(current["actions"])
        worse = rebuilt is None or (p_current_after is not None and p_current_before is not None
                                    and p_current_after < p_current_before - 0.05)
        if changed and worse:
            reasons.append("The plan in force got worse and the recommended plan changes, so new packs or approvals are needed.")
        elif changed:
            notes.append(f"A different plan now scores better ({chosen['p_goal']:.0%}); the plan in force still holds, so nothing is escalated.")
        if p_current_after is not None and p_current_after < target - 0.05 and result.status == "GOAL_NOT_REACHABLE" \
                and (p_current_before is None or p_current_after < p_current_before - 0.05):
            reasons.append(f"The plan in force now reaches only {p_current_after:.0%} against a {target:.0%} goal, and no allowed plan restores it.")
    elif result.status == "GOAL_NOT_REACHABLE":
        reasons.append("No plan is in force and no allowed plan reaches the goal.")
    bw, aw = before_base.first_shortfall_week, after_base.first_shortfall_week
    if aw is not None and (bw is None or aw < bw):
        reasons.append(f"The first negative week moves earlier: week {bw or '-'} → week {aw}.")
    route = "DIRECTOR_INBOX" if reasons else "DIGEST"
    # Priority: base-case damage x how sure the source is / weeks left before the first negative week.
    impact = max(0.0, float(before_base.min_closing_usd) - float(after_base.min_closing_usd))
    weeks_left = aw if aw is not None else 14
    certainty = float(EVENTS[kind]["certainty"])
    p_drop = (p_current_before - p_current_after) if (p_current_before is not None and p_current_after is not None) else 0.0
    score = round(impact / 1000 * certainty / max(1, weeks_left) + (10 if p_drop >= 0.30 else 0), 1)
    level = "LOW" if route == "DIGEST" else "HIGH" if (weeks_left <= 4 or p_drop >= 0.30) else "MEDIUM"
    deadline = (after_inputs.forecast_inputs.start_date + timedelta(weeks=aw - 1)).isoformat() if aw else None
    return {
        "priority": {"level": level, "score": score, "impact_usd": round(impact, 2), "certainty": certainty,
                     "deadline": deadline, "weeks_left": aw,
                     "rule": "score = base-case trough drop (USD k) x source certainty / weeks to first negative week (+10 if the plan in force loses 30+ points)"},
        "event": kind, "label": EVENTS[kind]["label"], "source": EVENTS[kind]["source"], "route": route, "reasons": reasons, "notes": notes,
        "base_case": {"first_negative_week_before": bw, "first_negative_week_after": aw,
                      "shortfall_before_usd": float(before_base.shortfall_usd or 0), "shortfall_after_usd": float(after_base.shortfall_usd or 0),
                      "min_closing_before_usd": float(before_base.min_closing_usd), "min_closing_after_usd": float(after_base.min_closing_usd)},
        "plan_in_force": {"description": current["description"] if current else None,
                          "p_goal_before": p_current_before, "p_goal_after": p_current_after},
        "new_plan": {"description": chosen["description"], "p_goal": chosen["p_goal"], "cost_usd": chosen["cost_usd"],
                     "packs": chosen["packs"], "status": result.status, "incumbent": chosen.get("incumbent")},
        "decision_needed": ("Approve the new plan's packs or decide how to close the rest (costs, sales, longer-term funding)."
                            if route == "DIRECTOR_INBOX" else None),
        "world_model": result.world_model["version"],
        "_chosen": chosen,
    }
