"""
Where the audit log and the pledge registry are written, resolved at call time.

WHY THIS MODULE EXISTS
----------------------
The evidence paths used to be module-level constants imported by name into
`permission_gatekeeper` and `cryptographic_registry`. That had two
consequences, both of which a reviewer hit:

1. Everything wrote to the one committed directory. The demo therefore
   persisted its pledges into `data/execution_evidence/audit_hash_registry.json`
   — and running it a second time raised `DoubleFinancingError`, because
   `INV-2026-103` was already pledged from the first run. The packaged ZIP
   shipped with that file already populated, so the demo failed on first run
   from the archive while the README said the evidence files start empty.

2. A path bound at import time can only be redirected by monkeypatching each
   importing module individually, which is brittle and silently incomplete
   when a new module starts writing evidence.

Resolving through this module fixes both. `use_directory()` points the whole
system at a working directory; `use_fresh_run_directory()` creates an empty,
timestamped one for a demo run so that running the demo never touches, and
never depends on, committed data.

The default remains `data/execution_evidence`, which is what a real deployment
would use: operational evidence that accumulates and must NOT be wiped between
runs. That is precisely why the demo gets its own directory rather than the
demo deleting the real one on startup.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import EXECUTION_EVIDENCE_DIR, DATA_DIR

DEMO_RUNS_DIR = DATA_DIR / "demo_runs"

_active_dir: Path = EXECUTION_EVIDENCE_DIR


def evidence_dir() -> Path:
    """Directory currently receiving audit and registry writes."""
    _active_dir.mkdir(parents=True, exist_ok=True)
    return _active_dir


def operation_logs_path() -> Path:
    """Path to the hash-chained operation log."""
    return evidence_dir() / "sandbox_operation_logs.jsonl"


def registry_path() -> Path:
    """Path to the anti-double-financing hash chain."""
    return evidence_dir() / "audit_hash_registry.json"


def artifacts_dir() -> Path:
    """Directory for generated funding pack PDFs."""
    return evidence_dir()


def use_directory(path) -> Path:
    """
    Point audit and registry writes at `path`.

    Args:
        path: Directory to use. Created if absent. Existing contents are left
            alone — redirecting is not the same as resetting, and a function
            that quietly deleted operational evidence would be worse than the
            bug it fixes.

    Returns:
        The active directory.
    """
    global _active_dir
    _active_dir = Path(path)
    _active_dir.mkdir(parents=True, exist_ok=True)
    return _active_dir


def use_default_directory() -> Path:
    """Restore the committed evidence directory."""
    return use_directory(EXECUTION_EVIDENCE_DIR)


def use_fresh_run_directory(label: str = "demo") -> Path:
    """
    Create and select an empty, timestamped directory for one run.

    This is how the demo gets a clean slate without deleting anything. Each
    run is self-contained and reproducible, repeated runs cannot collide, and
    `data/execution_evidence/` stays empty in the repository.

    Args:
        label: Prefix for the directory name.

    Returns:
        The new directory.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir = DEMO_RUNS_DIR / f"{label}-{stamp}"
    counter = 1
    while run_dir.exists():
        run_dir = DEMO_RUNS_DIR / f"{label}-{stamp}-{counter}"
        counter += 1
    return use_directory(run_dir)
