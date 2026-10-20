"""Summarise UAT sessions recorded with docs/UAT_PROTOCOL.md.

    python eval/uat_summary.py reports/uat_results.csv   # writes reports/uat_summary.md

CSV columns (one row per participant x task; SUS columns only on that participant's first row):
participant,role,task,completed_unaided,time_s,errors,assists,critical_error,seq,sus1,...,sus10
Refuses to summarise an empty file: no results means "not done", never invented numbers.
"""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path
from typing import Dict, List

THRESHOLDS = {"completion": 0.8, "seq": 5, "sus": 68}


def sus_score(items: List[int]) -> float:
    if len(items) != 10 or any(not 1 <= x <= 5 for x in items):
        raise ValueError("SUS needs 10 answers from 1 to 5")
    return 2.5 * sum((x - 1) if i % 2 == 0 else (5 - x) for i, x in enumerate(items))


def summarise(rows: List[Dict[str, str]]) -> Dict[str, object]:
    if not rows:
        raise ValueError("no UAT results recorded: report UAT as not done")
    tasks: Dict[str, List[Dict[str, str]]] = {}
    sus: Dict[str, List[float]] = {}
    for r in rows:
        tasks.setdefault(f"{r['role']}:{r['task']}", []).append(r)
        if r.get("sus1"):
            sus.setdefault(r["role"], []).append(sus_score([int(r[f"sus{i}"]) for i in range(1, 11)]))
    out_tasks = []
    for key, xs in sorted(tasks.items()):
        done = sum(int(x["completed_unaided"]) for x in xs) / len(xs)
        seq = statistics.median(int(x["seq"]) for x in xs)
        crit = sum(int(x["critical_error"]) for x in xs)
        out_tasks.append({"task": key, "n": len(xs), "completed_unaided": round(done, 2), "median_time_s": statistics.median(float(x["time_s"]) for x in xs),
                          "errors": sum(int(x["errors"]) for x in xs), "critical_errors": crit, "median_seq": seq,
                          "passes": done >= THRESHOLDS["completion"] and seq >= THRESHOLDS["seq"] and crit == 0})
    out_sus = {role: {"n": len(v), "mean": round(statistics.mean(v), 1), "passes": statistics.mean(v) >= THRESHOLDS["sus"]} for role, v in sus.items()}
    return {"participants": len({r["participant"] for r in rows}), "tasks": out_tasks, "sus": out_sus}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    path = Path(argv[0]) if argv else Path("reports/uat_results.csv")
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r.get("participant")]
    s = summarise(rows)
    md = ["# UAT summary", "", f"{s['participants']} participants. Thresholds: task completion >= 80% unaided, median SEQ >= 5, "
          "0 critical errors, SUS >= 68.", "", "| Task | n | Unaided | Median time (s) | Errors | Critical | Median SEQ | Pass |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {t['task']} | {t['n']} | {t['completed_unaided']:.0%} | {t['median_time_s']:.0f} | {t['errors']} | {t['critical_errors']} | "
           f"{t['median_seq']} | {'yes' if t['passes'] else '**no**'} |" for t in s["tasks"]]
    md += ["", "| Role | n | SUS mean | Pass |", "|---|---|---|---|"] + [f"| {k} | {v['n']} | {v['mean']} | {'yes' if v['passes'] else '**no**'} |"
                                                                    for k, v in s["sus"].items()]
    out = path.parent / "uat_summary.md"
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(out)
    return 0 if all(t["passes"] for t in s["tasks"]) and all(v["passes"] for v in s["sus"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
