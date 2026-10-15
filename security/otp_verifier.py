"""
OTP Verifier — Human-in-the-Loop approval gate for all L3_EXTERNAL_OTP actions.

In demo/competition mode (DEMO_MODE=True), the valid OTP is always '123456'.
In production, this module would integrate with an SMS/email TOTP service.

Every OTP attempt (pass or fail) is logged to the audit trail.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from config.settings import DEMO_MODE, DEMO_OTP, OPERATION_LOGS_PATH, EXECUTION_EVIDENCE_DIR


EXECUTION_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# Track active OTP sessions in-memory (keyed by session_id)
# In production, this would be a short-lived Redis/DB store with TTL
_active_sessions: dict = {}


def generate_otp_session(action_name: str, target_resource: str) -> dict:
    """
    Create a new OTP verification session for an L3 external action.

    In demo mode, the OTP is always DEMO_OTP ('123456') and shown to the user.
    In production, this would trigger an SMS/email delivery.

    Args:
        action_name: The action awaiting approval (e.g., 'SUBMIT_FUNDING_PACK').
        target_resource: The resource the action will affect (e.g., 'INV-2026-103').

    Returns:
        Session dict with session_id, otp (in demo mode), and instructions.
    """
    session_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    session = {
        "session_id": session_id,
        "action_name": action_name,
        "target_resource": target_resource,
        "created_at_utc": timestamp,
        "verified": False,
        "demo_mode": DEMO_MODE,
    }
    _active_sessions[session_id] = session

    if DEMO_MODE:
        session["otp_hint"] = DEMO_OTP
        message = (
            f"[DEMO MODE] OTP for '{action_name}' on '{target_resource}': "
            f"Enter code {DEMO_OTP} to approve."
        )
    else:
        message = (
            f"An OTP has been sent to your registered contact. "
            f"Enter the code to approve '{action_name}'."
        )

    return {
        "session_id": session_id,
        "message": message,
        "demo_mode": DEMO_MODE,
        **({"otp_hint": DEMO_OTP} if DEMO_MODE else {}),
    }


def verify_otp(session_id: str, entered_otp: str, actor: str = "HUMAN_USER") -> dict:
    """
    Validate the OTP provided by the human user for an active L3 session.

    Args:
        session_id: The session ID returned by generate_otp_session().
        entered_otp: The 6-digit code entered by the user.
        actor: Identifier of the person approving (e.g., 'CFO_DEMO_USER').

    Returns:
        Dict with 'verified' (bool), 'session_id', 'action_name', and 'reason'.
    """
    import json

    timestamp = datetime.now(timezone.utc).isoformat()
    log_id = str(uuid.uuid4())

    if session_id not in _active_sessions:
        log_entry = {
            "log_id": log_id,
            "timestamp_utc": timestamp,
            "permission_level": "L3_EXTERNAL_OTP",
            "action_name": "OTP_VERIFICATION",
            "actor": actor,
            "target_resource": session_id,
            "state_hash": hashlib.sha256(f"INVALID|{session_id}|{timestamp}".encode()).hexdigest(),
            "status": "REJECTED",
            "human_otp_verified": False,
            "reason": "OTP session not found or expired.",
        }
        with open(OPERATION_LOGS_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        return {"verified": False, "reason": "Session not found or expired. Please generate a new OTP."}

    session = _active_sessions[session_id]

    # Determine correct OTP (demo or production)
    correct_otp = DEMO_OTP if DEMO_MODE else _active_sessions[session_id].get("_secret_otp", "")

    verified = entered_otp.strip() == correct_otp
    status = "OTP_CONFIRMED" if verified else "OTP_REJECTED"
    reason = (
        f"Human OTP verified. '{session['action_name']}' on '{session['target_resource']}' is approved."
        if verified else
        "Incorrect OTP. Action blocked. Please try again."
    )

    log_entry = {
        "log_id": log_id,
        "timestamp_utc": timestamp,
        "permission_level": "L3_EXTERNAL_OTP",
        "action_name": session["action_name"],
        "actor": actor,
        "target_resource": session["target_resource"],
        "state_hash": hashlib.sha256(
            f"{session['action_name']}|{session['target_resource']}|{timestamp}".encode()
        ).hexdigest(),
        "status": status,
        "human_otp_verified": verified,
        "reason": reason,
    }

    with open(OPERATION_LOGS_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    if verified:
        session["verified"] = True
        # Clean up session after successful use (one-time tokens)
        _active_sessions.pop(session_id, None)

    return {
        "verified": verified,
        "session_id": session_id,
        "action_name": session["action_name"],
        "log_id": log_id,
        "reason": reason,
    }


def is_session_verified(session_id: str) -> bool:
    """Check if a session was already successfully verified (stateful check)."""
    return _active_sessions.get(session_id, {}).get("verified", False)
