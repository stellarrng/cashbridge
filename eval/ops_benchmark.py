"""Operations benchmark: how often does the Director get disturbed, and is it for the right things?

    python eval/ops_benchmark.py      (or: make ops)

100 SYNTHETIC raw events from six families: financing events (buyer delay, order cancelled, supplier
deposit, early payment), bank reconciliation, invoice audit, refund requests, support tickets, overdue
invoices and cash alerts. Several raw events can describe the same thing (a buyer's email, a call note and
the collections agent all report the same delay), so events are grouped into cases by entity first.

Every case carries a label written by the scenario generator *before* routing, with a rule that is
deliberately different from the router's:
  * financing events need the Director when the base-case lowest balance falls by more than USD 30,000
    or the first negative week moves earlier; otherwise nobody (digest);
  * a cash alert needs the Director when the reserve is breached within two periods, else the accountant;
  * refunds, reconciliation exceptions, duplicate invoices and overdue invoices need the accountant;
    exact reconciliations need nobody; support tickets need support (security queue if fraud is alleged).

The CashBridge router uses the Intelligence Core's re-plan and alert policy for financing events and the
automation engine's own review flags for the rest. Two baselines: "notify the Director of every event"
and "notify the Director of every event above USD 10,000".

Metrics: cases after grouping, Director alerts, intervention rate, tasks completed without a person,
false alerts (Director alerted but the label says not needed), misses (label says Director, router did
not), safety violations (any side-effect flag set, or any action outside the allow-list), latency.

Writes data/execution_evidence/ops_benchmark.json and ops_benchmark.md. Everything is SIMULATED.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from agents import intelligence_core as ic  # noqa: E402
from automation.engine import evaluate  # noqa: E402
from config.settings import EXECUTION_EVIDENCE_DIR  # noqa: E402
from core.forecasting_engine import forecast_13w  # noqa: E402
from scripts.run_demo_story import StoryClock  # noqa: E402
from ui.backend_real import RealBackend  # noqa: E402

OUT_JSON = EXECUTION_EVIDENCE_DIR / "ops_benchmark.json"
OUT_MD = EXECUTION_EVIDENCE_DIR / "ops_benchmark.md"
SIDE_EFFECTS = ("external_reply_sent", "posting_performed", "refund_executed", "payments_performed", "executive_notification_sent",
                "assignment_sent", "calendar_event_created", "external_notification_sent", "external_action_performed", "values_applied")
FAMILY_WEIGHTS = {"finance": 0.22, "reconcile": 0.16, "invoice_audit": 0.10, "refund": 0.16, "support": 0.14, "overdue": 0.12, "cash_alert": 0.10}


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def generate(n: int = 100, seed: int = 42) -> List[Dict[str, Any]]:
    """Raw events. Some are repeats of the same entity (follow-ups, second channel)."""
    rng = np.random.default_rng(seed)
    families = list(FAMILY_WEIGHTS)
    probs = np.array(list(FAMILY_WEIGHTS.values()))
    events: List[Dict[str, Any]] = []
    while len(events) < n:
        fam = families[int(rng.choice(len(families), p=probs / probs.sum()))]
        k = len(events)
        if fam == "finance":
            kind = str(rng.choice(list(ic.EVENTS)))
            quarter = int(rng.integers(0, 6))
            ev = {"family": fam, "entity": f"{kind}@Q{quarter}", "kind": kind, "quarter": quarter, "amount": None}
        elif fam == "reconcile":
            ref = f"TX-{int(rng.integers(100, 140))}"
            bank_amt = round(float(rng.uniform(500, 30000)), 2)
            mismatch = bool(rng.random() < 0.35)
            ledger_amt = round(bank_amt + (float(rng.uniform(5, 400)) if mismatch else 0.0), 2)
            ev = {"family": fam, "entity": ref, "amount": bank_amt,
                  "payload": {"ledger": [{"reference": ref, "amount": f"{ledger_amt:.2f}"}], "bank": [{"reference": ref, "amount": f"{bank_amt:.2f}"}]}}
        elif fam == "invoice_audit":
            no = f"SUP-{int(rng.integers(1, 30))}"
            dup = bool(rng.random() < 0.4)
            amt = round(float(rng.uniform(300, 15000)), 2)
            rows = [{"invoice_number": no, "vendor": "Mekong Timber", "amount": f"{amt:.2f}"}]
            if dup:
                rows.append(dict(rows[0]))
            ev = {"family": fam, "entity": no, "amount": amt, "payload": {"invoices": rows}}
        elif fam == "refund":
            order = f"ORD-{int(rng.integers(1000, 1060))}"
            paid = round(float(rng.uniform(20, 3000)), 2)
            requested = round(paid * float(rng.choice([0.5, 1.0, 1.3])), 2)
            ev = {"family": fam, "entity": order, "amount": requested,
                  "payload": {"order_id": order, "requested_amount": f"{requested:.2f}", "paid_amount": f"{paid:.2f}", "currency": "USD",
                              "payment_verified": bool(rng.random() < 0.85), "order_status": str(rng.choice(["delivered", "returned", "shipped"])),
                              "policy_eligible": bool(rng.random() < 0.8)}}
        elif fam == "support":
            thread = f"T-{int(rng.integers(1, 40))}"
            fraud = bool(rng.random() < 0.15)
            msg = "I see an unauthorized charge, this looks like fraud" if fraud else str(rng.choice(
                ["Where is my invoice for October?", "Delivery to Yokohama is late", "Can I change the billing address?"]))
            ev = {"family": fam, "entity": thread, "amount": None, "payload": {"message": msg}}
        elif fam == "overdue":
            no = str(rng.choice(["INV-1026", "INV-1027", "INV-1034", "INV-1023", "INV-1042"]))
            ev = {"family": fam, "entity": no, "amount": float(rng.uniform(8000, 32000)),
                  "payload": {"invoice_number": no, "days_overdue": int(rng.integers(1, 45)), "amount": "10000.00"}}
        else:
            breach_in = int(rng.integers(1, 6))
            balances = ["25000"] * 6
            if rng.random() < 0.7:
                balances[breach_in - 1] = "-1500"
            ev = {"family": fam, "entity": f"cash@{breach_in}", "amount": None, "payload": {"projected_balances": balances, "minimum_reserve": "10000"}}
        ev["raw_id"] = f"RAW-{k + 1:03d}"
        events.append(ev)
    return events


def group(events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    cases: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        cases[f"{e['family']}:{e['entity']}"].append(e)
    return dict(cases)


def run(n_events: int = 100, seed: int = 42, n_paths: int = 500) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        base = ic.CoreInputs.from_coordinator(RealBackend(runtime_dir=Path(tmp), clock=StoryClock()).coord)
    core = ic.IntelligenceCore(n_paths=n_paths)
    quarters = [base] + [ic.perturb_core_inputs(base, np.random.default_rng(700 + q)) for q in range(1, 6)]
    plans_in_force = {}
    events = generate(n_events, seed)
    cases = group(events)
    rows = []
    violations = 0
    latencies: Dict[str, List[float]] = defaultdict(list)
    for case_id, evs in cases.items():
        first = evs[0]
        fam = first["family"]
        started = time.perf_counter()
        side_effects: List[str] = []
        if fam == "finance":
            before = quarters[first["quarter"]]
            after = ic.apply_event(before, first["kind"])
            if first["quarter"] not in plans_in_force:
                plans_in_force[first["quarter"]] = core.plan(before).chosen
            a = ic.assess_event(core, before, after, first["kind"], plans_in_force[first["quarter"]])
            routed = "director" if a["route"] == "DIRECTOR_INBOX" else "none"
            # Ablation: escalate whenever the recommended plan changes, even if the plan in force still holds.
            routed_any_change = "director" if (a["route"] == "DIRECTOR_INBOX" or a["notes"]) else "none"
            b0, b1 = forecast_13w(before.forecast_inputs), forecast_13w(after.forecast_inputs)
            drop = float(b0.min_closing_usd) - float(b1.min_closing_usd)
            earlier = b1.first_shortfall_week is not None and (b0.first_shortfall_week is None or b1.first_shortfall_week < b0.first_shortfall_week)
            label = "director" if (drop > 30000 or earlier) else "none"
            actions = a["_chosen"]["actions"]
            if ic.validate_plan(actions, after, 1e9):
                violations += 1
            amount = drop
        else:
            kind = {"reconcile": "accounting_reconcile", "invoice_audit": "audit_invoice", "refund": "refund_review",
                    "support": "support_triage", "overdue": "collections_draft", "cash_alert": "cash_alert"}[fam]
            outs = [evaluate(kind, e["payload"]) for e in evs]
            out = outs[0]
            side_effects = [k for o in outs for k, v in _walk(o) if k in SIDE_EFFECTS and v is not False]
            violations += len(side_effects)
            if fam == "support":
                routed = "security" if out["priority"] == "high" else "support"
                label = "security" if "fraud" in first["payload"]["message"] else "support"
            elif fam == "cash_alert":
                breaches = out["reserve_breaches"]
                routed = "director" if breaches and breaches[0]["period"] <= 2 else ("accountant" if breaches else "none")
                bal = first["payload"]["projected_balances"]
                first_breach = next((i + 1 for i, v in enumerate(bal) if float(v) < 10000), None)
                label = "director" if first_breach and first_breach <= 2 else ("accountant" if first_breach else "none")
            else:
                routed = "accountant" if out["review_required"] else "none"
                if fam == "reconcile":
                    p = first["payload"]
                    label = "accountant" if p["ledger"][0]["amount"] != p["bank"][0]["amount"] else "none"
                elif fam == "invoice_audit":
                    label = "accountant" if len(first["payload"]["invoices"]) > 1 else "none"
                else:
                    label = "accountant"
            amount = first.get("amount") or 0.0
            routed_any_change = routed
        latencies[fam].append((time.perf_counter() - started) * 1000)
        rows.append({"case": case_id, "family": fam, "raw_events": len(evs), "routed": routed, "routed_any_change": routed_any_change, "label": label,
                     "amount": round(float(amount or 0), 2), "side_effects": side_effects})

    def score(route_fn) -> Dict[str, Any]:
        routed = [route_fn(r) for r in rows]
        director = [r for r, x in zip(rows, routed) if x == "director"]
        need = [r for r in rows if r["label"] == "director"]
        false_alerts = sum(1 for r in director if r["label"] != "director")
        missed = sum(1 for r, x in zip(rows, routed) if r["label"] == "director" and x != "director")
        return {"director_alerts": len(director), "false_alerts": false_alerts, "missed": missed,
                "needed": len(need), "intervention_rate_pct": round(100 * len(director) / len(rows), 1),
                "precision_pct": round(100 * (len(director) - false_alerts) / len(director), 1) if director else None}

    cb = score(lambda r: r["routed"])
    every_raw = {"director_alerts": len(events), "false_alerts": sum(len(cases[r["case"]]) for r in rows if r["label"] != "director"),
                 "missed": 0, "needed": cb["needed"], "intervention_rate_pct": 100.0,
                 "precision_pct": round(100 * sum(len(cases[r["case"]]) for r in rows if r["label"] == "director") / len(events), 1)}
    threshold = score(lambda r: "director" if r["amount"] >= 10000 else "other")
    # Ablations of the two ideas the router rests on.
    no_plan_check = score(lambda r: r["routed_any_change"])
    dup = sum(r["raw_events"] - 1 for r in rows if r["routed"] == "director")
    no_grouping = {"director_alerts": cb["director_alerts"] + dup, "false_alerts": cb["false_alerts"] + dup, "missed": cb["missed"],
                   "needed": cb["needed"], "duplicates": dup,
                   "rule": "same router, but every raw event of a Director case notifies separately (duplicates count as noise)"}
    auto_done = sum(1 for r in rows if r["routed"] == "none")
    agree = sum(1 for r in rows if r["routed"] == r["label"])
    by_owner = Counter(r["routed"] for r in rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synthetic": True,
        "protocol": {"raw_events": len(events), "seed": seed, "paths_per_finance_case": n_paths, "families": FAMILY_WEIGHTS,
                     "label_rule": "written by the generator before routing; see module docstring"},
        "summary": {
            "raw_events": len(events), "cases": len(rows), "grouping_reduction_pct": round(100 * (1 - len(rows) / len(events)), 1),
            "cashbridge": cb, "baseline_every_event": every_raw, "baseline_amount_threshold": threshold,
            "ablation": {"without_plan_in_force_check": no_plan_check, "without_grouping": no_grouping},
            "completed_without_a_person": auto_done, "routed_to": dict(by_owner), "routing_agreement_pct": round(100 * agree / len(rows), 1),
            "safety_violations": violations,
            "mean_latency_ms": {k: round(float(np.mean(v)), 1) for k, v in latencies.items()},
        },
        "cases": rows,
    }


def write(result: Dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    s = result["summary"]
    cb, ev, th = s["cashbridge"], s["baseline_every_event"], s["baseline_amount_threshold"]
    lines = [
        "# Operations benchmark (SIMULATED)", "",
        f"Generated {result['generated_at']}. {s['raw_events']} synthetic raw events, grouped into {s['cases']} cases "
        f"({s['grouping_reduction_pct']}% fewer items). Labels come from the generator's own rule, not from the router.", "",
        "| | Notify Director of every event | Director if amount ≥ USD 10k | CashBridge |", "|---|---|---|---|",
        f"| Director notifications | {ev['director_alerts']} | {th['director_alerts']} | {cb['director_alerts']} |",
        f"| Needed (label) | {cb['needed']} | {cb['needed']} | {cb['needed']} |",
        f"| False alerts | {ev['false_alerts']} | {th['false_alerts']} | {cb['false_alerts']} |",
        f"| Missed | {ev['missed']} | {th['missed']} | {cb['missed']} |",
        f"| Precision of Director alerts | {ev['precision_pct']}% | {th['precision_pct']}% | {cb['precision_pct']}% |", "",
        "Ablation (switch one idea off, same events and labels):", "",
        "| | Director notifications | False alerts | Missed |", "|---|---|---|---|",
        f"| CashBridge | {cb['director_alerts']} | {cb['false_alerts']} | {cb['missed']} |",
        f"| without the plan-in-force check (escalate on any plan change) | {s['ablation']['without_plan_in_force_check']['director_alerts']} | {s['ablation']['without_plan_in_force_check']['false_alerts']} | {s['ablation']['without_plan_in_force_check']['missed']} |",
        f"| without grouping events into cases | {s['ablation']['without_grouping']['director_alerts']} | {s['ablation']['without_grouping']['false_alerts']} | {s['ablation']['without_grouping']['missed']} |", "",
        f"- Completed without a person (digest / exact matches): **{s['completed_without_a_person']}** of {s['cases']} cases",
        f"- Routed to: {', '.join(f'{k} {v}' for k, v in sorted(s['routed_to'].items()))}",
        f"- Router agrees with the label on **{s['routing_agreement_pct']}%** of cases",
        f"- Safety violations (side-effect flags or plans outside the policy): **{s['safety_violations']}**",
        f"- Mean handling time per case (ms): {', '.join(f'{k} {v}' for k, v in s['mean_latency_ms'].items())}", "",
        "Read with care: the events, the labels and the router are all ours. The point is that the Director sees a small number of "
        "cases that matter, with no side effects, and that every disagreement with the label is listed in the JSON for inspection.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    result = run()
    write(result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
