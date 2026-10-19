"""Evaluation harness (Step 5.4)."""

import json
from pathlib import Path

import pytest

from agents.llm_client import LlmClient
from eval import run_eval
from ui.backend_real import RealBackend
from scripts.run_demo_story import StoryClock


@pytest.fixture(scope="module")
def results():
    return run_eval.run()


def test_task_file_has_fifteen_to_twenty_distinct_tasks_covering_the_spec_list():
    tasks = run_eval.load_tasks()
    assert 15 <= len(tasks) <= 20
    assert len({t["id"] for t in tasks}) == len(tasks)
    categories = {t["category"] for t in tasks}
    assert categories >= {"reconcile", "forecast", "funding", "verification", "fraud", "controls", "cfo", "scenario"}
    assert all(t["kind"] in run_eval.RUNNERS for t in tasks)


def test_every_cashbridge_task_passes_offline_and_the_baseline_is_skipped(results):
    assert results["passed"] == results["total"] and results["total"] >= 15
    assert results["baseline"].startswith("skipped")
    assert all(r["baseline_pass"] is None for r in results["rows"])
    assert all(r["invented_numbers"] == 0 for r in results["rows"])


def test_numeric_errors_are_reported_for_numeric_tasks(results):
    rows = {r["task"]: r for r in results["rows"]}
    assert rows["apr_factoring"]["numeric_error"] < 0.1 and rows["first_negative_week"]["numeric_error"] == 0
    assert rows["rank_options"]["numeric_error"] is None


def test_the_harness_can_fail(tmp_path):
    tasks = run_eval.load_tasks()
    wrong = [{**t, "expect": {**t["expect"], "week": 3}} for t in tasks if t["id"] == "first_negative_week"]
    outcome = run_eval.run(wrong)
    assert outcome["passed"] == 0 and outcome["rows"][0]["numeric_error"] == 4


def test_a_crashing_task_counts_as_failed_not_skipped():
    broken = [{"id": "boom", "category": "x", "kind": "invoice_status", "invoice": "INV-0000", "question": "?", "expect": {"status": "X"}}]
    outcome = run_eval.run(broken)
    assert outcome["total"] == 1 and outcome["passed"] == 0 and outcome["rows"][0]["answer"].startswith("error")


def test_each_task_gets_a_fresh_case():
    tasks = [t for t in run_eval.load_tasks() if t["id"] in ("double_financing_blocked", "refuse_send_without_otp")]
    assert run_eval.run(tasks)["passed"] == 2  # financing in one task must not leak into the next


def test_live_baseline_is_graded_and_invented_numbers_are_counted():
    class Provider:
        def __init__(self, answer):
            self.answer = answer

        def __call__(self, messages, model, timeout):
            return json.dumps({"answer": self.answer})

    task = [t for t in run_eval.load_tasks() if t["id"] == "first_negative_week"]
    good = run_eval.run(task, LlmClient(base_url="x", model="m", api_key="k", provider=Provider("Cash first goes negative in week 7.")))
    assert good["baseline"] == "live" and good["rows"][0]["baseline_pass"] is True and good["rows"][0]["baseline_invented_numbers"] == 0
    bad = run_eval.run(task, LlmClient(base_url="x", model="m", api_key="k", provider=Provider("Week 11, about 318,000 short.")))
    assert bad["rows"][0]["baseline_pass"] is False and bad["rows"][0]["baseline_invented_numbers"] >= 1
    assert bad["passed"] == 1  # CashBridge itself is unaffected by what the baseline says


def test_baseline_prompt_is_masked_before_it_leaves():
    seen = []

    def provider(messages, model, timeout):
        seen.append(json.dumps(messages))
        return json.dumps({"answer": "x"})

    run_eval.run([t for t in run_eval.load_tasks() if t["id"] == "first_negative_week"],
                 LlmClient(base_url="x", model="m", api_key="k", provider=provider))
    assert seen and "0312345678" not in seen[0]  # the seller tax ID in the prompt data is replaced by a token


def test_report_and_results_files(results, tmp_path):
    run_eval.write(results, tmp_path)
    report = (tmp_path / "eval_report.md").read_text()
    assert f"**{results['passed']} of {results['total']}**" in report and "skipped" in report and "SYNTHETIC" in report
    saved = json.loads((tmp_path / "eval_results.json").read_text())
    assert saved["passed"] == results["passed"] and len(saved["rows"]) == results["total"]
    run_eval.write(run_eval.run(), tmp_path / "again")
    assert (tmp_path / "again" / "eval_results.json").read_bytes() == (tmp_path / "eval_results.json").read_bytes()


def test_evidence_tab_data_comes_from_the_results_file(results, tmp_path):
    run_eval.write(results, tmp_path)
    backend = RealBackend(runtime_dir=tmp_path / "rt", clock=StoryClock(), eval_path=tmp_path / "eval_results.json")
    data = backend.get_snapshot()["evidence"]["eval"]
    assert data["passed"] == data["total"] == results["total"]
    assert set(data["rows"][0]) >= {"task", "cashbridge_pass", "baseline_pass", "invented_numbers"}
    empty = RealBackend(runtime_dir=tmp_path / "rt2", clock=StoryClock(), eval_path=tmp_path / "missing.json")
    assert empty.get_snapshot()["evidence"]["eval"] is None


def test_committed_report_is_current(results):
    committed = json.loads((Path(__file__).resolve().parent.parent / "data" / "execution_evidence" / "eval_results.json").read_text())
    assert committed == json.loads(json.dumps(results)), "run `make eval` and commit the result"
