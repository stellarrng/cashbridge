"""T06: every fault-injection scenario in eval/queue_faults.py must hold its invariant."""

import pytest

from eval import queue_faults


@pytest.mark.parametrize("title,fn", queue_faults.SCENARIOS, ids=[fn.__name__ for _, fn in queue_faults.SCENARIOS])
def test_fault_scenario_holds(tmp_path, title, fn):
    result = fn(tmp_path)
    assert result["passed"], (title, result["observed"])


def test_audit_review_rejects_unknown_decisions_and_blank_reviewers(tmp_path):
    from automation.engine import AutomationStore
    store = AutomationStore(tmp_path / "q.db")
    job = store.enqueue("accounting_reconcile", {"ledger": [{"reference": "A", "amount": "1"}],
                                                 "bank": [{"reference": "A", "amount": "2"}]}, "review-test-0001")
    store.run_pending()
    for decision in ("approved_lol", "", "accepted;DROP"):
        with pytest.raises(ValueError, match="Decision"):
            store.review_audit(job["id"], "auditor", decision)
    with pytest.raises(ValueError, match="Reviewer"):
        store.review_audit(job["id"], "  ", "rejected")
    with pytest.raises(ValueError, match="Exceptions require"):
        store.review_audit(job["id"], "auditor", "accepted")
    assert store.review_audit(job["id"], "auditor", "accepted_with_exceptions")["verified"] is True
