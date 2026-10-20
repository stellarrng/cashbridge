"""Controlled corrections of source fields behind locked metrics (v9 provenance).

A preparer proposes "this source field should read X" with a reason; a different person (the Director)
approves or rejects it. Nothing is overwritten: the original value, the proposal and the decision are
all kept, and a locked pack is never changed. An approved correction is flagged on the lineage and
applies to the next pack the SME prepares.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CorrectionDesk:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS field_corrections (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, pack_id TEXT NOT NULL,
                metric_key TEXT NOT NULL, source_ref TEXT NOT NULL, original_value TEXT, proposed_value TEXT NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL, proposed_by TEXT NOT NULL, created TEXT NOT NULL, decided_by TEXT, decision_note TEXT, decided TEXT)""")

    def _con(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def propose(self, tenant: str, pack_id: str, metric_key: str, source_ref: str, original_value: Any, proposed_value: str,
                reason: str, actor: str) -> Dict[str, Any]:
        proposed_value, reason = (proposed_value or "").strip(), (reason or "").strip()
        if not 1 <= len(proposed_value) <= 200:
            raise ValueError("Proposed value is required (at most 200 characters)")
        if not 8 <= len(reason) <= 500:
            raise ValueError("A reason of 8-500 characters is required")
        if any(ord(c) < 32 for c in proposed_value + reason.replace("\n", " ")):
            raise ValueError("Control characters are not allowed")
        if original_value is not None and str(original_value) == proposed_value:
            raise ValueError("The proposed value equals the current value")
        rid = "COR-" + uuid.uuid4().hex[:10].upper()
        with self._con() as con:
            con.execute("INSERT INTO field_corrections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, tenant, pack_id, metric_key, source_ref[:200], None if original_value is None else str(original_value)[:200],
                         proposed_value, reason, "pending", actor, _now(), None, None, None))
        return self.get(tenant, rid)

    def decide(self, tenant: str, rid: str, actor: str, approve: bool, note: str) -> Dict[str, Any]:
        note = (note or "").strip()
        if not 3 <= len(note) <= 500:
            raise ValueError("A decision note of 3-500 characters is required")
        with self._con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM field_corrections WHERE tenant=? AND id=?", (tenant, rid)).fetchone()
            if row is None:
                raise LookupError("correction not found")
            if row["status"] != "pending":
                raise ValueError(f"Correction already {row['status']}")
            if row["proposed_by"] == actor:
                raise PermissionError("The person who proposed a correction cannot decide it")
            con.execute("UPDATE field_corrections SET status=?, decided_by=?, decision_note=?, decided=? WHERE id=?",
                        ("approved" if approve else "rejected", actor, note, _now(), rid))
        return self.get(tenant, rid)

    def get(self, tenant: str, rid: str) -> Dict[str, Any]:
        with self._con() as con:
            row = con.execute("SELECT * FROM field_corrections WHERE tenant=? AND id=?", (tenant, rid)).fetchone()
        if row is None:
            raise LookupError("correction not found")
        return self._shape(dict(row))

    def list(self, tenant: str, pack_id: str) -> List[Dict[str, Any]]:
        with self._con() as con:
            rows = con.execute("SELECT * FROM field_corrections WHERE tenant=? AND pack_id=? ORDER BY created", (tenant, pack_id)).fetchall()
        return [self._shape(dict(r)) for r in rows]

    @staticmethod
    def _shape(r: Dict[str, Any]) -> Dict[str, Any]:
        r["effect"] = {"pending": "None yet. The locked pack is unchanged.",
                       "approved": "Applies to the next pack. The locked pack and its original value are unchanged.",
                       "rejected": "None. The original value stands."}[r["status"]]
        r["locked_pack_changed"] = False
        return r
