"""Write the current chain head hashes to ``data/execution_evidence/ANCHORS.md``.

Commit that file to git: it records the audit-log and registry heads outside the log files
themselves, so a later rewrite of either file no longer matches the anchored hashes. This is
the only mitigation for an admin rewriting the local chains; it does not make them
tamper-resistant. Run with ``make anchor``.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import EXECUTION_EVIDENCE_DIR  # noqa: E402
from core.invoice_registry import InvoiceRegistry  # noqa: E402
from security.audit_log import AuditLog  # noqa: E402

HEADER = """# Chain head anchors (SYNTHETIC DEMO DATA)

Each row records the head hash of the audit log and the invoice registry at one moment.
Commit this file. If either chain is later rewritten, its head will no longer match a row here.

| Anchored at (UTC) | Audit lines | Audit log head (SHA-256) | Registry blocks | Registry head (SHA-256) |
|---|---|---|---|---|
"""


def anchor(evidence_dir: Path = EXECUTION_EVIDENCE_DIR, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> str:
    """Append one anchor row and return it. Refuses to anchor a broken chain."""
    evidence_dir = Path(evidence_dir)
    audit = AuditLog(evidence_dir / "sandbox_operation_logs.jsonl")
    registry = InvoiceRegistry(evidence_dir / "invoice_registry.json")
    ok, broken, lines = audit.verify_chain()
    if not ok:
        raise SystemExit(f"audit chain is broken at line {broken}; not anchoring")
    reg_ok, reg_broken = registry.verify_chain()
    if not reg_ok:
        raise SystemExit(f"registry chain is broken at block {reg_broken}; not anchoring")
    row = (
        f"| {clock().astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} | {lines} | "
        f"`{audit.head_hash()}` | {len(registry.blocks())} | `{registry.head_hash()}` |\n"
    )
    path = evidence_dir / "ANCHORS.md"
    if not path.exists():
        path.write_text(HEADER, encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(row)
    return row


def main() -> None:
    print(anchor().strip())


if __name__ == "__main__":
    main()
