"""T08: regenerate every number a judge can check, with one command.

    python eval/reproduce_all.py [--quick] [--with-deploy]      (or: make evidence)

Runs each generator as a separate process, in a fixed order, with fixed seeds, and writes
  reports/EVIDENCE_INDEX.json   machine-readable: what ran, how long, exit code, headline numbers, seeds, n
  reports/BENCHMARKS.md         the same as a table with limitations next to every number
Exit code is non-zero if any step fails. Nothing here contacts a real bank, model provider or user.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

ROOT = Path(__file__).resolve().parent.parent
EVID = ROOT / "data" / "execution_evidence"
REPORTS = ROOT / "reports"


def _json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def story() -> Dict[str, Any]:
    # run_demo_story.py raises StoryFailed (non-zero exit) on any mismatched step, so exit 0 means all 11 held.
    lines = (EVID / "sandbox_operation_logs.jsonl").read_text(encoding="utf-8").count("\n")
    return {"headline": f"11/11 story steps hold; {lines} hash-chained audit lines; byte-identical on every run",
            "n": "11 steps", "seed": "simulated clock 07:00 UTC, seeded SYNTHETIC inputs"}


def eval_harness() -> Dict[str, Any]:
    d = _json(EVID / "eval_results.json")
    return {"headline": f"{d['passed']}/{d['total']} evaluation tasks pass", "n": d["total"], "seed": "deterministic"}


def planner() -> Dict[str, Any]:
    d = _json(EVID / "planner_benchmark.json")
    s = d["summary"]
    return {"headline": "P(goal) realised in hidden world: fixed {:.1%}, planner+memory {:.1%}, planner+learning {:.1%}".format(
        s["fixed_workflow"]["goal_success_mean"], s["planner_memory"]["goal_success_mean"], s["planner_learning"]["goal_success_mean"]),
        "n": f"{d['protocol']['test_cases']} cases x {d['protocol']['eval_paths']} paths", "seed": "cases 99, train 7, eval 50000+k"}


def ops() -> Dict[str, Any]:
    s = _json(EVID / "ops_benchmark.json")["summary"]
    cb = s["cashbridge"]
    return {"headline": f"{s['raw_events']} events -> {cb['director_alerts']} Director alerts, {cb['missed']} missed of {cb['needed']} needed",
            "n": s["raw_events"], "seed": 42}


def trust() -> Dict[str, Any]:
    s = _json(EVID / "trust_scorecard.json")["summary"]
    return {"headline": f"security {s['security']['passed']}/{s['security']['total']}, agent {s['agent']['passed']}/{s['agent']['total']}, "
                        f"Brier {s['model']['brier_model']} vs baseline {s['model']['brier_baseline']} (n={s['model']['n_predictions']})",
            "n": s["model"]["n_predictions"], "seed": "walk-forward on synthetic invoices"}


def risk() -> Dict[str, Any]:
    d = _json(REPORTS / "risk_planner.json")
    p = d["paired_risk_vs_cheapest"]["cvar95_change_usd"]
    r = d["paired_robust_vs_risk_aware"]
    return {"headline": f"risk-aware vs cheapest: CVaR95 {p['mean']:+,.0f} USD (95% CI {p['ci95'][0]:+,.0f} to {p['ci95'][1]:+,.0f}), "
                        f"cost change {d['paired_risk_vs_cheapest']['expected_cost_change_usd']['mean']:+,.0f} USD; robust vs risk-aware: "
                        f"P(goal) {r['p_goal_change']['mean']:+.1%}, CVaR95 {r['cvar95_change_usd']['mean']:+,.0f}, cost {r['expected_cost_change_usd']['mean']:+,.0f} USD",
            "n": f"{d['protocol']['cases']} cases x {d['protocol']['eval_paths']} out-of-sample paths", "seed": "cases 99, eval 90000+k"}


def robustness() -> Dict[str, Any]:
    d = _json(REPORTS / "ops_robustness.json")
    cb = d["sweep"]["pooled"]["cashbridge"]
    thr = d["sweep"]["pooled"]["baseline_amount_threshold"]
    return {"headline": f"missed {cb['missed']}/{cb['needed']} (Wilson 95% upper {cb['miss_rate_wilson95'][1]:.1%}); "
                        f"threshold baseline missed {thr['missed']}/{thr['needed']}; stress {sum(s['passed'] for s in d['stress'])}/{len(d['stress'])}",
            "n": f"{len(d['sweep']['seeds'])} seeds x 100 events", "seed": f"1..{len(d['sweep']['seeds'])}"}


def faults() -> Dict[str, Any]:
    r = _json(REPORTS / "queue_faults.json")["results"]
    return {"headline": f"{sum(x['passed'] for x in r)}/{len(r)} fault scenarios hold their invariant", "n": len(r), "seed": "deterministic"}


def fairness() -> Dict[str, Any]:
    d = _json(REPORTS / "model_fairness.json")
    ok = sum(g["within_interval"] for g in d["by_market"] + d["by_size"] + d["by_terms"])
    n = len(d["by_market"] + d["by_size"] + d["by_terms"])
    return {"headline": f"calibrated within 95% CI in {ok}/{n} groups; Brier {d['overall']['brier_full']} "
                        f"(without buyer identity {d['overall']['brier_without_buyer_identity']}); no personal attributes",
            "n": d["n_walk_forward"], "seed": "walk-forward"}


def backtest() -> Dict[str, Any]:
    rows = {r["dataset"].split(":")[0]: r for r in _json(REPORTS / "forecast_backtest.json")}
    parts = []
    for name, r in rows.items():
        m, iv = r["methods"], r["intervals"]
        parts.append(f"{name}: WAPE v8 rule {m['v8_rule']['wape']:.1%} -> v9 KM {m['km_pooled']['wape']:.1%} "
                     f"(contractual {m['contractual']['wape']:.1%}); 80% interval coverage split {iv['split_conformal']:.1%}, ACI {iv['aci']:.1%}")
    return {"headline": "; ".join(parts), "n": ", ".join(f"{r['origins']} origins / {r['invoices']} invoices" for r in rows.values()),
            "seed": "rolling origin, weekly"}


def external_buyer() -> Dict[str, Any]:
    out = []
    for s in _json(REPORTS / "external_buyer_validation.json")["splits"]:
        m = s["metrics"]
        out.append(f"{s['split']}: AUC v8 {m['M1_cashbridge_v8']['roc_auc']} vs v9 {m['M2_behavioural_v9']['roc_auc']}, "
                   f"Brier {m['M1_cashbridge_v8']['brier']} vs {m['M2_behavioural_v9']['brier']}, ECE {m['M1_cashbridge_v8']['ece']} vs {m['M2_behavioural_v9']['ece']}")
    return {"headline": "; ".join(out), "n": "2,466 public invoices, 100 customers", "seed": "customer-clustered bootstrap 500"}


def distress() -> Dict[str, Any]:
    hs = _json(REPORTS / "external_distress_validation.json")["horizons"]
    pick = lambda m: f"{min(h['metrics'][m]['roc_auc'] for h in hs):.2f}-{max(h['metrics'][m]['roc_auc'] for h in hs):.2f}"  # noqa: E731
    return {"headline": f"bankruptcy ROC-AUC over 5 horizons: CashBridge ledger ratios {pick('A_cashbridge')}, Altman Z'' {pick('altman_z2')}, "
                        f"all 64 ratios (trees) {pick('D_all_trees')}",
            "n": f"{sum(h['companies'] for h in hs)} company-years (Polish, UCI)", "seed": "stratified 5-fold CV, seed 7"}


def sba() -> Dict[str, Any]:
    d = _json(REPORTS / "external_sba_validation.json")
    m = d["metrics"]
    return {"headline": f"SBA loan default, test {d['test']['approval_fy']}: ROC-AUC logistic {m['logistic']['roc_auc']}, trees {m['boosted_trees']['roc_auc']}",
            "n": f"{d['test']['loans']} test loans", "seed": "time split by approval year"}


def external_data() -> Dict[str, Any]:
    return {"headline": "public IBM AR sample downloaded and SHA-256 verified (not redistributed)", "n": "1 file", "seed": "pinned hash"}


def deploy() -> Dict[str, Any]:
    r = _json(REPORTS / "deploy_verification.json")["results"]
    return {"headline": f"{sum(x['ok'] for x in r)}/{len(r)} production-mode checks over local HTTPS", "n": len(r), "seed": "fresh secrets each run"}


STEPS: List[Dict[str, Any]] = [
    {"id": "story", "cmd": ["scripts/run_demo_story.py"], "read": story, "limit": "SYNTHETIC case; MOCK lender."},
    {"id": "eval", "cmd": ["eval/run_eval.py"], "read": eval_harness, "limit": "Task suite written by the team."},
    {"id": "planner", "cmd": ["eval/planner_benchmark.py"], "read": planner, "limit": "Simulated quarters and a simulated hidden world.", "slow": True},
    {"id": "ops", "cmd": ["eval/ops_benchmark.py"], "read": ops, "limit": "Generator-written labels; one seed (see robustness)."},
    {"id": "trust", "cmd": ["eval/trust_scorecard.py"], "read": trust, "limit": "Adversarial cases chosen by the team; synthetic invoices for the model."},
    {"id": "risk_planner", "cmd": ["eval/risk_planner_benchmark.py", "--cases", "40"], "quick": ["eval/risk_planner_benchmark.py", "--cases", "8"],
     "read": risk, "limit": "CVaR weight fixed by policy, not tuned; simulated."},
    {"id": "ops_robustness", "cmd": ["eval/ops_robustness.py", "--seeds", "30"], "quick": ["eval/ops_robustness.py", "--seeds", "4"],
     "read": robustness, "limit": "Same generator family; real events need a shadow period."},
    {"id": "queue_faults", "cmd": ["eval/queue_faults.py"], "read": faults, "limit": "SQLite on one host; MOCK provider."},
    {"id": "model_card", "cmd": ["eval/model_fairness.py"], "read": fairness,
     "limit": "185 synthetic invoices, one buyer per market (buyer and country effects confounded)."},
    {"id": "external_data", "cmd": ["scripts/fetch_external_data.py"], "read": external_data,
     "limit": "Public anonymised sample; licence unclear, so it is downloaded, hash-checked and never packaged."},
    {"id": "forecast_backtest", "cmd": ["eval/forecast_backtest.py"], "read": backtest,
     "limit": "Receipts only (no costs or new sales); external sample has 30-day terms only."},
    {"id": "external_buyer", "cmd": ["eval/external_buyer_validation.py"], "read": external_buyer, "needs_external": True,
     "limit": "Public sample, not Vietnamese or Chinese SMEs; one label definition."},
    {"id": "distress", "cmd": ["eval/external_distress_validation.py"], "read": distress, "needs_external": "polish_5year.arff",
     "limit": "Polish companies 2000-2013; bankruptcy, not loan default; screening hint, not a credit model."},
    {"id": "sba_default", "cmd": ["eval/external_sba_validation.py"], "read": sba, "needs_external": "SBAnational.csv",
     "limit": "U.S. SBA-guaranteed loans; runs only when the file is attached (not downloadable here)."},
    {"id": "deploy", "cmd": ["scripts/verify_deployment_local.py"], "read": deploy, "limit": "Local HTTPS, not a cloud provider; no pentest.",
     "optional": True},
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="smaller sweeps; skips the minute-long planner benchmark")
    parser.add_argument("--with-deploy", action="store_true", help="also run the local production/TLS verification")
    args = parser.parse_args(argv)
    REPORTS.mkdir(exist_ok=True)
    rows = []
    for step in STEPS:
        if step.get("optional") and not args.with_deploy:
            continue
        needed = step.get("needs_external")
        if needed and not (ROOT / "data" / "external" / (needed if isinstance(needed, str) else "ar_ibm_sample.csv")).exists():
            rows.append({"id": step["id"], "skipped": f"data file {needed if isinstance(needed, str) else 'ar_ibm_sample.csv'} not present: NOT evaluated"})
            continue
        if args.quick and step.get("slow"):
            rows.append({"id": step["id"], "skipped": "quick mode"})
            continue
        cmd = [sys.executable] + (step.get("quick") if args.quick and step.get("quick") else step["cmd"])
        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        row: Dict[str, Any] = {"id": step["id"], "command": " ".join(["python"] + cmd[1:]), "exit_code": proc.returncode,
                               "seconds": round(time.perf_counter() - started, 1), "limitation": step["limit"]}
        if proc.returncode == 0:
            try:
                row.update(step["read"]())
            except Exception as error:  # a generator that ran but wrote nothing readable is a failure
                row.update(exit_code=99, headline=f"output unreadable: {error}")
        else:
            row["headline"] = "FAILED: " + (proc.stderr or proc.stdout).strip().splitlines()[-1][:300] if (proc.stderr or proc.stdout).strip() else "FAILED"
        print(f"{'ok  ' if row['exit_code'] == 0 else 'FAIL'} {step['id']:<15} {row['seconds']:>6}s  {row.get('headline', '')}")
        rows.append(row)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "n/a"
    index = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "synthetic": True, "quick": args.quick,
             "environment": {"python": platform.python_version(), "platform": platform.platform(), "git_commit": commit}, "steps": rows}
    (REPORTS / "EVIDENCE_INDEX.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    md = ["# Reproducible evidence index (T08)", "",
          f"Generated {index['generated_at']} by `python eval/reproduce_all.py{' --quick' if args.quick else ''}` "
          f"(Python {index['environment']['python']}, commit {commit}). All data SYNTHETIC; lender MOCK.", "",
          "| Step | Result | Sample / seed | Time | Limitation |", "|---|---|---|---|---|"]
    for r in rows:
        if r.get("skipped"):
            md.append(f"| {r['id']} | skipped ({r['skipped']}) | | | |")
            continue
        md.append(f"| `{r['command']}` | {'' if r['exit_code'] == 0 else '**FAILED** '}{r.get('headline', '')} | {r.get('n', '')} / {r.get('seed', '')} | "
                  f"{r['seconds']} s | {r['limitation']} |")
    md += ["", "Detailed reports: `reports/forecast_backtest.md`, `reports/external_buyer_validation.md`, `reports/risk_planner.md`, "
           "`reports/ops_robustness.md`, `reports/queue_faults.md`, "
           "`reports/deploy_verification.md`, `data/execution_evidence/*.md`."]
    (REPORTS / "BENCHMARKS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    failed = [r["id"] for r in rows if r.get("exit_code", 0) != 0]
    print("reports/BENCHMARKS.md written;", "all steps passed" if not failed else f"FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
