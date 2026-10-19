"""Audit log: an append-only, hash-chained JSONL file (tamper-evident).

Each line stores the SHA-256 of the previous line, so editing, reordering or deleting a
line in the middle is detected by ``verify_chain``. Honest limits: deleting the newest
lines, or rewriting the whole file, is only caught if the chain head was anchored
elsewhere (``scripts/anchor_head.py``).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from config.settings import Tier
from schemas.agent_schemas import AuditLine, Decision

GENESIS_HASH = "0" * 64
Clock = Callable[[], datetime]


def canonical_json(value: Any) -> str:
    """Stable JSON text: sorted keys, no spaces, non-ASCII kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_of(value: Any) -> str:
    """SHA-256 hex digest of the canonical JSON form of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _line_hash(fields: Dict[str, Any]) -> str:
    body = {k: v for k, v in fields.items() if k != "line_sha256"}
    return sha256_of(body)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AuditLog:
    """Writer for one audit file. The path and clock are passed in."""

    def __init__(self, path: Path, clock: Clock = _utc_now) -> None:
        self.path = Path(path)
        self._clock = clock

    def append(
        self,
        *,
        case_id: str,
        agent: str,
        tool: str,
        tier: Tier,
        decision: Decision,
        reason: str,
        input_payload: Any = None,
        output_payload: Any = None,
    ) -> AuditLine:
        """Write one line. Inputs and outputs are stored only as SHA-256 digests."""
        lines = _read_lines(self.path)
        if lines:
            last = json.loads(lines[-1])
            seq, prev = last["seq"] + 1, last["line_sha256"]
        else:
            seq, prev = 1, GENESIS_HASH
        fields: Dict[str, Any] = {
            "seq": seq,
            "timestamp_utc": self._clock().astimezone(timezone.utc).isoformat(),
            "case_id": case_id,
            "agent": agent,
            "tool": tool,
            "tier": tier.value,
            "decision": decision.value,
            "reason": reason,
            "input_sha256": sha256_of(input_payload),
            "output_sha256": sha256_of(output_payload),
            "prev_line_sha256": prev,
        }
        fields["line_sha256"] = _line_hash(fields)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(fields, sort_keys=True, ensure_ascii=False) + "\n")
        return AuditLine(**fields)

    def tail(self, n: int = 10) -> List[Dict[str, Any]]:
        """Last ``n`` lines shaped like the UI contract ``tier_monitor`` rows."""
        rows = []
        for line in _read_lines(self.path)[-n:]:
            data = json.loads(line)
            rows.append(
                {
                    "seq": data["seq"],
                    "time": data["timestamp_utc"][11:19],
                    "agent": data["agent"],
                    "tool": data["tool"],
                    "tier": data["tier"],
                    "decision": data["decision"],
                    "reason": data["reason"],
                }
            )
        return rows

    def verify_chain(self) -> Tuple[bool, Optional[int], int]:
        """Check this log. See module-level ``verify_chain``."""
        return verify_chain(self.path)

    def head_hash(self) -> str:
        """Hash of the newest line (the value to anchor outside this machine)."""
        lines = _read_lines(self.path)
        return json.loads(lines[-1])["line_sha256"] if lines else GENESIS_HASH


def verify_chain(path: Path) -> Tuple[bool, Optional[int], int]:
    """Recompute the chain. Return (ok, first_broken_seq, lines_checked).

    ``first_broken_seq`` is the seq the broken line should have had (its position),
    or None when the whole chain is intact.
    """
    previous = GENESIS_HASH
    checked = 0
    for position, raw in enumerate(_read_lines(Path(path)), start=1):
        checked += 1
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return False, position, checked
        if (
            data.get("seq") != position
            or data.get("prev_line_sha256") != previous
            or data.get("line_sha256") != _line_hash(data)
        ):
            return False, position, checked
        previous = data["line_sha256"]
    return True, None, checked
