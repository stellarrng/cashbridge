"""
Permission Gatekeeper — enforces the 5-tier permission state machine and owns
the hash-chained audit log.

TWO DEFECTS FIXED HERE
----------------------
1. THE AUDIT LOG WAS NOT CHAINED. The README advertises "SHA-256 hash-linked
   audit logs" that "detect unauthorized changes". What the code actually wrote
   was an independent `state_hash = sha256(action|target|timestamp)` per line,
   with no reference to any previous entry. Deleting a line, reordering lines
   or editing a line's `details` left every remaining hash valid. There was no
   chain and nothing was tamper-evident. Entries now carry `prev_hash` and
   `entry_hash` over the entire record, and `verify_log_integrity()` walks the
   file.

2. L3 APPROVAL WAS SELF-ASSERTED. `request_permission(..., otp_verified=True)`
   trusted a boolean from the caller, so any code path could declare its own
   human approval. The parameter is now an `otp_session_id` that is redeemed
   against the OTP module, bound to this exact action and resource, once.

HONEST LIMITATION
-----------------
A local hash chain detects edits by anyone who cannot rewrite the whole file.
It does NOT make the log immutable against whoever controls this process: that
party can recompute every hash from the genesis entry and produce a valid
chain. Tamper-EVIDENCE against an external party requires anchoring the head
hash somewhere the operator does not control — counter-signing by the funder,
periodic publication, or append-only WORM storage. `get_chain_head()` exists
so a deployment can export that anchor. Do not describe this log as immutable
in a pitch; describe it as tamper-evident to third parties once anchored.
"""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from config.settings import PermissionLevel
from config.runtime import operation_logs_path

GENESIS_PREV_HASH = "0" * 64

# Fields excluded from the hash preimage because they ARE the hash.
_UNHASHED_FIELDS = {"entry_hash"}


class PermissionDeniedError(Exception):
    """Raised when an action is hard-blocked by the gatekeeper."""


class OTPRequiredError(Exception):
    """Raised when an L3 action is attempted without a valid human approval."""


# ─────────────────────────────────────────────────────────────────────────────
# Hash-chained audit log
# ─────────────────────────────────────────────────────────────────────────────

