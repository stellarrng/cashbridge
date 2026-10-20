"""T06 fault injection for the automation queue and the outbox (at-least-once, but never twice).

    python eval/queue_faults.py         # writes reports/queue_faults.md and reports/queue_faults.json

Each scenario injects a fault (provider outage, crash after claim, zombie worker, crash between the
provider accepting and us recording it, concurrent workers, duplicate submission) and checks the
invariant that matters: bounded retries, nothing lost, and no external effect performed twice.
All handlers and the provider are local and SIMULATED.
"""

from __future__ import annotations

import collections
import json
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import automation.engine as eng  # noqa: E402
from automation import outbox  # noqa: E402
from automation.engine import AutomationStore  # noqa: E402

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def _job_row(store: AutomationStore, job_id: str) -> Dict[str, Any]:
    with store._connect() as conn:
        return dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def _due_now(store: AutomationStore, job_id: str) -> None:
    with store._connect() as conn:  # fast-forward the backoff timer (fixture time travel)
        conn.execute("UPDATE jobs SET next_run=NULL WHERE id=?", (job_id,))


def _swap_handler(fn: Callable) -> Callable[[], None]:
    original = eng.evaluate
    eng.evaluate = fn
    return lambda: setattr(eng, "evaluate", original)


def transient_outage_is_bounded(tmp: Path) -> Dict[str, Any]:
    store = AutomationStore(tmp / "q1.db")
    job = store.enqueue("support_triage", {"message": "Where is my refund?"}, "fault-transient-01")
    restore = _swap_handler(lambda k, p: (_ for _ in ()).throw(ConnectionError("provider down")))
    states, backoffs = [], []
    try:
        for _ in range(eng.MAX_ATTEMPTS + 2):
            res = store.run_pending()
            if not res:
                break
            states.append(res[0]["state"])
            if res[0]["retry_at"]:
                backoffs.append(eng.backoff_seconds(res[0]["attempts"]))
            _due_now(store, job["id"])
    finally:
        restore()
    row = _job_row(store, job["id"])
    ok = states == ["pending"] * (eng.MAX_ATTEMPTS - 1) + ["dead_letter"] and row["attempts"] == eng.MAX_ATTEMPTS and row["dead_at"]
    return {"observed": {"states": states, "backoff_seconds": backoffs, "attempts": row["attempts"]}, "passed": bool(ok)}


def invalid_payload_fails_fast(tmp: Path) -> Dict[str, Any]:
    store = AutomationStore(tmp / "q2.db")
    job = store.enqueue("collections_draft", {"invoice_number": "INV-1", "days_overdue": -4, "amount": "10"}, "fault-invalid-001")
    res = store.run_pending()
    again = store.run_pending()
    row = _job_row(store, job["id"])
    return {"observed": {"state": res[0]["state"], "attempts": row["attempts"], "rerun_picked_up": len(again)},
            "passed": res[0]["state"] == "failed" and row["attempts"] == 1 and again == []}


def unexpected_bug_is_quarantined(tmp: Path) -> Dict[str, Any]:
    store = AutomationStore(tmp / "q3.db")
    job = store.enqueue("support_triage", {"message": "hello"}, "fault-bug-000001")
    restore = _swap_handler(lambda k, p: 1 / 0)
    try:
        res = store.run_pending()
    finally:
        restore()
    dlq = [d["id"] for d in store.dead_letters()]
    return {"observed": {"state": res[0]["state"], "in_dlq": job["id"] in dlq, "error": res[0]["result"]["error"]},
            "passed": res[0]["state"] == "dead_letter" and job["id"] in dlq}


def crash_after_claim_is_recovered(tmp: Path) -> Dict[str, Any]:
    store = AutomationStore(tmp / "q4.db")
    job = store.enqueue("cash_alert", {"projected_balances": ["5000", "-200"], "minimum_reserve": "1000"}, "fault-crash-00001")
    with store._connect() as conn:  # a worker claimed it, then the container was killed
        conn.execute("UPDATE jobs SET state='running', attempts=1, lease='dead-worker', claimed_at='2020-01-01T00:00:00+00:00' WHERE id=?",
                     (job["id"],))
    recovered = store.recover_stale(older_seconds=60)
    res = store.run_pending()
    row = _job_row(store, job["id"])
    return {"observed": {"recovered": recovered, "final_state": res[0]["state"], "attempts": row["attempts"]},
            "passed": recovered == 1 and res[0]["state"] == "needs_review" and row["attempts"] == 2}


