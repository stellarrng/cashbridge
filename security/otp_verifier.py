"""
OTP Verifier — human-in-the-loop approval gate for L3_EXTERNAL_OTP actions.

SECURITY DEFECTS FIXED IN THIS MODULE
-------------------------------------
1. AUTHENTICATION BYPASS. The previous implementation read the expected code as

       correct_otp = DEMO_OTP if DEMO_MODE else _active_sessions[sid].get("_secret_otp", "")

   `_secret_otp` was never written anywhere, so with DEMO_MODE off the expected
   value was the empty string. `"".strip() == ""` is True, so submitting a blank
   OTP approved any L3 external action — submitting funding packs, sending
   collection letters — in exactly the configuration meant for production.
   Codes are now generated with `secrets` and stored at session creation.

2. NO BINDING TO THE GATE. `request_permission(..., otp_verified=True)` took a
   caller-supplied boolean. Any code path could assert its own approval. The
   gatekeeper now takes an `otp_session_id` and asks this module whether that
   specific session approved that specific action on that specific resource.

3. SESSIONS NEVER EXPIRED despite the docstring claiming a TTL, and there was
   no attempt limit, so a 6-digit code was brute-forceable indefinitely.

4. TIMING. Comparison used `==`; now `secrets.compare_digest`.

Approval is consumed on use: one session approves one action, once.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from config.settings import (
    DEMO_MODE,
    DEMO_OTP,
    OTP_TTL_SECONDS,
    OTP_MAX_ATTEMPTS,
)

# In-memory session store. A production deployment needs a short-TTL shared
# store (Redis or equivalent); an in-process dict does not survive a restart
# and does not work behind more than one worker.
_active_sessions: Dict[str, Dict[str, Any]] = {}

# Sessions that completed verification and have not yet been consumed by the
# gatekeeper. Keyed by session_id.
_approved_sessions: Dict[str, Dict[str, Any]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(entry: Dict[str, Any]) -> None:
    """Append an OTP event to the operation log via the gatekeeper's chain."""
    # Imported lazily to avoid a circular import at module load.
    from security.permission_gatekeeper import append_chained_log

    append_chained_log(entry)


def _expired(session: Dict[str, Any]) -> bool:
    created = datetime.fromisoformat(session["created_at_utc"])
    return _now() - created > timedelta(seconds=OTP_TTL_SECONDS)


def generate_otp_session(action_name: str, target_resource: str) -> dict:
    """
    Create an OTP verification session for one L3 external action.

    The returned session approves exactly the (action_name, target_resource)
    pair given here. It cannot be replayed against a different action.

    Args:
        action_name: Action awaiting approval (e.g. 'SUBMIT_FUNDING_PACK').
        target_resource: Resource it affects (e.g. 'INV-2026-103').

    Returns:
        Dict with session_id, a human-facing message and, in demo mode only,
        the code itself.
    """
    session_id = str(uuid.uuid4())
    timestamp = _now().isoformat()

    # In demo mode the code is fixed and shown on screen so judges can drive the
    # flow. Outside demo mode it is a cryptographically random 6-digit code and
    # is never returned to the caller.
    otp_code = DEMO_OTP if DEMO_MODE else f"{secrets.randbelow(10**6):06d}"

    _active_sessions[session_id] = {
        "session_id": session_id,
        "action_name": action_name,
        "target_resource": target_resource,
        "created_at_utc": timestamp,
        "expires_at_utc": (_now() + timedelta(seconds=OTP_TTL_SECONDS)).isoformat(),
        "attempts": 0,
        "verified": False,
        "secret_otp": otp_code,
        "demo_mode": DEMO_MODE,
    }

    _log(
        {
            "timestamp_utc": timestamp,
            "permission_level": "L3_EXTERNAL_OTP",
            "action_name": "OTP_SESSION_CREATED",
            "actor": "SYSTEM_AGENT",
            "target_resource": target_resource,
            "status": "REQUIRES_OTP",
            "human_otp_verified": False,
            "reason": f"OTP session opened for '{action_name}'.",
            "details": {"session_id": session_id, "ttl_seconds": OTP_TTL_SECONDS},
        }
    )

    if DEMO_MODE:
        message = (
            f"[DEMO MODE] OTP for '{action_name}' on '{target_resource}': "
            f"enter {DEMO_OTP} to approve. Valid for {OTP_TTL_SECONDS}s."
        )
    else:
        # No delivery channel is implemented. Say so rather than implying an SMS
        # was sent.
        message = (
            f"An OTP is required to approve '{action_name}'. "
            f"NOTE: no SMS/email delivery channel is configured in this build, "
            f"so the code cannot reach you outside demo mode."
        )

    result = {
        "session_id": session_id,
        "message": message,
        "demo_mode": DEMO_MODE,
        "expires_at_utc": _active_sessions[session_id]["expires_at_utc"],
    }
    if DEMO_MODE:
        result["otp_hint"] = DEMO_OTP
    return result