def _canonical(entry: Dict[str, Any]) -> str:
    """
    Deterministic serialisation of a log entry for hashing.

    Sorted keys and no insignificant whitespace, so the same record always
    produces the same preimage regardless of dict insertion order.
    """
    payload = {k: v for k, v in entry.items() if k not in _UNHASHED_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _read_all_entries() -> List[Dict[str, Any]]:
    path = operation_logs_path()
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def get_chain_head() -> str:
    """
    Current head hash of the audit chain.

    Export and anchor this externally (counter-signed by the funder, published,
    or written to append-only storage) to make the log tamper-evident against
    the system operator rather than only against a casual editor.
    """
    entries = _read_all_entries()
    if not entries:
        return GENESIS_PREV_HASH
    return entries[-1].get("entry_hash", GENESIS_PREV_HASH)


def append_chained_log(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Append one entry, linked to the previous entry's hash.

    Args:
        entry: Log fields. `log_id`, `sequence`, `prev_hash` and `entry_hash`
            are assigned here and overwrite anything supplied.

    Returns:
        The stored entry, including its hashes.
    """
    existing = _read_all_entries()
    prev_hash = existing[-1].get("entry_hash", GENESIS_PREV_HASH) if existing else GENESIS_PREV_HASH

    record = dict(entry)
    record.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
    record["log_id"] = str(uuid.uuid4())
    record["sequence"] = len(existing)
    record["prev_hash"] = prev_hash
    record["entry_hash"] = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()

    with open(operation_logs_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")

    return record


def verify_log_integrity() -> Dict[str, Any]:
    """
    Walk the audit chain and report the first inconsistency.

    Checks each entry's own hash, its link to its predecessor, and that
    sequence numbers are contiguous from zero (so a deleted line is caught,
    not just an edited one).

    Legacy entries written before chaining existed have no `entry_hash`; they
    are reported as unchained rather than as tampering, because they were never
    covered by a chain in the first place.

    Returns:
        Dict with 'is_valid', 'entry_count', 'unchained_legacy_entries',
        'head_hash' and 'first_violation'.
    """
    entries = _read_all_entries()
    if not entries:
        return {
            "is_valid": True,
            "entry_count": 0,
            "unchained_legacy_entries": 0,
            "head_hash": GENESIS_PREV_HASH,
            "first_violation": None,
        }

    legacy = sum(1 for e in entries if "entry_hash" not in e)
    chained = [e for e in entries if "entry_hash" in e]

    prev_hash = GENESIS_PREV_HASH
    expected_sequence = chained[0].get("sequence", 0) if chained else 0

    for e in chained:
        recomputed = hashlib.sha256(_canonical(e).encode("utf-8")).hexdigest()
        if recomputed != e["entry_hash"]:
            return {
                "is_valid": False,
                "entry_count": len(entries),
                "unchained_legacy_entries": legacy,
                "head_hash": entries[-1].get("entry_hash", GENESIS_PREV_HASH),
                "first_violation": (
                    f"Entry {e.get('sequence')} ({e.get('log_id')}): content does not "
                    f"match its recorded hash."
                ),
            }
        if e["prev_hash"] != prev_hash:
            return {
                "is_valid": False,
                "entry_count": len(entries),
                "unchained_legacy_entries": legacy,
                "head_hash": entries[-1].get("entry_hash", GENESIS_PREV_HASH),
                "first_violation": (
                    f"Entry {e.get('sequence')}: prev_hash does not match the "
                    f"preceding entry — an entry was removed, reordered or inserted."
                ),
            }
        if e.get("sequence") != expected_sequence:
            return {
                "is_valid": False,
                "entry_count": len(entries),
                "unchained_legacy_entries": legacy,
                "head_hash": entries[-1].get("entry_hash", GENESIS_PREV_HASH),
                "first_violation": (
                    f"Sequence gap at entry {e.get('sequence')}: expected "
                    f"{expected_sequence}."
                ),
            }
        prev_hash = e["entry_hash"]
        expected_sequence += 1

    return {
        "is_valid": True,
        "entry_count": len(entries),
        "unchained_legacy_entries": legacy,
        "head_hash": prev_hash,
        "first_violation": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# The gate
# ─────────────────────────────────────────────────────────────────────────────

def request_permission(
    permission_level: PermissionLevel,
    action_name: str,
    target_resource: str,
    actor: str = "SYSTEM_AGENT",
    otp_session_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate an action against the 5-tier permission model and log the decision.

    L0-L2 are auto-approved. L3 requires a verified OTP session that was opened
    for this exact action and resource, and is consumed on use. L4 is blocked
    unconditionally.

    Args:
        permission_level: Tier the action requires.
        action_name: Action being attempted.
        target_resource: Resource it affects.
        actor: Agent or user requesting it.
        otp_session_id: Verified OTP session for an L3 action. A boolean flag is
            no longer accepted — approval must be redeemable against the OTP
            module, not asserted by the caller.
        details: Extra context recorded in the audit entry.

    Returns:
        Dict with 'approved', 'status', 'log_id' and 'reason'.

    Raises:
        PermissionDeniedError: On any L4 request.
        OTPRequiredError: On an L3 request without a valid, matching approval.
    """
    base = {
        "permission_level": permission_level.value,
        "action_name": action_name,
        "actor": actor,
        "target_resource": target_resource,
        "details": details or {},
    }

    # ── L4: hard block, no exceptions ─────────────────────────────────────
    if permission_level == PermissionLevel.L4_MONEY_MOVEMENT:
        reason = (
            "L4_MONEY_MOVEMENT: zero autonomy. Fund movement is restricted to "
            "human-executed banking portals and cannot be delegated to any agent."
        )
        append_chained_log({**base, "status": "HARD_BLOCKED", "human_otp_verified": False, "reason": reason})
        raise PermissionDeniedError(reason)

    # ── L3: requires a redeemable human approval ──────────────────────────
    if permission_level == PermissionLevel.L3_EXTERNAL_OTP:
        from security.otp_verifier import consume_approval

        approval = (
            consume_approval(otp_session_id, action_name, target_resource)
            if otp_session_id
            else None
        )
        if approval is None:
            reason = (
                "L3_EXTERNAL_OTP: a verified human OTP approval for this exact "
                "action and resource is required before any external submission "
                "or outbound message."
            )
            append_chained_log({**base, "status": "REQUIRES_OTP", "human_otp_verified": False, "reason": reason})
            raise OTPRequiredError(reason)

        reason = (
            f"L3_EXTERNAL_OTP: approved by {approval['approved_by']} at "
            f"{approval['approved_at_utc']}. Approval consumed."
        )
        entry = append_chained_log(
            {
                **base,
                "status": "OTP_CONFIRMED",
                "human_otp_verified": True,
                "approved_by": approval["approved_by"],
                "reason": reason,
            }
        )
        return {
            "approved": True,
            "status": "OTP_CONFIRMED",
            "log_id": entry["log_id"],
            "reason": reason,
        }

    # ── L0, L1, L2: auto-approved ─────────────────────────────────────────
    auto_reasons = {
        PermissionLevel.L0_READ: "L0_READ: read-only ingestion. Auto-approved.",
        PermissionLevel.L1_ANALYZE: "L1_ANALYZE: internal analysis and drafting. Auto-approved.",
        PermissionLevel.L2_INTERNAL_WRITE: "L2_INTERNAL_WRITE: internal ledger update. Auto-approved.",
    }
    reason = auto_reasons[permission_level]
    entry = append_chained_log({**base, "status": "APPROVED", "human_otp_verified": False, "reason": reason})
    return {"approved": True, "status": "APPROVED", "log_id": entry["log_id"], "reason": reason}


def get_audit_log(last_n: int = 20) -> list:
    """Return the last N audit entries for display."""
    return _read_all_entries()[-last_n:]
