"""
Packaging guards — checks that the thing a reviewer downloads actually works.

These exist because of a specific failure. The repository was packaged after
the demo and a manual PDF check had been run, so the archive shipped with
`data/execution_evidence/audit_hash_registry.json` containing a pledge for
`INV-2026-103`. A reviewer unzipping it and running `demo_walkthrough.py` hit
`DoubleFinancingError` on the first attempt — while the README stated that the
evidence files start empty.

92 unit tests passed at the time. None of them looked at what was in the box.
These do.

Note the deliberate exception to the autouse isolation fixture: these tests
inspect the real repository files on purpose, so they read paths directly
rather than going through `config.runtime`.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "data" / "execution_evidence"
REGISTRY = EVIDENCE_DIR / "audit_hash_registry.json"
OPERATION_LOG = EVIDENCE_DIR / "sandbox_operation_logs.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# Shipped state
# ─────────────────────────────────────────────────────────────────────────────

def test_committed_registry_is_empty():
    """
    A populated registry makes the demo fail on a fresh clone. It must ship
    empty, and the README must not have to apologise for it.
    """
    assert REGISTRY.exists(), "The registry file should exist, empty."
    chain = json.loads(REGISTRY.read_text() or "[]")
    assert chain == [], (
        f"{REGISTRY.name} ships with {len(chain)} pledge(s). The demo will raise "
        f"DoubleFinancingError on first run from the archive. Clear it before "
        f"packaging."
    )


def test_committed_operation_log_is_empty():
    assert OPERATION_LOG.exists(), "The operation log should exist, empty."
    body = OPERATION_LOG.read_text().strip()
    assert body == "", (
        f"{OPERATION_LOG.name} ships with "
        f"{len(body.splitlines())} entries. Clear it before packaging."
    )


def test_no_generated_funding_packs_are_committed(shipped_state):
    assert not shipped_state["committed_pdfs"], (
        f"Generated PDFs committed: {shipped_state['committed_pdfs']}. These "
        f"are run output, not source."
    )


def test_demo_run_output_is_excluded_from_packaging():
    """
    Run output must not be packaged.

    Asserting the directory is absent would be wrong twice over: the slow
    tests below run the demo and create it legitimately, and a developer who
    ran the demo an hour ago would see a spurious failure. What actually
    matters is that it is declared as ignored, which holds whether or not a
    run has happened.
    """
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore is missing, so run output can be committed."
    body = gitignore.read_text()
    assert "data/demo_runs/" in body, (
        "data/demo_runs/ is not in .gitignore. Per-run evidence would be "
        "committed and packaged."
    )
    assert "data/execution_evidence/*.pdf" in body, (
        "Generated funding packs are not ignored."
    )


# ─────────────────────────────────────────────────────────────────────────────
# The demo actually runs, twice
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_demo_runs():
    """
    Remove run directories this test creates, so running the suite locally
    does not litter the tree a reviewer then packages.
    """
    runs = REPO_ROOT / "data" / "demo_runs"
    before = set(runs.iterdir()) if runs.exists() else set()
    yield
    if runs.exists():
        import shutil

        for path in set(runs.iterdir()) - before:
            shutil.rmtree(path, ignore_errors=True)
        if not any(runs.iterdir()):
            runs.rmdir()


def _run_demo():
    return subprocess.run(
        [sys.executable, "demo_walkthrough.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.slow
def test_demo_runs_from_a_clean_checkout(clean_demo_runs):
    result = _run_demo()
    assert result.returncode == 0, (
        f"demo_walkthrough.py exited {result.returncode}.\n"
        f"STDERR:\n{result.stderr[-3000:]}"
    )
    for marker in ("STEP 1", "STEP 2", "STEP 3", "STEP 4", "STEP 5",
                   "Walkthrough complete"):
        assert marker in result.stdout, f"Demo did not reach {marker!r}"


@pytest.mark.slow
def test_demo_is_repeatable(clean_demo_runs):
    """
    The original bug in one line: the first run succeeded and the second
    failed, because run one left its pledges where run two would find them.
    """
    first = _run_demo()
    second = _run_demo()
    assert first.returncode == 0, first.stderr[-2000:]
    assert second.returncode == 0, (
        "The demo is not repeatable — the second run failed.\n"
        f"STDERR:\n{second.stderr[-3000:]}"
    )
    assert "DoubleFinancingError" not in second.stderr


@pytest.mark.slow
def test_demo_does_not_write_into_committed_evidence(clean_demo_runs):
    before_registry = REGISTRY.read_text()
    before_log = OPERATION_LOG.read_text()
    assert _run_demo().returncode == 0
    assert REGISTRY.read_text() == before_registry, (
        "The demo wrote into the committed registry. Runtime evidence belongs "
        "in a per-run directory."
    )
    assert OPERATION_LOG.read_text() == before_log, (
        "The demo wrote into the committed operation log."
    )


@pytest.mark.slow
def test_demo_writes_its_evidence_somewhere_inspectable():
    """Isolation must not mean the run leaves nothing to audit."""
    result = _run_demo()
    assert result.returncode == 0
    runs = REPO_ROOT / "data" / "demo_runs"
    assert runs.exists()
    latest = max(runs.iterdir(), key=lambda p: p.stat().st_mtime)
    chain = json.loads((latest / "audit_hash_registry.json").read_text())
    assert len(chain) >= 1, "The run produced no pledge record"
    log_lines = (latest / "sandbox_operation_logs.jsonl").read_text().strip().splitlines()
    assert len(log_lines) > 10, "The run produced almost no audit trail"


# ─────────────────────────────────────────────────────────────────────────────
# Documentation that can go stale
# ─────────────────────────────────────────────────────────────────────────────

def test_readme_does_not_hardcode_a_test_count():
    """
    The README claimed 91 tests when the suite had 92. A count written in
    prose drifts the moment a test is added; the number is better left to
    `pytest` to report.
    """
    readme = (REPO_ROOT / "README.md").read_text()
    import re

    offenders = re.findall(r"\b\d{2,4}\s+(?:tests|checks)\b", readme)
    assert not offenders, (
        f"README states a fixed test count {offenders}, which goes stale on the "
        f"next commit. Point at `pytest -q` instead."
    )


def test_demo_does_not_hardcode_a_test_count():
    body = (REPO_ROOT / "demo_walkthrough.py").read_text()
    import re

    offenders = re.findall(r"\b\d{2,4}\s+(?:tests|checks)\b", body)
    assert not offenders, f"demo_walkthrough.py states a fixed test count {offenders}"


def test_readme_evidence_claim_matches_reality():
    """The README says the evidence files start empty; they must."""
    readme = (REPO_ROOT / "README.md").read_text().lower()
    if "start empty" in readme or "starts empty" in readme:
        assert json.loads(REGISTRY.read_text() or "[]") == []
        assert OPERATION_LOG.read_text().strip() == ""
