"""Pydantic v2 models for the case state machine, gatekeeper, audit log and approvals."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional

from pydantic import BaseModel, Field

from config.settings import Tier


class CaseState(str, Enum):
    """States of a case file (instructions.md section 3, Rule 5)."""

    NEW = "NEW"
    RECONCILED = "RECONCILED"
    FORECASTED = "FORECASTED"
    CLOSED = "CLOSED"
    SHORTFALL_DETECTED = "SHORTFALL_DETECTED"
    OPTIONS_RANKED = "OPTIONS_RANKED"
    INVOICE_VERIFIED = "INVOICE_VERIFIED"
    PACK_DRAFTED = "PACK_DRAFTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUBMITTED = "SUBMITTED"
    FUNDED = "FUNDED"
    REJECTED = "REJECTED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    BLOCKED = "BLOCKED"


_FORWARD = {
    CaseState.NEW: {CaseState.RECONCILED},
    CaseState.RECONCILED: {CaseState.FORECASTED},
    CaseState.FORECASTED: {CaseState.CLOSED, CaseState.SHORTFALL_DETECTED},
    CaseState.SHORTFALL_DETECTED: {CaseState.OPTIONS_RANKED},
    CaseState.OPTIONS_RANKED: {CaseState.INVOICE_VERIFIED},
    CaseState.INVOICE_VERIFIED: {CaseState.PACK_DRAFTED},
    CaseState.PACK_DRAFTED: {CaseState.AWAITING_APPROVAL},
    CaseState.AWAITING_APPROVAL: {CaseState.SUBMITTED},
    CaseState.SUBMITTED: {CaseState.FUNDED, CaseState.REJECTED},
}
TERMINAL_STATES: FrozenSet[CaseState] = frozenset(
    {CaseState.CLOSED, CaseState.FUNDED, CaseState.REJECTED, CaseState.BLOCKED}
)
_RESUMABLE = frozenset(_FORWARD) - {CaseState.SUBMITTED}

ALLOWED_TRANSITIONS: Dict[CaseState, FrozenSet[CaseState]] = {
    state: frozenset(targets | {CaseState.NEEDS_HUMAN, CaseState.BLOCKED})
    for state, targets in _FORWARD.items()
}
# A human resolving NEEDS_HUMAN sends the case back to any in-flight state.
ALLOWED_TRANSITIONS[CaseState.NEEDS_HUMAN] = frozenset(_RESUMABLE | {CaseState.BLOCKED})
for _terminal in TERMINAL_STATES:
    ALLOWED_TRANSITIONS[_terminal] = frozenset()


class IllegalTransition(ValueError):
    """Raised when a case tries to move to a state its current state does not allow."""


def can_transition(current: CaseState, target: CaseState) -> bool:
    """Return True if ``current`` may move to ``target``."""
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: CaseState, target: CaseState) -> None:
    """Raise IllegalTransition unless ``current`` may move to ``target``."""
    if not can_transition(current, target):
        raise IllegalTransition(f"{current.value} -> {target.value} is not allowed")


class CaseFile(BaseModel):
    """A shortfall case or an invoice nominated for funding. Owned by the coordinator."""

    case_id: str
    state: CaseState = CaseState.NEW
    resume_state: Optional[CaseState] = None
    needs_human_reason: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    history: List[str] = Field(default_factory=list)

    def move_to(self, target: CaseState, reason: str = "") -> None:
        """Move to ``target`` if the transition is legal, remembering the previous state."""
        assert_transition(self.state, target)
        if target is CaseState.NEEDS_HUMAN:
            self.resume_state = self.state
            self.needs_human_reason = reason or None
        self.history.append(f"{self.state.value}->{target.value}")
        self.state = target


class Decision(str, Enum):
    """Gatekeeper decisions recorded in the audit log."""

    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ToolCallEnvelope(BaseModel):
    """A request from an agent to run one tool."""

    agent: str
    tool: str
    tier: Tier
    case_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ApprovalRecord(BaseModel):
    """Proof that a human approved one specific action with a valid OTP."""

    approval_id: str
    action_type: str
    action_hash: str
    approver: str
    approved_at: datetime
    valid_until: datetime


class GateDecision(BaseModel):
    """The gatekeeper's answer for one tool call. Exactly one audit line backs it."""

    decision: Decision
    reason: str
    tier: Tier
    agent: str
    tool: str
    case_id: str
    action_hash: Optional[str] = None
    audit_seq: int


class AuditLine(BaseModel):
    """One hash-chained line in the audit log (instructions.md section 3, Rule 4)."""

    seq: int = Field(ge=1)
    timestamp_utc: str
    case_id: str
    agent: str
    tool: str
    tier: Tier
    decision: Decision
    reason: str
    input_sha256: str
    output_sha256: str
    prev_line_sha256: str
    line_sha256: str


class PaymentPromise(BaseModel):
    """A buyer's dated promise to pay, parsed from a reply."""

    invoice_id: str
    buyer: str
    promised_date: date
    source_text: str
