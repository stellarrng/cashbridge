"""UAT summary maths (SUS scoring, thresholds) and the rule that no results means 'not done'."""

import pytest

from eval.uat_summary import summarise, sus_score


def test_sus_scoring_matches_the_standard_formula():
    assert sus_score([5, 1] * 5) == 100.0
    assert sus_score([1, 5] * 5) == 0.0
    assert sus_score([3] * 10) == 50.0
    with pytest.raises(ValueError):
        sus_score([6] * 10)


def test_empty_results_are_refused_not_invented():
    with pytest.raises(ValueError, match="not done"):
        summarise([])


def test_thresholds_and_critical_errors():
    base = {"role": "bank", "task": "B2", "time_s": "120", "errors": "0", "assists": "0", "seq": "6"}
    rows = [dict(base, participant="P1", completed_unaided="1", critical_error="0", **{f"sus{i}": ("4" if i % 2 else "2") for i in range(1, 11)}),
            dict(base, participant="P2", completed_unaided="1", critical_error="1")]
    s = summarise(rows)
    assert s["tasks"][0]["passes"] is False  # one critical error fails the task even at 100% completion
    assert s["sus"]["bank"]["mean"] == 75.0 and s["sus"]["bank"]["passes"]
