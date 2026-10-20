"""T16: Executive Inbox stays quiet and complete across seeds and under bursts / small-but-critical events."""

from eval import ops_robustness as orb


def test_wilson_interval_is_sane():
    assert orb.wilson(0, 145)[0] == 0.0 and 0.02 < orb.wilson(0, 145)[1] < 0.03
    lo, hi = orb.wilson(35, 145)
    assert lo < 35 / 145 < hi


def test_small_sweep_never_misses_and_beats_threshold_baseline():
    sw = orb.sweep([3, 11, 29], n_paths=120)
    cb, thr = sw["pooled"]["cashbridge"], sw["pooled"]["baseline_amount_threshold"]
    assert cb["missed"] == 0 and sw["safety_violations_total"] == 0
    assert cb["false_alerts_per_100_events"] < thr["false_alerts_per_100_events"]


def test_stress_cases_hold():
    results = orb.stress(n_paths=120)
    assert all(r["passed"] for r in results), [r for r in results if not r["passed"]]
