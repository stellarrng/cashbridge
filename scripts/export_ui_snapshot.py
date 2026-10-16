"""Write the real UI snapshot to ``data/execution_evidence/ui_snapshot_real.json``.

Uses the simulated story clock and a throw-away runtime folder, so the file is identical on every
run and shows exactly what the UI receives: the real week-7 shortfall, the APR ranking and the alerts.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import EXECUTION_EVIDENCE_DIR  # noqa: E402
from scripts.run_demo_story import StoryClock  # noqa: E402
from ui.backend_real import RealBackend  # noqa: E402

TARGET = EXECUTION_EVIDENCE_DIR / "ui_snapshot_real.json"


def export(target: Path = TARGET) -> Path:
    with tempfile.TemporaryDirectory() as folder:
        backend = RealBackend(runtime_dir=Path(folder), clock=StoryClock())
        snapshot = backend.get_snapshot()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(f"wrote {export()}")
