"""T16: is the Executive Inbox result an accident of seed 42? Multi-seed sweep plus stress cases.

    python eval/ops_robustness.py [--seeds 30]     # writes reports/ops_robustness.{json,md}

1. Seed sweep: the same 100-event generator with many seeds. Reports, pooled over seeds, the share of
   Director-needed cases that were missed (with a Wilson 95% interval), false alerts per 100 events
   and alerts per 100 events, for CashBridge and both baselines.
2. Stress cases built on top of seed 42:
   * burst: one reserve breach reported 30 times through different channels -> must be ONE alert;
   * critical but small: a reserve breach next period with no invoice amount attached -> must reach the
     Director (the USD 10,000 threshold baseline misses it by construction);
   * duplicate flood of harmless events (exact reconciliations, routine tickets) -> must not alert.

Everything is SIMULATED with labels written by the generator before routing. These numbers say how
the router behaves on this generator; they do not predict alert rates in a real company.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval import ops_benchmark as ob  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
ROUTERS = ("cashbridge", "baseline_every_event", "baseline_amount_threshold")


def wilson(k: int, n: int, z: float = 1.96) -> List[float]:
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def sweep(seeds: List[int], n_paths: int = 300) -> Dict[str, Any]:
    per_seed, pooled = [], {r: {"alerts": 0, "false": 0, "missed": 0, "needed": 0} for r in ROUTERS}
    events_total = 0
    for seed in seeds:
        s = ob.run(100, seed=seed, n_paths=n_paths)["summary"]
        events_total += s["raw_events"]
        row = {"seed": seed}
        for r in ROUTERS:
            m = s[r]
            pooled[r]["alerts"] += m["director_alerts"]
            pooled[r]["false"] += m["false_alerts"]
            pooled[r]["missed"] += m["missed"]
            pooled[r]["needed"] += m["needed"]
            row[r] = {k: m[k] for k in ("director_alerts", "false_alerts", "missed", "needed")}
        row["safety_violations"] = s["safety_violations"]
        per_seed.append(row)
    summary = {}
    for r, p in pooled.items():
        summary[r] = {"alerts_per_100_events": round(100 * p["alerts"] / events_total, 1),
                      "false_alerts_per_100_events": round(100 * p["false"] / events_total, 1),
                      "missed": p["missed"], "needed": p["needed"],
                      "miss_rate": round(p["missed"] / p["needed"], 4) if p["needed"] else None,
                      "miss_rate_wilson95": wilson(p["missed"], p["needed"])}
    seeds_with_miss = sum(1 for row in per_seed if row["cashbridge"]["missed"])
    return {"seeds": seeds, "events": events_total, "n_paths": n_paths, "pooled": summary,
            "seeds_with_any_cashbridge_miss": seeds_with_miss,
            "safety_violations_total": sum(r["safety_violations"] for r in per_seed), "per_seed": per_seed}


def _case(result: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    return next(r for r in result["cases"] if r["case"] == case_id)


def stress(n_paths: int = 300) -> List[Dict[str, Any]]:
    base = ob.generate(100, 42)
    out = []

    breach = {"family": "cash_alert", "entity": "cash@burst", "amount": None,
              "payload": {"projected_balances": ["-1500", "25000", "25000"], "minimum_reserve": "10000"}}
    burst = base + [dict(copy.deepcopy(breach), raw_id=f"BURST-{i:02d}") for i in range(30)]
    r = ob.run(events=burst, n_paths=n_paths)
    c = _case(r, "cash_alert:cash@burst")
    out.append({"scenario": "Burst: one reserve breach reported 30 times", "observed": {"raw_events": c["raw_events"], "routed": c["routed"],
                "director_alerts_total": r["summary"]["cashbridge"]["director_alerts"], "missed": r["summary"]["cashbridge"]["missed"]},
                "passed": c["routed"] == "director" and c["raw_events"] == 30 and r["summary"]["cashbridge"]["missed"] == 0})

    small = base + [{"family": "cash_alert", "entity": "cash@small", "amount": None, "raw_id": "SMALL-1",
                     "payload": {"projected_balances": ["9990.00", "25000"], "minimum_reserve": "10000"}}]
    r = ob.run(events=small, n_paths=n_paths)
    c = _case(r, "cash_alert:cash@small")
    threshold_routes = "director" if c["amount"] >= 10000 else "other"
    out.append({"scenario": "Critical but small: reserve missed by USD 10 next period, no amount attached",
                "observed": {"cashbridge": c["routed"], "label": c["label"], "threshold_baseline": threshold_routes},
                "passed": c["routed"] == "director" == c["label"] and threshold_routes != "director"})

    harmless = [{"family": "reconcile", "entity": "TX-OK", "amount": 25000.0, "raw_id": f"OK-{i}",
                 "payload": {"ledger": [{"reference": "TX-OK", "amount": "25000.00"}], "bank": [{"reference": "TX-OK", "amount": "25000.00"}]}}
                for i in range(20)]
    harmless += [{"family": "support", "entity": "T-ROUTINE", "amount": None, "raw_id": f"TK-{i}",
                  "payload": {"message": "Can I change the billing address?"}} for i in range(20)]
    r0 = ob.run(events=base, n_paths=n_paths)["summary"]["cashbridge"]
    r = ob.run(events=base + harmless, n_paths=n_paths)
    out.append({"scenario": "Flood: 40 harmless duplicates (exact reconciliations, routine tickets)",
                "observed": {"director_alerts_before": r0["director_alerts"], "director_alerts_after": r["summary"]["cashbridge"]["director_alerts"],
                             "reconcile_routed": _case(r, "reconcile:TX-OK")["routed"], "ticket_routed": _case(r, "support:T-ROUTINE")["routed"]},
                "passed": r["summary"]["cashbridge"]["director_alerts"] == r0["director_alerts"]
                and _case(r, "reconcile:TX-OK")["routed"] == "none"})
    return out


def write(result: Dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "ops_robustness.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    sw = result["sweep"]
    names = {"cashbridge": "CashBridge router", "baseline_every_event": "Notify on every event", "baseline_amount_threshold": "Notify if amount >= USD 10,000"}
    lines = ["# Executive Inbox robustness (T16)", "",
             f"`python eval/ops_robustness.py --seeds {len(sw['seeds'])}`. SIMULATED events and generator-written labels; "
             "not a measurement on a real company.", "",
             f"## Seed sweep: {len(sw['seeds'])} seeds x 100 events = {sw['events']} events", "",
             "| Router | Alerts / 100 events | False alerts / 100 events | Missed / needed | Miss rate (Wilson 95%) |", "|---|---|---|---|---|"]
    for r in ROUTERS:
        p = sw["pooled"][r]
        lo, hi = p["miss_rate_wilson95"]
        lines.append(f"| {names[r]} | {p['alerts_per_100_events']} | {p['false_alerts_per_100_events']} | {p['missed']} / {p['needed']} | "
                     f"{p['miss_rate']:.1%} ({lo:.1%} to {hi:.1%}) |")
    lines += ["", f"Seeds where CashBridge missed at least one Director-needed case: **{sw['seeds_with_any_cashbridge_miss']}** of {len(sw['seeds'])}. "
              f"Side-effect safety violations across all runs: **{sw['safety_violations_total']}**.", "",
              "## Stress cases", "", "| Scenario | Holds | Observed |", "|---|---|---|"]
    for s in result["stress"]:
        lines.append(f"| {s['scenario']} | {'yes' if s['passed'] else '**NO**'} | `{json.dumps(s['observed'])}` |")
    lines += ["", "## Limits", "",
              "- Labels and events come from the same generator family; zero misses here is an upper bound on real-world performance, not a guarantee.",
              "- The upper end of the Wilson interval is the honest headline: with this many Director-needed cases, a miss rate up to that value "
              "cannot be ruled out.", "- Real deployment needs a shadow period on live events with human-labelled outcomes."]
    path = REPORT_DIR / "ops_robustness.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--paths", type=int, default=300)
    args = parser.parse_args(argv)
    result = {"synthetic": True, "sweep": sweep(list(range(1, args.seeds + 1)), args.paths), "stress": stress(args.paths)}
    print(write(result))
    print(json.dumps(result["sweep"]["pooled"], indent=2))
    for s in result["stress"]:
        print(("PASS " if s["passed"] else "FAIL ") + s["scenario"], s["observed"])
    return 0 if all(s["passed"] for s in result["stress"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
