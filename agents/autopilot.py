"""Finance Autopilot: a governed agent that goes from "will we run out of cash?" to an approvable pack.

    analyze_cash_gap -> verify_receivables -> compare_funding_options -> stress_test
                     -> prepare_funding_pack -> request_approval (hand-off to the Director)

How it is governed
  * The agent chooses the next step, but only from ``ALLOWED_NEXT[current_step]``. A planner that
    proposes anything else (an L3/L4 tool, skipping verification, an unknown tool) is refused, the
    refusal is written to the audit log and the deterministic policy choice is used instead.
  * Every number comes from the deterministic engines (forecast, matching, APR, coverage). The
    planner never computes money. The default planner is a deterministic policy; an LLM planner
    can be plugged in through ``planner=`` and is held to exactly the same guard.
  * The agent can at most *prepare* a pack (internal, reversible). Submitting it is L3 and needs
    the Director's action-bound OTP; the agent has no path to it. L4 (money movement) has no tool.
  * Each claim is registered as evidence with a status, so a reader can tell verified facts from
    model estimates, assumptions and gaps the system cannot check.

All data is SYNTHETIC.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from config.settings import Tier
from config.tool_allowlist import L3_TOOLS, L4_TOOLS
from core.funding_coverage import coverage, peak_need, week_of
from schemas.agent_schemas import CaseState, Decision
from schemas.forecast_schemas import ScenarioParams
from security import injection_guard

PLANNER_ID = "deterministic-policy-v1"
TOOLS = ("analyze_cash_gap", "verify_receivables", "compare_funding_options", "stress_test",
         "prepare_funding_pack", "request_approval")
TERMINAL = ("stop", "escalate")
ALLOWED_NEXT: Dict[Optional[str], frozenset] = {
    None: frozenset({"analyze_cash_gap"}),
    "analyze_cash_gap": frozenset({"verify_receivables", "stop"}),
    "verify_receivables": frozenset({"compare_funding_options", "escalate"}),
    "compare_funding_options": frozenset({"stress_test", "escalate"}),
    "stress_test": frozenset({"prepare_funding_pack", "escalate"}),
    "prepare_funding_pack": frozenset({"request_approval", "escalate"}),
    "request_approval": frozenset({"stop"}),
}
EVIDENCE_STATUSES = ("VERIFIED", "CALCULATED", "MODEL_ESTIMATE", "ASSUMPTION", "NEEDS_HUMAN", "NOT_VERIFIABLE_HERE")

Planner = Callable[[Dict[str, Any], List[str]], str]


def _money(value: Any) -> float:
    return round(float(value), 2)


@dataclass
class _Run:
    steps: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    refused: List[Dict[str, Any]] = field(default_factory=list)
    obs: Dict[str, Any] = field(default_factory=dict)

    def ev(self, claim: str, value: Any, status: str, source: str, note: str = "") -> str:
        assert status in EVIDENCE_STATUSES, status
        ident = f"EV-{len(self.evidence) + 1:02d}"
        self.evidence.append({"id": ident, "claim": claim, "value": value, "status": status, "source": source, "note": note})
        return ident


class FinanceAutopilot:
    """Runs one governed pass over the coordinator's live case."""

    def __init__(self, coordinator: Any, planner: Optional[Planner] = None, core: Optional[Any] = None) -> None:
        self.coord = coordinator
        self.planner = planner
        self.core = core  # optional IntelligenceCore: scores the recommendation on simulated paths

    # ------------------------------------------------------------------ planning
    @staticmethod
    def policy_next(step: Optional[str], obs: Dict[str, Any]) -> str:
        """The deterministic policy: what a careful analyst would do next given what is known."""
        if step is None:
            return "analyze_cash_gap"
        if step == "analyze_cash_gap":
            return "verify_receivables" if obs.get("shortfall_week") else "stop"
        if step == "verify_receivables":
            return "compare_funding_options" if obs.get("nominee") else "escalate"
        if step == "compare_funding_options":
            return "stress_test" if obs.get("recommended_option") else "escalate"
        if step == "stress_test":
            return "prepare_funding_pack" if obs.get("can_prepare") else "escalate"
        if step == "prepare_funding_pack":
            return "request_approval" if obs.get("pack_ready") else "escalate"
        return "stop"

    def _choose(self, step: Optional[str], run: _Run) -> str:
        allowed = sorted(ALLOWED_NEXT[step])
        policy_choice = self.policy_next(step, run.obs)
        if self.planner is None:
            return policy_choice
        summary = {k: v for k, v in run.obs.items() if isinstance(v, (str, int, float, bool)) or v is None}
        try:
            proposed = str(self.planner(summary, allowed)).strip()
        except Exception as error:  # a failing planner never stops the governed policy
            proposed = f"<planner error: {type(error).__name__}>"
        if proposed == policy_choice:
            return proposed
        reason = ("money movement is never available to an agent" if proposed in L4_TOOLS else
                  "external actions need the Director's OTP, not an agent" if proposed in L3_TOOLS else
                  f"not an allowed next step after {step or 'start'} (allowed: {', '.join(allowed)})" if proposed not in allowed else
                  "the evidence does not support this step yet; policy guard kept the safe step")
        run.refused.append({"after": step, "proposed": proposed, "used": policy_choice, "reason": reason})
        self.coord.audit.append(case_id=self.coord.case.case_id, agent="autopilot", tool=f"planner:{proposed}"[:80],
                                tier=Tier.L4_MONEY_MOVEMENT if proposed in L4_TOOLS else Tier.L1_ANALYZE,
                                decision=Decision.BLOCKED, reason=f"Planner proposal refused: {reason}",
                                input_payload={"after": step, "proposed": proposed})
        return policy_choice

    def _log(self, tool: str, payload: Dict[str, Any], output: Dict[str, Any]) -> None:
        self.coord.audit.append(case_id=self.coord.case.case_id, agent="autopilot", tool=tool, tier=Tier.L1_ANALYZE,
                                decision=Decision.ALLOWED, reason="Governed autopilot step (read/analyze only)",
                                input_payload=payload, output_payload=output)

    # ------------------------------------------------------------------ tools
    def analyze_cash_gap(self, run: _Run) -> Dict[str, Any]:
        c = self.coord
        f = c.forecast
        week, gap = f.first_shortfall_week, f.shortfall_usd
        start = c.forecast_inputs.start_date
        peak = peak_need(f.weeks, f.buffer_usd)
        ev = [run.ev("Opening cash", _money(c.cash_today), "VERIFIED", "bank:opening_balance", "Synthetic bank statement")]
        if not week:
            run.obs.update(shortfall_week=None)
            ev.append(run.ev("Lowest closing balance in 13 weeks", _money(f.min_closing_usd), "CALCULATED", f"forecast:{c.forecast_run_id}"))
            return {"why": "Start with the cash position: nothing else matters if no week goes negative.",
                    "result": f"No negative week in the 13-week forecast; lowest balance USD {_money(f.min_closing_usd):,.2f}.",
                    "evidence": ev, "data": {"shortfall_week": None, "peak": peak}}
        drivers = sorted(f.attribution, key=lambda a: (a.source_ref == "ledger:baseline", -a.amount_usd))
        ev.append(run.ev(f"First negative week (starts {start.isoformat()} + {week - 1} weeks)", week, "CALCULATED", f"forecast:{c.forecast_run_id}",
                         "13-week engine: expected inflow = value x P(on time); late share four weeks later"))
        ev.append(run.ev(f"Shortfall in week {week}", _money(gap), "CALCULATED", f"forecast:{c.forecast_run_id}"))
        ev.append(run.ev("Cash needed to keep all 13 weeks at zero", peak["need_to_zero_usd"], "CALCULATED", f"forecast:{c.forecast_run_id}",
                         f"Trough in week {peak['trough_week']}; open invoices plus confirmed orders, no unconfirmed sales"))
        orders = c.forecast_inputs.confirmed_orders
        if orders:
            ev.append(run.ev(f"Confirmed, not-yet-invoiced orders counted ({len(orders)})",
                             _money(sum((o.amount.to_usd() for o in orders), Decimal(0))), "ASSUMPTION", "forecast:confirmed_orders",
                             f"Counted at {orders[0].ship_confidence:.0%} shipment confidence and the buyer's on-time probability; "
                             "they are not receivables and cannot back a funding request"))
        ev.append(run.ev("No unconfirmed new sales in the horizon", "invoices + confirmed orders only", "ASSUMPTION", "forecast:inputs",
                         "Conservative: orders not yet confirmed are left out"))
        for d in drivers[:3]:
            status = "MODEL_ESTIMATE" if d.source_ref.startswith("inv:") else "VERIFIED" if d.source_ref.startswith("doc:") else "CALCULATED"
            ev.append(run.ev(f"Driver: {d.driver}", _money(d.amount_usd), status, d.source_ref))
        run.obs.update(shortfall_week=week, shortfall_usd=_money(gap), peak_need_usd=peak["need_to_zero_usd"],
                       trough_week=peak["trough_week"], negative_weeks=peak["negative_weeks"])
        top = drivers[0]
        return {"why": "Find when the account goes negative and why, before looking at any financing.",
                "result": (f"Week {week} closes USD {_money(gap):,.2f} short. Largest driver: {top.driver} (USD {_money(top.amount_usd):,.2f}). "
                           f"Without action the balance is lowest in week {peak['trough_week']} (USD {peak['trough_closing_usd']:,.2f}) "
                           f"and is negative in {peak['negative_weeks']} of 13 weeks."),
                "evidence": ev, "data": {"shortfall_week": week, "shortfall_usd": _money(gap), "peak": peak,
                                          "drivers": [{"driver": d.driver, "amount_usd": _money(d.amount_usd), "source": d.source_ref} for d in drivers]}}

    def verify_receivables(self, run: _Run) -> Dict[str, Any]:
        c = self.coord
        rows = c.verification
        by_status: Dict[str, int] = {}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        ev: List[str] = []
        exceptions: List[str] = []
        for r in rows:
            if r["status"] != "ELIGIBLE":
                exceptions.append(f"{r['invoice_id']} {r['status'].lower()}: {'; '.join(r['differences']) or 'see 3-way match'}")
                ev.append(run.ev(f"{r['invoice_id']} excluded from funding", r["status"], "NEEDS_HUMAN", f"match:{r['invoice_id']}",
                                 "; ".join(r["differences"])))
        for invoice_no, problems in sorted(c.scan_checks.items()):
            if problems:
                exceptions.append(f"{invoice_no} scan needs a person: {problems[0][:120]}")
                ev.append(run.ev(f"Scanned {invoice_no} below 0.85 confidence", "left for a person", "NEEDS_HUMAN", f"scan:{invoice_no}"))
        unmatched = [r for r in c.recon_rows if r["status"] == "NEEDS_HUMAN"]
        for r in unmatched:
            exceptions.append(f"{r['txn_id']} ({r['currency']} {r['amount']:,.0f}) unmatched")
            ev.append(run.ev(f"Bank credit {r['txn_id']} unmatched", r["reason"], "NEEDS_HUMAN", f"bank:{r['txn_id']}"))
        blocked = [a for a in c.alerts if a.get("type") == "BEC"]
        if blocked:
            ev.append(run.ev("Lookalike-domain bank-change emails blocked", len(blocked), "VERIFIED", "inbox:bec_detector",
                             "Payee details are never changed by the system"))
        concentration = [b for b in c.buyer_risk_rows() if b["concentration_alert"]]
        for b in concentration:
            ev.append(run.ev(f"Buyer concentration: {b['buyer']}", f"{b['share_of_receivables_pct']}% of open receivables", "CALCULATED",
                             f"risk:{b['buyer_id']}", "Above the 40% alert line"))
        nominee = c.nominee
        if nominee is None or c.state in (CaseState.NEEDS_HUMAN, CaseState.BLOCKED):
            run.obs.update(nominee=None, escalation=c.case.needs_human_reason)
            reason = "No invoice passes every check (3-way match, registry, tax ID, readable scans, not yet due)."
            if c.state is CaseState.NEEDS_HUMAN:
                reason = f"Case needs a person: {c.case.needs_human_reason or 'see exceptions'}."
            return {"why": "Only verified receivables may back a funding request.", "result": reason,
                    "evidence": ev, "data": {"by_status": by_status, "exceptions": exceptions, "nominee": None}}
        row = next(r for r in rows if r["invoice_id"] == nominee.invoice_no)
        scans = [s for s in c.scans if s["invoice_no"] == nominee.invoice_no]
        ev.append(run.ev(f"{nominee.invoice_no} 3-way match (invoice, PO, B/L)", row["status"], "VERIFIED", f"match:{nominee.invoice_no}",
                         "Amounts within 0.01; quantity, packages, ports and buyer agree"))
        ev.append(run.ev(f"{nominee.invoice_no} face value", _money(nominee.amount.to_usd()), "VERIFIED", f"doc:{nominee.invoice_no}"))
        ev.append(run.ev(f"{nominee.invoice_no} seller tax ID", "valid" if row["tax_id_valid"] else "invalid", "VERIFIED", "registry:issuer"))
        ev.append(run.ev(f"{nominee.invoice_no} scanned documents", f"{len(scans)} read, lowest confidence {min((s['min_confidence'] for s in scans), default=0):.2f}",
                         "VERIFIED" if scans and all(s["matches_record"] for s in scans) else "NEEDS_HUMAN", f"scan:{nominee.invoice_no}"))
        ev.append(run.ev(f"{nominee.invoice_no} not yet financed (this installation)", row["registry_status"], "VERIFIED", "registry:local",
                         "Local hash-chained registry only"))
        ev.append(run.ev(f"{nominee.invoice_no} not financed at another lender", "unknown", "NOT_VERIFIABLE_HERE", "registry:external",
                         "Needs a shared lender registry or the e-invoice authority; the bank must check"))
        ev.append(run.ev(f"Buyer {nominee.buyer_name} KYC / credit limit", "not checked", "NOT_VERIFIABLE_HERE", "bank:kyc",
                         "Lender responsibility"))
        spare = [r for r in rows if r["status"] == "ELIGIBLE" and r["registry_status"] == "NOT_REGISTERED" and r["currency"] == "USD"
                 and r["invoice_id"] != nominee.invoice_no and r["due_date"] > c.as_of.isoformat()]
        spare.sort(key=lambda r: -r["amount"])
        run.obs.update(nominee=nominee.invoice_no, exceptions=len(exceptions),
                       spare_invoices=[{"invoice_id": r["invoice_id"], "buyer": r["buyer"], "amount_usd": r["amount"], "due_date": r["due_date"]} for r in spare])
        return {"why": "Only verified receivables may back a funding request; exceptions stay with a person.",
                "result": (f"{by_status.get('ELIGIBLE', 0)} of {len(rows)} open invoices pass the 3-way match. Nominated {nominee.invoice_no} "
                           f"(USD {_money(nominee.amount.to_usd()):,.2f}, {nominee.buyer_name}, due {nominee.due_date.isoformat()}). "
                           f"{len(exceptions)} exception(s) left for a person."),
                "evidence": ev, "data": {"by_status": by_status, "exceptions": exceptions, "nominee": nominee.invoice_no}}

    def compare_funding_options(self, run: _Run) -> Dict[str, Any]:
        c = self.coord
        f = c.forecast
        start = c.forecast_inputs.start_date
        settle = c.nominee.due_date if c.nominee else None
        rows = []
        ev: List[str] = []
        for o in c.options:
            cov = coverage(f.weeks, option=o, funding_week=f.first_shortfall_week, buffer_usd=f.buffer_usd,
                           start_date=start, settle_on=settle) if o.eligible else None
            rows.append({"id": o.id, "name": o.name, "type": o.type, "eligible": o.eligible, "amount_usd": _money(o.amount_usd) if o.amount_usd else None,
                         "apr_pct": o.apr_pct, "total_cost_usd": _money(o.cost_breakdown.get("total_usd", 0)) if o.cost_breakdown else None,
                         "lender_pack": o.type in ("factoring", "loan"), "ineligible_reason": o.ineligible_reason, "coverage": cov})
            if o.eligible and o.apr_pct is not None:
                ev.append(run.ev(f"{o.name}: annualised cost", o.apr_pct, "CALCULATED", f"funding:{o.id}", o.formula or ""))
                ev.append(run.ev(f"{o.name}: terms", ", ".join(f"{k.replace('_', ' ')} {float(v) if isinstance(v, Decimal) else v:g}" for k, v in o.assumptions.items()),
                                 "ASSUMPTION", "catalog:mock_lender", "MOCK lender catalogue, not a quote"))
        packable = [r for r in rows if r["eligible"] and r["lender_pack"] and r["apr_pct"] is not None]
        covering = [r for r in packable if r["coverage"] and r["coverage"]["covers_first_gap"]]
        best = min(covering or packable, key=lambda r: r["apr_pct"], default=None)
        if best is None:
            run.obs.update(recommended_option=None)
            return {"why": "Price every way to bridge the gap on the same annualised basis.", "result": "No eligible lender option in the catalogue.",
                    "evidence": ev, "data": {"options": rows}}
        cov = best["coverage"]
        headroom = round(best["amount_usd"] - (run.obs.get("shortfall_usd") or 0), 2)
        ev.append(run.ev(f"{best['name']} covers week {f.first_shortfall_week}", "yes" if cov["covers_first_gap"] else "no", "CALCULATED", "coverage:engine",
                         f"Headroom USD {headroom:,.2f}"))
        ev.append(run.ev("Balance after this option goes negative again", f"week {cov['first_negative_week_after']}" if cov["first_negative_week_after"] else "no",
                         "CALCULATED", "coverage:engine", "; ".join(a for a in cov["assumptions"] if a)))
        ev.append(run.ev("Residual gap at the trough after this option", cov["residual_gap_usd"], "CALCULATED", "coverage:engine",
                         f"Week {cov['trough_week']}"))
        discount = next((r for r in rows if r["type"] == "discount" and r["eligible"]), None)
        run.obs.update(recommended_option=best["id"], recommended_apr=best["apr_pct"], residual_gap_usd=cov["residual_gap_usd"],
                       first_negative_after=cov["first_negative_week_after"], headroom_usd=headroom)
        why = [f"Cheapest option that covers the week-{f.first_shortfall_week} gap: {best['apr_pct']:.2f}% a year, total cost USD {best['total_cost_usd']:,.2f}."]
        others = [r for r in packable if r["id"] != best["id"]]
        for r in others:
            why.append(f"{r['name']}: {r['apr_pct']:.2f}% a year ({r['apr_pct'] - best['apr_pct']:+.2f} points).")
        if discount:
            why.append(f"{discount['name']} costs {discount['apr_pct']:.2f}% a year and is agreed with the buyer, so it is not a lender pack.")
        return {"why": "Price every way to bridge the gap on the same annualised basis, then check it really covers the weeks that follow.",
                "result": (f"Recommend {best['name']} for USD {best['amount_usd']:,.2f} at {best['apr_pct']:.2f}% a year. It covers week {f.first_shortfall_week} "
                           f"with USD {headroom:,.2f} headroom, but the balance turns negative again in week {cov['first_negative_week_after']} "
                           f"and the trough is still USD {cov['residual_gap_usd']:,.2f} short." if cov["first_negative_week_after"] else
                           f"Recommend {best['name']} for USD {best['amount_usd']:,.2f} at {best['apr_pct']:.2f}% a year; it keeps every week above zero."),
                "evidence": ev, "data": {"options": rows, "recommended": best["id"], "why": why}}

    def stress_test(self, run: _Run) -> Dict[str, Any]:
        c = self.coord
        base = c.forecast
        scenarios = [
            ("Buyers pay 15 days later", ScenarioParams(dso_change_days=15), "stress"),
            ("FX moves 2% against us", ScenarioParams(fx_change_pct=-2), "stress"),
            ("Collect 15 days faster (DSO -15)", ScenarioParams(dso_change_days=-15), "lever"),
            ("Negotiate PO-2214 deposit down to 15%", ScenarioParams(deposit_pct=15), "lever"),
            ("Both levers together", ScenarioParams(dso_change_days=-15, deposit_pct=15), "lever"),
        ]
        out = []
        ev: List[str] = []
        for label, params, kind in scenarios:
            result = c.simulate(params)
            fr = result.forecast
            item = {"label": label, "kind": kind, "params": params.model_dump(),
                    "first_shortfall_week": fr.first_shortfall_week,
                    "shortfall_usd": _money(fr.shortfall_usd) if fr.shortfall_usd is not None else None,
                    "min_closing_usd": _money(fr.min_closing_usd),
                    "trough_change_usd": _money(fr.min_closing_usd - base.min_closing_usd)}
            out.append(item)
            ev.append(run.ev(f"Scenario: {label}", f"first gap week {item['first_shortfall_week']}, trough USD {item['min_closing_usd']:,.2f}",
                             "CALCULATED", "forecast:what_if", "Engine what-if; inputs are hypothetical"))
        advance = next((o.amount_usd for o in c.options if o.id == run.obs.get("recommended_option")), None)
        stressed = [s for s in out if s["kind"] == "stress"]
        breaks = [s for s in stressed if s["shortfall_usd"] is not None and advance is not None and s["shortfall_usd"] > float(advance)]
        earlier = [s for s in stressed if s["first_shortfall_week"] and base.first_shortfall_week and s["first_shortfall_week"] < base.first_shortfall_week]
        levers = sorted([s for s in out if s["kind"] == "lever"], key=lambda s: -s["trough_change_usd"])
        best_lever = levers[0] if levers else None
        run.obs.update(stress_breaks=len(breaks), stress_earlier=len(earlier),
                       can_prepare=bool(run.obs.get("recommended_option")) and c.state in (CaseState.INVOICE_VERIFIED, CaseState.AWAITING_APPROVAL))
        notes = []
        if earlier:
            notes.append("Under stress the first gap arrives earlier (week " + ", ".join(str(s["first_shortfall_week"]) for s in earlier) +
                         "): funds must be available sooner than the base case says.")
        if breaks:
            notes.append("In at least one stress case the first gap is larger than the advance.")
        if best_lever:
            notes.append(f"Best non-borrowing lever: {best_lever['label']} improves the trough by USD {best_lever['trough_change_usd']:,.2f}.")
        core_view = self._core_view(run, ev, notes)
        return {"why": "A recommendation is only useful if it survives bad news; also look for levers that reduce the need to borrow.",
                "result": " ".join(notes) or "The recommendation holds under the tested stresses.",
                "evidence": ev, "data": {"scenarios": out, "best_lever": best_lever, "core": core_view}}

    def _core_view(self, run: _Run, ev: List[str], notes: List[str]) -> Optional[Dict[str, Any]]:
        """Score the recommended pack on simulated paths and ask the Intelligence Core for a plan built for bad paths."""
        if self.core is None or not run.obs.get("recommended_option"):
            return None
        from agents import intelligence_core as ic  # local import keeps the autopilot importable without NumPy-heavy modules

        inputs = ic.CoreInputs.from_coordinator(self.coord)
        result = self.core.plan(inputs, baseline_actions=ic.fixed_workflow_actions(inputs))
        base, chosen = result.baseline, result.chosen
        version = result.world_model["version"]
        if base:
            ev.append(run.ev("Recommended pack alone: paths with no negative week", f"{base['p_goal']:.0%}", "MODEL_ESTIMATE",
                             f"core:{version}", f"{result.world_model['paths']} simulated paths; world model {version}"))
            notes.append(f"On {result.world_model['paths']} simulated paths the recommended pack alone keeps every week at or above zero "
                         f"{base['p_goal']:.0%} of the time.")
        ev.append(run.ev(f"Intelligence Core plan ({result.status})", f"{chosen['description']}: {chosen['p_goal']:.0%}", "MODEL_ESTIMATE",
                         f"core:{version}", f"Expected cost USD {chosen['cost_usd']:,.2f}; {chosen['packs']} pack(s), each needs the Director"))
        notes.append(f"A plan built for bad paths ({chosen['description']}) reaches {chosen['p_goal']:.0%}"
                     + (" and meets the goal." if result.status == "GOAL_MET" else f"; no allowed plan reaches {result.goal['min_probability']:.0%}."))
        run.obs.update(core_status=result.status, core_p_goal=chosen["p_goal"], core_baseline_p_goal=base.get("p_goal") if base else None)
        return {"status": result.status, "goal": result.goal, "chosen": {k: chosen[k] for k in ("plan_id", "description", "p_goal", "cost_usd", "packs", "actions", "why")},
                "fixed_workflow": {k: base[k] for k in ("description", "p_goal", "cost_usd")} if base else None,
                "world_model": version, "paths": result.world_model["paths"]}

    def prepare_funding_pack(self, run: _Run, actor: Optional[str], execute: bool) -> Dict[str, Any]:
        c = self.coord
        option_id = run.obs.get("recommended_option")
        if not execute:
            run.obs.update(pack_ready=False, plan_only=True)
            return {"why": "Drafting a pack is an internal write reserved for the preparer role.",
                    "result": f"Plan only: {option_id} is ready to be drafted by the accountant (preparer). Nothing was written.",
                    "evidence": [], "status": "proposed", "data": {"option_id": option_id}}
        if c.state is CaseState.AWAITING_APPROVAL and c.selected_option_id == option_id:
            outcome = {"ok": True, "reused": True}
        else:
            c.choose_option(option_id)
            outcome = c.prepare_pack(prepared_by=actor)
        if not outcome.get("ok"):
            run.obs.update(pack_ready=False)
            return {"why": "Lock the figures and hash the documents so nothing can change after approval.",
                    "result": f"Pack not drafted: {outcome.get('error')}", "evidence": [], "status": "escalated", "data": outcome}
        pack = c.pack
        ev = [run.ev("Funding pack bundle hash (SHA-256)", pack["bundle_sha256"], "CALCULATED", f"pack:{pack['pack_id']}",
                     "Covers document hashes and locked metrics"),
              run.ev("Cover letter passed the number lock", "every number is a locked figure", "VERIFIED", "security:number_check")]
        run.obs.update(pack_ready=True, pack_id=pack["pack_id"])
        return {"why": "Lock the figures and hash the documents so nothing can change after approval.",
                "result": f"Drafted {pack['pack_id']} ({len(pack['locked_metrics'])} locked metrics, 3 source documents hashed). Status {pack['status']}.",
                "evidence": ev, "data": {"pack_id": pack["pack_id"], "action_hash": pack["action_hash"], "reused": outcome.get("reused", False)}}

    def request_approval(self, run: _Run) -> Dict[str, Any]:
        pack_id = run.obs.get("pack_id")
        return {"why": "Submitting to a lender leaves the system (L3): only the Director can release it, with a one-time code bound to this exact pack.",
                "result": f"Handed {pack_id} to the Director. The agent cannot submit it; the OTP challenge is issued when the Director opens the approval.",
                "evidence": [], "data": {"pack_id": pack_id, "awaiting": "sme_director"}}

    # ------------------------------------------------------------------ run
    def run(self, *, actor: Optional[str] = None, execute: bool = False, goal: str = "Close the forecast cash gap safely") -> Dict[str, Any]:
        c = self.coord
        goal = (goal or "")[:300]
        injected = injection_guard.inspect(goal).suspicious
        run = _Run()
        started = c.state.value
        step: Optional[str] = None
        for _ in range(len(TOOLS) + 2):
            nxt = self._choose(step, run)
            if nxt in TERMINAL:
                outcome = nxt
                break
            if nxt == "prepare_funding_pack":
                result = self.prepare_funding_pack(run, actor, execute)
            else:
                result = getattr(self, nxt)(run)
            status = result.get("status", "completed")
            run.steps.append({"n": len(run.steps) + 1, "tool": nxt, "why": result["why"], "result": result["result"],
                              "status": status, "evidence": result["evidence"], "data": result.get("data", {})})
            self._log(f"autopilot.{nxt}", {"actor": actor, "execute": execute}, {"status": status, "result": result["result"][:200]})
            step = nxt
            if status == "proposed":
                outcome = "plan_ready"
                break
        else:  # pragma: no cover - the transition table is acyclic
            outcome = "escalate"

        decision = {"stop": "AWAITING_DIRECTOR_APPROVAL" if run.obs.get("pack_ready") else "MONITOR",
                    "plan_ready": "PLAN_READY_FOR_PREPARER", "escalate": "HUMAN_REVIEW_REQUIRED"}[outcome]
        if decision == "MONITOR" and run.obs.get("shortfall_week"):
            decision = "HUMAN_REVIEW_REQUIRED"
        if c.state in (CaseState.SUBMITTED, CaseState.FUNDED, CaseState.REJECTED):
            decision = {CaseState.SUBMITTED: "SUBMITTED_TO_LENDER", CaseState.FUNDED: "FUNDED_BY_LENDER",
                        CaseState.REJECTED: "DECLINED_BY_LENDER"}[c.state]
        recommendation = self._recommendation(run, decision)
        body = {"steps": [s["tool"] for s in run.steps], "evidence": [(e["id"], e["status"]) for e in run.evidence], "decision": decision}
        run_id = "AP-" + hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:10].upper()
        counts: Dict[str, int] = {}
        for e in run.evidence:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
        return {
            "run_id": run_id, "planner": PLANNER_ID if self.planner is None else "external-planner+policy-guard",
            "mode": "execute" if execute else "plan_only", "actor": actor, "goal": goal,
            "goal_injection_detected": injected, "goal_used_for_tool_selection": False,
            "case_state_before": started, "case_state_after": c.state.value,
            "decision": decision, "steps": run.steps, "evidence": run.evidence, "evidence_counts": counts,
            "refused_proposals": run.refused, "recommendation": recommendation,
            "human_handoff": self._handoff(decision, run),
            "guardrails": [
                "Next step limited to an allowlisted transition; off-policy proposals are refused and logged",
                "Numbers come from deterministic engines; the planner never computes money",
                "Agent may draft (internal) but never submit (L3 OTP) or move money (L4 has no tool)",
                "Preparer and approver must be different people (segregation of duties)",
                "Goal text is shown to humans only; it cannot add or remove a step",
            ],
            "synthetic": True,
        }

    def _recommendation(self, run: _Run, decision: str) -> Optional[Dict[str, Any]]:
        steps = {s["tool"]: s for s in run.steps}
        if "compare_funding_options" not in steps:
            return None
        cmp_data = steps["compare_funding_options"]["data"]
        if not cmp_data.get("recommended"):
            return None
        best = next(o for o in cmp_data["options"] if o["id"] == cmp_data["recommended"])
        cov = best["coverage"]
        stress = steps.get("stress_test", {}).get("data", {})
        spare = run.obs.get("spare_invoices") or []
        advance_pct = 0.8
        try:
            advance_pct = float(self.coord.catalog.factoring.advance_pct) / 100  # type: ignore[attr-defined]
        except Exception:
            pass
        capacity = round(sum(s["amount_usd"] for s in spare) * advance_pct, 2)
        what_would_change = []
        weeks = self.coord.forecast.weeks
        inflows = sum(Decimal(w.inflows) for w in weeks)
        outflows = sum(Decimal(w.outflows) for w in weeks)
        structural = outflows - inflows - Decimal(self.coord.cash_today)
        if cov and cov["first_negative_week_after"]:
            what_would_change.append(
                f"The pack bridges week {cov['funding_week']} only. Cash turns negative again in week {cov['first_negative_week_after']} and the trough "
                f"is USD {cov['residual_gap_usd']:,.2f} short (invoices plus confirmed orders).")
            if structural > 0:
                what_would_change.append(
                    f"Over 13 weeks, outflows (USD {_money(outflows):,.2f}) exceed opening cash plus expected collections by USD {_money(structural):,.2f}. "
                    "Factoring more invoices only brings cash forward; it cannot close a gap where costs exceed collections. "
                    "That needs new sales, lower costs or longer-term finance: a decision for the Director, not the agent.")
            if spare:
                what_would_change.append(
                    f"For timing only, other verified unpledged USD invoices ({', '.join(s['invoice_id'] for s in spare[:4])}) could be advanced "
                    f"(about USD {capacity:,.2f} at {advance_pct:.0%}), each needing its own pack and approval.")
        if cov and cov["covers_first_gap"] and not cov["first_negative_week_after"]:
            low = min(cov["weeks"], key=lambda r: r["closing_after"])
            what_would_change.insert(0,
                f"With the advance, every week from {cov['funding_week']} to 13 stays at or above zero in the base case "
                f"(lowest USD {low['closing_after']:,.2f} in week {low['week']}); the factor is repaid from {self.coord.nominee.invoice_no if self.coord.nominee else 'the pledged invoice'} "
                f"in week {cov['settlement_week']}.")
            below = [r["week"] for r in cov["weeks"] if r["below_buffer"] and r["week"] >= cov["funding_week"]]
            if below:
                label = f"Week {below[0]} stays" if len(below) == 1 else f"Weeks {', '.join(map(str, below))} stay"
                what_would_change.append(f"{label} below the USD {float(self.coord.forecast.buffer_usd):,.0f} buffer: thin, not negative.")
        if stress.get("best_lever"):
            bl = stress["best_lever"]
            what_would_change.append(f"{bl['label']} would raise the trough by USD {bl['trough_change_usd']:,.2f} without borrowing, "
                                     "if the buyers and the supplier agree; the forecast does not assume they will.")
        core = stress.get("core")
        if core:
            what_would_change.append(
                f"The base case is one path. On simulated paths this pack alone keeps cash at or above zero {core['fixed_workflow']['p_goal']:.0%} "
                f"of the time; the Intelligence Core's plan ({core['chosen']['description']}) reaches {core['chosen']['p_goal']:.0%} "
                f"for about USD {core['chosen']['cost_usd']:,.0f} in expected cost. Extra packs each need their own approval.")
        else:
            what_would_change.append("The base case is one path. If buyers pay later than their history suggests, coverage can fail.")
        return {
            "option_id": best["id"], "option_name": best["name"], "amount_usd": best["amount_usd"], "apr_pct": best["apr_pct"],
            "total_cost_usd": best["total_cost_usd"], "covers_first_gap": bool(cov and cov["covers_first_gap"]),
            "headroom_usd": run.obs.get("headroom_usd"), "residual_gap_usd": cov["residual_gap_usd"] if cov else None,
            "first_negative_week_after": cov["first_negative_week_after"] if cov else None,
            "why": cmp_data.get("why", []),
            "conditions": ["Lender KYC on the SME and the buyer", "External duplicate-financing check (shared registry)",
                           "Notice of assignment accepted by the buyer (factoring)", "Director OTP for this exact pack"],
            "what_would_change": what_would_change,
            "additional_capacity_usd": capacity if spare else 0.0,
            "structural_gap_usd": _money(max(structural, Decimal(0))),
            "horizon_inflows_usd": _money(inflows), "horizon_outflows_usd": _money(outflows),
            "coverage": cov,
            "core_plan": stress.get("core"),
        }

    @staticmethod
    def _handoff(decision: str, run: _Run) -> Dict[str, str]:
        if decision == "AWAITING_DIRECTOR_APPROVAL":
            return {"who": "Director (sme_director)", "action": f"Review {run.obs.get('pack_id')} and approve with the one-time code, or reject it",
                    "why": "External submission is L3; also decide whether to add the extra packs the scenario test suggests for bad paths"}
        if decision == "PLAN_READY_FOR_PREPARER":
            return {"who": "Chief accountant (sme_accountant)", "action": "Run the Autopilot in execute mode to draft the pack",
                    "why": "The Director approves but does not prepare (segregation of duties)"}
        if decision in ("SUBMITTED_TO_LENDER", "FUNDED_BY_LENDER", "DECLINED_BY_LENDER"):
            return {"who": "Bank reviewer (bank_reviewer)", "action": "Lender reviews the submitted pack and records a human credit decision",
                    "why": "The pack has left the SME workspace; the agent has no further role in it"}
        if decision == "MONITOR":
            return {"who": "Finance team", "action": "No funding needed; re-run when new data arrives", "why": "No negative week forecast"}
        return {"who": "Chief accountant", "action": "Resolve the exceptions listed in the trace", "why": "The evidence does not support an automatic recommendation"}
