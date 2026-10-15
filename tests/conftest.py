"""
Pytest configuration.

Every test runs against a throwaway evidence directory, selected through
`config.runtime` rather than by monkeypatching each module that happens to
write evidence. The earlier version patched three module attributes by name,
which meant a newly added writer silently escaped isolation and appended to
the committed `data/execution_evidence/` files — mutating the audit log and
the pledge registry that the demo reads.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_evidence(tmp_path):
    """Point all evidence writes at a per-test temp directory."""
    from config import runtime
    from security import otp_verifier

    run_dir = runtime.use_directory(tmp_path / "evidence")
    otp_verifier._reset_for_tests()
    try:
        yield {
            "dir": run_dir,
            "logs": runtime.operation_logs_path(),
            "registry": runtime.registry_path(),
        }
    finally:
        otp_verifier._reset_for_tests()
        runtime.use_default_directory()


@pytest.fixture(scope="session")
def shipped_state():
    """
    Snapshot of the repository as the test session found it.

    The packaging checks ask what a reviewer downloads, but the slow tests in
    the same suite run the demo, which legitimately creates
    `data/demo_runs/`. Asserting against the live filesystem makes those
    checks order-dependent — they pass alone and fail after the demo tests.
    Taken once at session start, before anything has run.
    """
    runs = ROOT / "data" / "demo_runs"
    return {
        "demo_runs_existed": runs.exists() and any(runs.iterdir()),
        "committed_pdfs": sorted(
            p.name for p in (ROOT / "data" / "execution_evidence").glob("*.pdf")
        ),
    }
