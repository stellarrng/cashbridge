"""Action-bound one-time approvals for L3 actions (TOTP via pyotp).

An approval is valid only if it
  * matches the current TOTP code,
  * is bound to ``action_hash = SHA-256(action_type + canonical JSON payload)``,
  * is used once (consumed ``(action_hash, code)`` pairs are remembered),
  * is used within 120 seconds of the challenge.

Approving pack A therefore never authorises sending pack B, and changing the payload
after approval invalidates it.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Literal, Optional, Set, Tuple

import pyotp
from pydantic import BaseModel

from config.settings import OTP_SECRET, OTP_VALIDITY_SECONDS
from schemas.agent_schemas import ApprovalRecord
from security.audit_log import canonical_json

Clock = Callable[[], datetime]
OtpError = Literal["invalid_code", "expired", "replayed", "payload_mismatch"]


def action_hash(action_type: str, payload: Dict[str, Any]) -> str:
    """SHA-256 of the action type followed by the canonical JSON payload."""
    return hashlib.sha256((action_type + canonical_json(payload)).encode("utf-8")).hexdigest()


class Challenge(BaseModel):
    """What the approver is asked to approve."""

    action_type: str
    action_hash: str
    issued_at: datetime
    expires_at: datetime
    instructions: str


class OtpResult(BaseModel):
    """Either an approval record or one of the four contract error strings."""

    ok: bool
    error: Optional[OtpError] = None
    approval: Optional[ApprovalRecord] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OtpVerifier:
    """Issues challenges and verifies codes. The clock is injectable for tests."""

    def __init__(
        self,
        secret: str = OTP_SECRET,
        clock: Clock = _utc_now,
        validity_seconds: int = OTP_VALIDITY_SECONDS,
        approver: str = "Minh",
    ) -> None:
        self._totp = pyotp.TOTP(secret)
        self._clock = clock
        self._validity = timedelta(seconds=validity_seconds)
        self._approver = approver
        self._consumed: Set[Tuple[str, str]] = set()

    def current_code(self) -> str:
        """The code valid right now. Used only by demo automation and tests."""
        return self._totp.at(self._clock())

    def issue_challenge(self, action_type: str, payload: Dict[str, Any]) -> Challenge:
        """Bind a new challenge to this exact action and payload."""
        now = self._clock()
        digest = action_hash(action_type, payload)
        return Challenge(
            action_type=action_type,
            action_hash=digest,
            issued_at=now,
            expires_at=now + self._validity,
            instructions=(
                f"Enter the 6-digit code from the authenticator within "
                f"{int(self._validity.total_seconds())} seconds to approve {action_type} "
                f"(action_hash {digest[:12]}...)."
            ),
        )

    def verify(
        self,
        challenge: Challenge,
        code: str,
        *,
        action_type: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> OtpResult:
        """Check ``code`` against ``challenge``.

        Pass ``action_type`` and ``payload`` of the action about to run so a code issued
        for a different action (or an edited payload) is refused as payload_mismatch.
        """
        now = self._clock()
        if action_type is not None and payload is not None:
            if action_hash(action_type, payload) != challenge.action_hash:
                return OtpResult(ok=False, error="payload_mismatch")
        if now > challenge.expires_at:
            return OtpResult(ok=False, error="expired")
        pair = (challenge.action_hash, code)
        if pair in self._consumed:
            return OtpResult(ok=False, error="replayed")
        if not self._totp.verify(code, for_time=now, valid_window=1):
            return OtpResult(ok=False, error="invalid_code")
        self._consumed.add(pair)
        return OtpResult(
            ok=True,
            approval=ApprovalRecord(
                approval_id=str(uuid.uuid4()),
                action_type=challenge.action_type,
                action_hash=challenge.action_hash,
                approver=self._approver,
                approved_at=now,
                valid_until=now + self._validity,
            ),
        )
