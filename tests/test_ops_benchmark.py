"""Operations benchmark: deterministic, no side effects, far fewer Director alerts than notify-everything."""

import json

from config.settings import EXECUTION_EVIDENCE_DIR
from eval import ops_benchmark as ob


def test_small_ops_benchmark_is_deterministic_and_safe():
    a, b = ob.run(n_events=40, seed=3, n_paths=200), ob.run(n_events=40, seed=3, n_paths=200)
    sa, sb = dict(a["summary"]), dict(b["summary"])
    sa.pop("mean_latency_ms"); sb.pop("mean_latency_ms")
    assert sa == sb
    s = a["summary"]
    assert s["safety_violations"] == 0 and s["cases"] <= s["raw_events"]
    assert s["cashbridge"]["director_alerts"] < s["baseline_every_event"]["director_alerts"]


def test_committed_ops_benchmark_matches_its_cases():
    d = json.loads((EXECUTION_EVIDENCE_DIR / "ops_benchmark.json").read_text())
    rows = d["cases"]
    assert d["summary"]["cases"] == len(rows) and sum(r["raw_events"] for r in rows) == d["summary"]["raw_events"]
    assert d["summary"]["cashbridge"]["director_alerts"] == sum(1 for r in rows if r["routed"] == "director")
    assert d["summary"]["safety_violations"] == 0