def verify_otp(session_id: str, entered_otp: str, actor: str = "HUMAN_USER") -> dict:
    """
    Validate a human-entered OTP against an open session.

    Args:
        session_id: Session returned by generate_otp_session().
        entered_otp: Code entered by the approver.
        actor: Identity of the person approving.

    Returns:
        Dict with 'verified', 'session_id', 'action_name' and 'reason'.
        A successful verification marks the session approved; the gatekeeper
        consumes it exactly once.
    """
    timestamp = _now().isoformat()
    session = _active_sessions.get(session_id)

    def reject(reason: str, action: str = "OTP_VERIFICATION", target: str = "") -> dict:
        _log(
            {
                "timestamp_utc": timestamp,
                "permission_level": "L3_EXTERNAL_OTP",
                "action_name": action,
                "actor": actor,
                "target_resource": target or session_id,
                "status": "OTP_REJECTED",
                "human_otp_verified": False,
                "reason": reason,
                "details": {"session_id": session_id},
            }
        )
        return {"verified": False, "session_id": session_id, "reason": reason}

    if session is None:
        return reject("OTP session not found, already used, or expired.")

    if _expired(session):
        _active_sessions.pop(session_id, None)
        return reject(
            f"OTP session expired after {OTP_TTL_SECONDS}s. Request a new code.",
            session["action_name"],
            session["target_resource"],
        )

    if session["attempts"] >= OTP_MAX_ATTEMPTS:
        _active_sessions.pop(session_id, None)
        return reject(
            f"Too many incorrect attempts ({OTP_MAX_ATTEMPTS}). Session burned.",
            session["action_name"],
            session["target_resource"],
        )

    session["attempts"] += 1

    # Reject empty/short input outright rather than letting it reach a
    # comparison — the bypass this module previously had.
    candidate = (entered_otp or "").strip()
    expected = session["secret_otp"]
    if not candidate or not expected:
        return reject(
            "Empty OTP submitted or no code was issued for this session.",
            session["action_name"],
            session["target_resource"],
        )

    if not secrets.compare_digest(candidate, expected):
        remaining = OTP_MAX_ATTEMPTS - session["attempts"]
        return reject(
            f"Incorrect OTP. Action blocked. {max(0, remaining)} attempt(s) remaining.",
            session["action_name"],
            session["target_resource"],
        )

    # Verified. Move the session to the approved store, bound to this exact
    # action and resource, for one-time consumption by the gatekeeper.
    session["verified"] = True
    _active_sessions.pop(session_id, None)
    _approved_sessions[session_id] = {
        "session_id": session_id,
        "action_name": session["action_name"],
        "target_resource": session["target_resource"],
        "approved_at_utc": timestamp,
        "approved_by": actor,
        "expires_at_utc": session["expires_at_utc"],
    }

    reason = (
        f"Human OTP verified by {actor}. '{session['action_name']}' on "
        f"'{session['target_resource']}' is approved for a single execution."
    )
    _log(
        {
            "timestamp_utc": timestamp,
            "permission_level": "L3_EXTERNAL_OTP",
            "action_name": session["action_name"],
            "actor": actor,
            "target_resource": session["target_resource"],
            "status": "OTP_CONFIRMED",
            "human_otp_verified": True,
            "reason": reason,
            "details": {"session_id": session_id},
        }
    )

    return {
        "verified": True,
        "session_id": session_id,
        "action_name": session["action_name"],
        "target_resource": session["target_resource"],
        "approved_by": actor,
        "reason": reason,
    }


def consume_approval(
    session_id: str, action_name: str, target_resource: str
) -> Optional[Dict[str, Any]]:
    """
    Redeem a verified OTP session for one specific action. Used by the gatekeeper.

    The approval is only honoured if the action and resource match what the
    human was shown when they approved, and it is removed on success so the
    same approval cannot authorise a second action.

    Args:
        session_id: The verified session.
        action_name: Action now being attempted.
        target_resource: Resource now being acted on.

    Returns:
        The approval record, or None if there is no matching live approval.
    """
    approval = _approved_sessions.get(session_id)
    if approval is None:
        return None

    created = datetime.fromisoformat(approval["expires_at_utc"])
    if _now() > created:
        _approved_sessions.pop(session_id, None)
        return None

    if (
        approval["action_name"] != action_name
        or approval["target_resource"] != target_resource
    ):
        # A real approval being replayed against a different action is a
        # meaningful security event, not a routine miss.
        _log(
            {
                "timestamp_utc": _now().isoformat(),
                "permission_level": "L3_EXTERNAL_OTP",
                "action_name": "OTP_APPROVAL_MISMATCH",
                "actor": approval.get("approved_by", "UNKNOWN"),
                "target_resource": target_resource,
                "status": "BLOCKED",
                "human_otp_verified": False,
                "reason": (
                    f"Approval for '{approval['action_name']}' on "
                    f"'{approval['target_resource']}' was replayed against "
                    f"'{action_name}' on '{target_resource}'."
                ),
                "details": {"session_id": session_id},
            }
        )
        return None

    return _approved_sessions.pop(session_id)


def is_session_verified(session_id: str) -> bool:
    """Whether a session has been verified and not yet consumed."""
    return session_id in _approved_sessions


def _reset_for_tests() -> None:
    """Clear all session state. Test helper only."""
    _active_sessions.clear()
    _approved_sessions.clear()
