"""The trust scorecard runs offline and every adversarial / agent case passes."""

import json

import pytest

from eval import trust_scorecard
from config.settings import EXECUTION_EVIDENCE_DIR


@pytest.mark.slow
def test_scorecard_all_cases_pass():
    result = trust_scorecard.run()
    failed = [c["id"] for c in result["security"] + result["agent"] if not c["passed"]]
    assert not failed, failed
    assert result["summary"]["security"]["total"] >= 20
    assert result["model"]["n_predictions"] > 10


def test_committed_scorecard_is_current_shape():
    data = json.loads((EXECUTION_EVIDENCE_DIR / "trust_scorecard.json").read_text())
    assert data["summary"]["security"]["passed"] == data["summary"]["security"]["total"]
    assert {c["id"] for c in data["security"]} == {c[0] for c in trust_scorecard.security_cases()}
