"""Period lock: a SHA-256 seal over a reconciled period.

After locking, a change never edits the lock in place. It creates version n+1 whose
hash chains to the previous version. Honest scope: a lock proves "not changed after
lock", not "correct from the start".
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel


class PeriodLockRecord(BaseModel):
    """One version of a period lock."""

    period_id: str
    version: int
    rows_sha256: str
    previous_lock_sha256: str
    lock_sha256: str


GENESIS = "0" * 64


def _rows_hash(rows: Sequence[Dict[str, Any]]) -> str:
    canonical = json.dumps(list(rows), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_hash(period_id: str, version: int, rows_sha256: str, previous: str) -> str:
    return hashlib.sha256(f"{period_id}|{version}|{rows_sha256}|{previous}".encode("utf-8")).hexdigest()


class PeriodLocks:
    """In-memory store of lock versions per period."""

    def __init__(self) -> None:
        self._versions: Dict[str, List[PeriodLockRecord]] = {}

    def lock(self, period_id: str, rows: Sequence[Dict[str, Any]]) -> PeriodLockRecord:
        """Seal ``rows``. Identical rows return the current version; changed rows add one."""
        rows_sha = _rows_hash(rows)
        history = self._versions.setdefault(period_id, [])
        if history and history[-1].rows_sha256 == rows_sha:
            return history[-1]
        previous = history[-1].lock_sha256 if history else GENESIS
        version = len(history) + 1
        record = PeriodLockRecord(
            period_id=period_id,
            version=version,
            rows_sha256=rows_sha,
            previous_lock_sha256=previous,
            lock_sha256=_lock_hash(period_id, version, rows_sha, previous),
        )
        history.append(record)
        return record

    def latest(self, period_id: str) -> Optional[PeriodLockRecord]:
        """Newest version for a period, or None if never locked."""
        history = self._versions.get(period_id)
        return history[-1] if history else None

    def verify(self, period_id: str, rows: Sequence[Dict[str, Any]]) -> bool:
        """True if ``rows`` match the newest lock and the version chain is intact."""
        history = self._versions.get(period_id)
        if not history:
            return False
        previous = GENESIS
        for record in history:
            expected = _lock_hash(record.period_id, record.version, record.rows_sha256, previous)
            if record.lock_sha256 != expected or record.previous_lock_sha256 != previous:
                return False
            previous = record.lock_sha256
        return history[-1].rows_sha256 == _rows_hash(rows)