def zombie_worker_cannot_overwrite(tmp: Path) -> Dict[str, Any]:
    """Worker A stalls, the supervisor recovers its claim and worker B re-runs the job. A wakes up and
    writes WHILE B is still running: without a lease check A's stale result would win and B's be lost."""
    path = tmp / "q5.db"
    store_a, store_b = AutomationStore(path), AutomationStore(path)
    job = store_a.enqueue("support_triage", {"message": "invoice question"}, "fault-zombie-0001")
    a_started, b_started, resume_a, resume_b = (threading.Event() for _ in range(4))
    real = eng.evaluate

    def stalling(kind, payload):
        if threading.current_thread().name == "worker-A":
            a_started.set()
            resume_a.wait(5)
            return {"category": "STALE-RESULT-FROM-A", "review_required": True}
        b_started.set()
        resume_b.wait(5)
        return real(kind, payload)

    restore = _swap_handler(stalling)
    out: Dict[str, Any] = {}
    try:
        a = threading.Thread(target=lambda: out.setdefault("a", store_a.run_pending(1)), name="worker-A")
        a.start()
        a_started.wait(5)
        with store_b._connect() as conn:  # A's claim now looks stale to the supervisor
            conn.execute("UPDATE jobs SET claimed_at='2020-01-01T00:00:00+00:00' WHERE id=?", (job["id"],))
        store_b.recover_stale(older_seconds=60)
        b = threading.Thread(target=lambda: out.setdefault("b", store_b.run_pending(1)), name="worker-B")
        b.start()
        b_started.wait(5)
        resume_a.set()   # the zombie finishes first, while B still holds the live lease
        a.join(5)
        resume_b.set()
        b.join(5)
    finally:
        restore()
    row = _job_row(store_a, job["id"])
    final = json.loads(row["result"])
    return {"observed": {"worker_A": out["a"][0]["state"], "worker_B": out["b"][0]["state"], "final_category": final.get("category")},
            "passed": out["a"][0]["state"] == "lease_lost" and out["b"][0]["state"] == "needs_review"
            and final.get("category") == "billing"}


