"""
Permission Gatekeeper — Enforces the 5-Tier Zero-Trust Permission State Machine.

Every system action must pass through this module. Actions are auto-approved for L0–L2,
require Human-in-the-Loop OTP for L3, and are hard-blocked for L4.
All checks are written to the immutable sandbox_operation_logs.jsonl audit trail.
"""

import json
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import (
    PermissionLevel,
    OPERATION_LOGS_PATH,
    EXECUTION_EVIDENCE_DIR,
)


# Ensure the evidence directory exists on first import
EXECUTION_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class PermissionDeniedError(Exception):
    """Raised when an action is hard-blocked by the permission gatekeeper."""
    pass


class OTPRequiredError(Exception):
    """Raised when an L3 action is attempted without OTP verification."""
    pass


def _compute_state_hash(action_name: str, target_resource: str, timestamp: str) -> str:
    """Deterministic SHA-256 hash of the action state for audit immutability."""
    raw = f"{action_name}|{target_resource}|{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _append_audit_log(log_entry: Dict[str, Any]) -> None:
    """Append a single audit log entry to the immutable JSONL operation log file."""
    with open(OPERATION_LOGS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")


def request_permission(
    permission_level: PermissionLevel,
    action_name: str,
    target_resource: str,
    actor: str = "SYSTEM_AGENT",
    otp_verified: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Core gatekeeper function. Evaluates whether the requested action is allowed
    under the 5-tier permission model and writes to the audit log.

    Args:
        permission_level: The required permission tier (L0 through L4).
        action_name: Human-readable name for the action (e.g., 'SUBMIT_FUNDING_PACK').
        target_resource: The resource being acted upon (e.g., 'INV-2026-103').
        actor: The agent or user requesting the action.
        otp_verified: Whether a valid OTP has already been confirmed (for L3 actions).
        details: Optional extra context to include in the audit log.

    Returns:
        A dict with 'approved' (bool), 'status', 'log_id', and 'reason'.

    Raises:
        PermissionDeniedError: If the action is L4 (hard-blocked, zero autonomy).
        OTPRequiredError: If the action is L3 and no OTP has been verified.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    log_id = str(uuid.uuid4())
    state_hash = _compute_state_hash(action_name, target_resource, timestamp)

    base_entry = {
        "log_id": log_id,
        "timestamp_utc": timestamp,
        "permission_level": permission_level.value,
        "action_name": action_name,
        "actor": actor,
        "target_resource": target_resource,
        "state_hash": state_hash,
        "human_otp_verified": otp_verified,
        "details": details or {},
    }

    # ── L4: HARD BLOCK — Zero autonomy, no exceptions ──────────────────────
    if permission_level == PermissionLevel.L4_MONEY_MOVEMENT:
        entry = {
            **base_entry,
            "status": "HARD_BLOCKED",
            "reason": (
                "L4_MONEY_MOVEMENT: Zero autonomy. Banking transactions and fund "
                "movements are restricted entirely to human-executed banking portals. "
                "This action cannot be delegated to any automated agent."
            ),
        }
        _append_audit_log(entry)
        raise PermissionDeniedError(entry["reason"])

    # ── L3: REQUIRES Human-in-the-Loop OTP verification ─────────────────────
    if permission_level == PermissionLevel.L3_EXTERNAL_OTP:
        if not otp_verified:
            entry = {
                **base_entry,
                "status": "REQUIRES_OTP",
                "reason": (
                    "L3_EXTERNAL_OTP: Human-in-the-Loop OTP approval is required "
                    "before submitting external documents or communications."
                ),
            }
            _append_audit_log(entry)
            raise OTPRequiredError(entry["reason"])

        # OTP has been confirmed — approve
        entry = {
            **base_entry,
            "status": "OTP_CONFIRMED",
            "reason": "L3_EXTERNAL_OTP: Human OTP verified. External action approved.",
        }
        _append_audit_log(entry)
        return {"approved": True, "status": "OTP_CONFIRMED", "log_id": log_id, "reason": entry["reason"]}

    # ── L0, L1, L2: Auto-approved ────────────────────────────────────────────
    auto_reasons = {
        PermissionLevel.L0_READ: "L0_READ: Read-only data ingestion. Auto-approved.",
        PermissionLevel.L1_ANALYZE: "L1_ANALYZE: Internal analysis and draft generation. Auto-approved.",
        PermissionLevel.L2_INTERNAL_WRITE: "L2_INTERNAL_WRITE: High-confidence internal ledger update. Auto-approved.",
    }
    entry = {
        **base_entry,
        "status": "APPROVED",
        "reason": auto_reasons[permission_level],
    }
    _append_audit_log(entry)
    return {"approved": True, "status": "APPROVED", "log_id": log_id, "reason": entry["reason"]}


def get_audit_log(last_n: int = 20) -> list:
    """Read the last N entries from the immutable operation log for display in the UI."""
    if not OPERATION_LOGS_PATH.exists():
        return []
    with open(OPERATION_LOGS_PATH, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    return lines[-last_n:]
