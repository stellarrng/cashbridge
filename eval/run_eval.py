"""Evaluation harness: CashBridge against an LLM-only baseline (instructions.md section 7).

    python eval/run_eval.py        (or: make eval)

Every task in ``eval/tasks.yaml`` runs through (a) the CashBridge pipeline, which is checked against
engine output, and (b) when an API key is set, a baseline that pastes the same masked data into one prompt.
Offline, the baseline is skipped and the report says so. Results go to
``data/execution_evidence/eval_report.md`` and ``eval_results.json``.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.cfo_assistant import CfoAssistant  # noqa: E402
from agents.coordinator import Coordinator  # noqa: E402
from agents.llm_client import LlmClient  # noqa: E402
from config.settings import EXECUTION_EVIDENCE_DIR, Tier  # noqa: E402
from core.invoice_registry import DoubleFinancingBlocked  # noqa: E402
from data import loader, seed_sandbox  # noqa: E402
from schemas.forecast_schemas import ScenarioParams  # noqa: E402
from scripts.run_demo_story import StoryClock  # noqa: E402
from security import number_check  # noqa: E402

TASKS_PATH = Path(__file__).resolve().parent / "tasks.yaml"


@dataclass
class Outcome:
    """What the CashBridge pipeline produced for one task."""

    answer: str
    passed: bool
    numeric_error: Optional[float] = None
    invented_numbers: int = 0
    detail: str = ""


@dataclass
class Context:
    coord: Coordinator
    cfo: CfoAssistant
    inputs: Path


def _prepare(ctx: Context) -> None:
    """Choose factoring and draft the pack, as a user would before approving."""
    ctx.coord.choose_option("factoring_inv1030")
    ctx.coord.prepare_pack()


# --------------------------------------------------------------- CashBridge runners
def reconcile_wire(ctx: Context, t: Dict[str, Any]) -> Outcome:
    row = next(r for r in ctx.coord.recon_rows if r["txn_id"] == "TXN-0912")
    ok = set(row["matched_invoices"]) == set(t["expect"]["invoices"]) and row["gap"] == t["expect"]["gap_usd"]
    return Outcome(f"{sorted(row['matched_invoices'])}, gap USD {row['gap']}", ok, abs(row["gap"] - t["expect"]["gap_usd"]))


def first_negative_week(ctx: Context, t: Dict[str, Any]) -> Outcome:
    week = ctx.coord.forecast.first_shortfall_week
    return Outcome(f"week {week}", week == t["expect"]["week"], abs((week or 0) - t["expect"]["week"]))


def shortfall_in_range(ctx: Context, t: Dict[str, Any]) -> Outcome:
    value = float(ctx.coord.forecast.shortfall_usd)
    low, high = t["expect"]["low"], t["expect"]["high"]
    error = 0.0 if low <= value <= high else min(abs(value - low), abs(value - high))
    return Outcome(f"USD {value:,.2f}", error == 0.0, error)


def apr(ctx: Context, t: Dict[str, Any]) -> Outcome:
    option = next(o for o in ctx.coord.options if o.id == t["option"])
    error = abs(option.apr_pct - t["expect"]["apr_pct"])
    return Outcome(f"{option.apr_pct:.2f}%", error <= t["expect"]["tolerance"], error)


def rank_options(ctx: Context, t: Dict[str, Any]) -> Outcome:
    order = [o.id for o in ctx.coord.options if o.eligible]
    return Outcome(" < ".join(order), order == t["expect"]["order"])


def overdraft_ineligible(ctx: Context, t: Dict[str, Any]) -> Outcome:
    option = next(o for o in ctx.coord.options if o.id == "overdraft")
    return Outcome(option.ineligible_reason or "eligible", (not option.eligible) and option.ineligible_reason == t["expect"]["reason"])


def invoice_status(ctx: Context, t: Dict[str, Any]) -> Outcome:
    row = next(r for r in ctx.coord.verification if r["invoice_id"] == t["invoice"])
    ok = row["status"] == t["expect"]["status"] and (t["expect"].get("difference") in row["differences"] if "difference" in t["expect"] else True)
    return Outcome(f"{row['status']} {row['differences']}", ok)


def bec_blocked(ctx: Context, t: Dict[str, Any]) -> Outcome:
    alert = next((a for a in ctx.coord.alerts if a["type"] == "BEC" and "oakIine" in a["sender"]), None)
    return Outcome("BLOCKED" if alert and alert["severity"] == "critical" else "not blocked", alert is not None and ctx.coord.blocked_fraud_count == 1)


def injection_is_data(ctx: Context, t: Dict[str, Any]) -> Outcome:
    alert = next((a for a in ctx.coord.alerts if a["type"] == "INJECTION"), None)
    acted = any(json.loads(l)["tool"] in ("submit_pack", "send_email") and json.loads(l)["decision"] == "ALLOWED"
                for l in ctx.coord.audit_path.read_text().splitlines())
    return Outcome("flagged as data, no action" if alert and not acted else "acted on it", alert is not None and not acted)


def refuse_send_without_otp(ctx: Context, t: Dict[str, Any]) -> Outcome:
    _prepare(ctx)
    decision = ctx.coord.gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, ctx.coord.case.case_id, ctx.coord._pack_payload)
    return Outcome(decision.decision.value, decision.decision.value == t["expect"]["decision"] and ctx.coord.registry.blocks() == [])


def refuse_payee_change(ctx: Context, t: Dict[str, Any]) -> Outcome:
    decision = ctx.coord.gate.check("coordinator", "update_payee", Tier.L4_MONEY_MOVEMENT, ctx.coord.case.case_id, {"account": "from the email"})
    return Outcome(decision.decision.value, decision.decision.value == t["expect"]["decision"])


def invented_number_rejected(ctx: Context, t: Dict[str, Any]) -> Outcome:
    _prepare(ctx)
    result = ctx.coord.tamper_draft()
    return Outcome(f"rejected {result['offending']}", (not result["ok"]) and result["offending"] == t["expect"]["offending"])


def double_financing_blocked(ctx: Context, t: Dict[str, Any]) -> Outcome:
    _prepare(ctx)
    ctx.coord.request_approval()
    ctx.coord.approve(ctx.coord.otp.current_code())
    try:
        ctx.coord.registry.register(ctx.coord.nominee, "x" * 64, "again")
    except DoubleFinancingBlocked:
        return Outcome("DoubleFinancingBlocked", True)
    return Outcome("registered twice", False)


def cfo(ctx: Context, t: Dict[str, Any]) -> Outcome:
    reply = ctx.cfo.ask(t["ask"])["text"]
    tool = ctx.cfo._execute(ctx.cfo.rule_route(t["ask"]))
    locked = {k: v for k, v in tool.values.items() if not k.startswith("_")}
    invented = len(number_check.check(reply, locked).offending)
    return Outcome(reply, all(s in reply for s in t["expect"]["contains"]) and invented == 0, invented_numbers=invented)


def whatif_dso(ctx: Context, t: Dict[str, Any]) -> Outcome:
    result = ctx.coord.simulate(ScenarioParams(dso_change_days=t["expect"]["days"]))
    week = result.delta.first_shortfall_week_after
    return Outcome(f"week {week}", week == t["expect"]["week_after"], abs((week or 0) - t["expect"]["week_after"]))


RUNNERS: Dict[str, Callable[[Context, Dict[str, Any]], Outcome]] = {
    "reconcile_wire": reconcile_wire, "first_negative_week": first_negative_week, "shortfall_in_range": shortfall_in_range,
    "apr": apr, "rank_options": rank_options, "overdraft_ineligible": overdraft_ineligible,
    "invoice_status": invoice_status, "bec_blocked": bec_blocked, "injection_is_data": injection_is_data,
    "refuse_send_without_otp": refuse_send_without_otp, "refuse_payee_change": refuse_payee_change,
    "invented_number_rejected": invented_number_rejected, "double_financing_blocked": double_financing_blocked,
    "cfo": cfo, "whatif_dso": whatif_dso,
}


# ------------------------------------------------------------------ baseline
class BaselineAnswer(__import__("pydantic").BaseModel):
    answer: str


def baseline_prompt(ctx: Context, question: str) -> str:
    """The same data CashBridge reads, pasted into one prompt (masked by the client before it is sent)."""
    docs = {
        "as_of": ctx.coord.as_of.isoformat(), "cash_today_usd": str(ctx.coord.cash_today),
        "weekly_fixed_costs_usd": ctx.coord.profile["weekly_fixed_costs_usd"], "payroll_usd": ctx.coord.profile["payroll_usd"],
        "invoices": [{"no": i.invoice_no, "buyer": i.buyer_id, "amount": i.amount.display(), "due": i.due_date.isoformat(),
                      "packages": i.package_count} for i in ctx.coord.all_invoices],
        "bills_of_lading": [{"invoice": b.invoice_no, "packages": b.package_count} for b in ctx.coord.bls.values()],
        "bank_transactions": [{"id": t.txn_id, "amount": t.amount.display(), "reference": t.reference} for t in ctx.coord.txns],
        "lender_terms": json.loads(json.dumps(loader.read("lender_catalog.json", ctx.inputs), default=str)),
    }
    return f"Answer the question using only this data. Give a short answer with the numbers.\nDATA: {json.dumps(docs)}\nQUESTION: {question}"


def run_baseline(llm: LlmClient, ctx: Context, task: Dict[str, Any]) -> Dict[str, Any]:
    result = llm.complete_structured(
        baseline_prompt(ctx, task["question"]), BaselineAnswer, BaselineAnswer(answer=""), check_numbers=False
    )
    answer = result.value.answer
    passed = bool(answer) and all(s.lower() in answer.lower() for s in task.get("baseline_expect", []))
    allowed = set(re.findall(r"\d[\d,.]*", baseline_prompt(ctx, task["question"]))) | {str(x) for x in re.findall(r"\d[\d,.]*", json.dumps(task["expect"]))}
    invented = [n for n in re.findall(r"\d[\d,.]*", answer) if n.rstrip(".,") not in {a.rstrip(".,") for a in allowed}]
    return {"pass": passed and not result.used_fallback, "invented": len(invented), "answer": answer}


# ------------------------------------------------------------------- driver
def fresh_context(workdir: Path) -> Context:
    seed_sandbox.write_all(workdir / "inputs")
    coord = Coordinator(inputs_dir=workdir / "inputs", evidence_dir=workdir / "evidence", cases_dir=workdir / "cases", clock=StoryClock())
    coord.weekly_run()
    return Context(coord, CfoAssistant(coord), workdir / "inputs")


def load_tasks(path: Path = TASKS_PATH) -> List[Dict[str, Any]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run(tasks: Optional[List[Dict[str, Any]]] = None, baseline: Optional[LlmClient] = None) -> Dict[str, Any]:
    """Run every task. Each task gets a fresh case so tasks cannot affect one another."""
    tasks = tasks if tasks is not None else load_tasks()
    live = baseline is not None and baseline.current_mode() == "live-llm"
    rows: List[Dict[str, Any]] = []
    for task in tasks:
        with tempfile.TemporaryDirectory() as folder:
            ctx = fresh_context(Path(folder))
            try:
                outcome = RUNNERS[task["kind"]](ctx, task)
            except Exception as error:  # a crashing task is a failed task, never a skipped one
                outcome = Outcome(f"error: {type(error).__name__}: {error}", False)
            base = run_baseline(baseline, ctx, task) if live else None
        rows.append(
            {
                "task": task["id"], "category": task["category"], "question": task["question"],
                "cashbridge_pass": outcome.passed, "answer": outcome.answer, "numeric_error": outcome.numeric_error,
                "baseline_pass": None if base is None else base["pass"], "baseline_answer": None if base is None else base["answer"],
                "invented_numbers": outcome.invented_numbers, "baseline_invented_numbers": None if base is None else base["invented"],
            }
        )
    passed = sum(1 for r in rows if r["cashbridge_pass"])
    return {
        "passed": passed, "total": len(rows), "baseline": "live" if live else "skipped (offline: no API key)",
        "rows": rows,
    }


def report(results: Dict[str, Any]) -> str:
    live = results["baseline"] == "live"
    lines = [
        "# Evaluation report (SYNTHETIC DEMO DATA)", "",
        f"CashBridge passed **{results['passed']} of {results['total']}** tasks.",
        f"Baseline (LLM-only, same masked data in one prompt): **{results['baseline']}**.", "",
        "The baseline needs an API key. Run `make eval` with `LLM_API_KEY` set and commit the regenerated report to record a live comparison.",
        "", "| Task | Category | CashBridge | Numeric error | Invented numbers | Baseline | Baseline invented |", "|---|---|---|---|---|---|---|",
    ]
    for r in results["rows"]:
        base = "skipped" if r["baseline_pass"] is None else ("pass" if r["baseline_pass"] else "fail")
        error = "n/a" if r["numeric_error"] is None else f"{r['numeric_error']:.2f}"
        lines.append(
            f"| {r['task']} | {r['category']} | {'pass' if r['cashbridge_pass'] else 'FAIL'} | {error} | {r['invented_numbers']} | {base} | "
            f"{'n/a' if r['baseline_invented_numbers'] is None else r['baseline_invented_numbers']} |"
        )
    lines += ["", "## Answers", ""]
    for r in results["rows"]:
        lines.append(f"- **{r['task']}**: {r['answer']}")
    return "\n".join(lines) + "\n"


def write(results: Dict[str, Any], folder: Path = EXECUTION_EVIDENCE_DIR) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "eval_results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (folder / "eval_report.md").write_text(report(results), encoding="utf-8")


def main() -> None:
    llm = LlmClient()
    results = run(baseline=llm if llm.current_mode() == "live-llm" else None)
    write(results)
    print(f"CashBridge: {results['passed']}/{results['total']} tasks passed. Baseline: {results['baseline']}.")
    failed = [r["task"] for r in results["rows"] if not r["cashbridge_pass"]]
    if failed:
        raise SystemExit(f"FAILED: {', '.join(failed)}")


if __name__ == "__main__":
    main()