def concurrent_workers_process_each_job_once(tmp: Path, jobs: int = 120, workers: int = 6) -> Dict[str, Any]:
    path = tmp / "q6.db"
    seed = AutomationStore(path)
    ids = [seed.enqueue("support_triage", {"message": f"ticket {i}"}, f"fault-conc-{i:05d}")["id"] for i in range(jobs)]
    counter: collections.Counter = collections.Counter()
    lock = threading.Lock()
    real = eng.evaluate

    def counting(kind, payload):
        with lock:
            counter[payload["message"]] += 1
        return real(kind, payload)

    restore = _swap_handler(counting)
    start = time.perf_counter()
    try:
        def work():
            store = AutomationStore(path)
            while store.run_pending(10):
                pass
        threads = [threading.Thread(target=work) for _ in range(workers)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
    finally:
        restore()
    with seed._connect() as conn:
        states = collections.Counter(r[0] for r in conn.execute("SELECT state FROM jobs"))
    dupes = sum(1 for v in counter.values() if v > 1)
    return {"observed": {"jobs": jobs, "workers": workers, "handler_calls": sum(counter.values()), "jobs_run_twice": dupes,
                         "states": dict(states), "seconds": round(time.perf_counter() - start, 2)},
            "passed": sum(counter.values()) == jobs and dupes == 0 and states.get("needs_review") == len(ids)}


def duplicate_submission_is_one_job(tmp: Path) -> Dict[str, Any]:
    store = AutomationStore(tmp / "q7.db")
    first = store.enqueue("cash_alert", {"projected_balances": ["1"], "minimum_reserve": "5"}, "client-retry-key-1")
    second = store.enqueue("cash_alert", {"projected_balances": ["1"], "minimum_reserve": "5"}, "client-retry-key-1")
    with store._connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    return {"observed": {"same_id": first["id"] == second["id"], "rows": n}, "passed": first["id"] == second["id"] and n == 1}


def redrive_reuses_the_job(tmp: Path) -> Dict[str, Any]:
    store = AutomationStore(tmp / "q8.db")
    job = store.enqueue("support_triage", {"message": "x"}, "fault-redrive-001")
    restore = _swap_handler(lambda k, p: 1 / 0)
    try:
        store.run_pending()
    finally:
        restore()
    store.redrive(job["id"])
    res = store.run_pending()
    with store._connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    try:
        store.redrive(job["id"])
        double_redrive_refused = False
    except ValueError:
        double_redrive_refused = True
    return {"observed": {"after_redrive": res[0]["state"], "rows": n, "second_redrive_refused": double_redrive_refused},
            "passed": res[0]["state"] == "needs_review" and n == 1 and double_redrive_refused}


def outbox_crash_after_provider_accept_is_not_doubled(tmp: Path) -> Dict[str, Any]:
    path = str(tmp / "q9.db")
    store = AutomationStore(path)
    job = store.enqueue("collections_draft", {"invoice_number": "INV-1030", "days_overdue": 12, "amount": "8400.00"}, "fault-outbox-0001")
    store.run_pending()
    store.approve(job["id"], "sme.lan")
    provider = outbox.MockProvider()
    provider.fail_before_accept = 1  # outage: nothing performed
    provider.fail_after_accept = 1   # performed, but we never heard back
    rounds = [outbox.dispatch(path, provider) for _ in range(4)]
    effects = outbox.list_effects(path)
    return {"observed": {"rounds": [[r["state"] for r in rnd] for rnd in rounds], "provider_side_effects": len(provider.performed),
                         "final_state": effects[0]["state"], "receipt": effects[0]["receipt"]},
            "passed": len(provider.performed) == 1 and effects[0]["state"] == "sent" and len(effects) == 1}


def approval_and_outbox_commit_together(tmp: Path) -> Dict[str, Any]:
    path = str(tmp / "q10.db")
    store = AutomationStore(path)
    job = store.enqueue("support_reply_draft", {"ticket_id": "T-1", "category": "refund"}, "fault-atomic-0001")
    store.run_pending()
    real_stage = outbox.stage_for_approved_job

    def crash(*a, **k):
        raise sqlite3.OperationalError("disk I/O error")

    outbox.stage_for_approved_job = crash
    try:
        store.approve(job["id"], "sme.lan")
        crashed = False
    except sqlite3.OperationalError:
        crashed = True
    finally:
        outbox.stage_for_approved_job = real_stage
    state_after_crash = _job_row(store, job["id"])["state"]
    store.approve(job["id"], "sme.lan")
    return {"observed": {"crashed": crashed, "job_state_after_crash": state_after_crash,
                         "effects_after_retry": len(outbox.list_effects(path))},
            "passed": crashed and state_after_crash == "needs_review" and len(outbox.list_effects(path)) == 1}


def real_providers_are_refused(tmp: Path) -> Dict[str, Any]:
    class RealBank:
        is_mock = False
        supports_idempotency_keys = True

        def send(self, *a, **k):
            raise AssertionError("must never be called")

    class NoKeys(outbox.MockProvider):
        supports_idempotency_keys = False

    refused = []
    for p in (RealBank(), NoKeys()):
        try:
            outbox.dispatch(str(tmp / "q11.db"), p)
            refused.append(False)
        except outbox.ProviderNotAllowed:
            refused.append(True)
    return {"observed": {"refused": refused}, "passed": all(refused)}


SCENARIOS = [
    ("Transient provider outage: bounded retry with backoff, then DLQ", transient_outage_is_bounded),
    ("Invalid payload fails fast (no retry storm)", invalid_payload_fails_fast),
    ("Unexpected handler bug is quarantined in the DLQ", unexpected_bug_is_quarantined),
    ("Worker killed after claim: stale lease recovered and job completed", crash_after_claim_is_recovered),
    ("Zombie worker returns after recovery: its late write is discarded", zombie_worker_cannot_overwrite),
    ("6 concurrent workers, 120 jobs: every job handled exactly once", concurrent_workers_process_each_job_once),
    ("Client retries the same submission: one job", duplicate_submission_is_one_job),
    ("DLQ redrive reuses the same job; a second redrive is refused", redrive_reuses_the_job),
    ("Provider accepted, connection lost, worker retries: effect performed once", outbox_crash_after_provider_accept_is_not_doubled),
    ("Crash while staging the outbox rolls back the approval too", approval_and_outbox_commit_together),
    ("Non-mock or non-idempotent providers are refused", real_providers_are_refused),
]


def run_all(tmp: Path) -> List[Dict[str, Any]]:
    results = []
    for title, fn in SCENARIOS:
        try:
            r = fn(tmp)
        except Exception as error:  # a crash in a scenario is a failure, not a skip
            r = {"observed": {"exception": f"{type(error).__name__}: {error}"}, "passed": False}
        results.append({"scenario": title, "id": fn.__name__, **r})
    return results


def write_report(results: List[Dict[str, Any]], out_dir: Path = REPORT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "queue_faults.json").write_text(json.dumps({"synthetic": True, "results": results}, indent=2), encoding="utf-8")
    lines = ["# Queue and outbox fault injection (T06)", "",
             "Generated by `python eval/queue_faults.py`. Local SQLite queue, pure handlers and a MOCK provider: "
             "this shows the failure semantics, not the behaviour of a real bank or mail API.", "",
             f"**{sum(r['passed'] for r in results)}/{len(results)} scenarios hold their invariant.**", "",
             "| # | Fault injected | Holds | Observed |", "|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r['scenario']} | {'yes' if r['passed'] else '**NO**'} | `{json.dumps(r['observed'], ensure_ascii=False)}` |")
    lines += ["", "## What this does not prove", "",
              "- SQLite on one host. A multi-host deployment needs a server database or managed queue with the same lease semantics.",
              "- The provider is a mock that honours idempotency keys. A real provider must be checked to do the same "
              "(contract test) before `dispatch` may be pointed at it; the code refuses non-mock providers today.",
              "- Redrive and audit review are protected by a separate reviewer token (see tests/test_adversarial.py), "
              "not yet by per-user OIDC identities."]
    path = out_dir / "queue_faults.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        res = run_all(Path(d))
    print(write_report(res))
    for r in res:
        print(("PASS " if r["passed"] else "FAIL ") + r["scenario"])
    raise SystemExit(0 if all(r["passed"] for r in res) else 1)
