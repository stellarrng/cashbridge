"""Permission gatekeeper: every tool call goes through ``PermissionGatekeeper.check``.

Rules (instructions.md section 3, Rule 2)
  * L4 (money movement) is always BLOCKED. No tool exists for it.
  * A tool outside the agent's allowlist, or an unknown tool, is BLOCKED.
  * A call that declares a lower tier than the tool's registered tier is BLOCKED.
  * L0 and L1 are ALLOWED. L2 is ALLOWED only at confidence 1.0, otherwise the call
    waits for a human (Lan).
  * L3 needs an ApprovalRecord bound to this exact action; each approval works once and
    only within its validity window. Otherwise it waits (AWAITING_APPROVAL) or is REJECTED.

Every call writes exactly one audit line.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Set

from config.settings import Tier
from config.tool_allowlist import L4_TOOLS, TOOL_ALLOWLIST, TOOL_TIERS
from schemas.agent_schemas import ApprovalRecord, Decision, GateDecision
from security.audit_log import AuditLog
from security.otp_verifier import action_hash

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PermissionGatekeeper:
    """Decides allow / block / require-approval and writes the audit line."""

    def __init__(
        self,
        audit_log: AuditLog,
        allowlist: Optional[Dict[str, frozenset]] = None,
        clock: Clock = _utc_now,
    ) -> None:
        self._audit = audit_log
        self._allowlist = TOOL_ALLOWLIST if allowlist is None else allowlist
        self._clock = clock
        self._spent_approvals: Set[str] = set()

    def check(
        self,
        agent: str,
        tool: str,
        tier: Tier,
        case_id: str,
        payload: Optional[Dict[str, Any]] = None,
        approval: Optional[ApprovalRecord] = None,
        human_approver: Optional[str] = None,
    ) -> GateDecision:
        """Decide one tool call and log it. ``human_approver`` lets a named human clear a fuzzy L2 write."""
        payload = payload or {}
        decision, reason, digest = self._decide(agent, tool, tier, payload, approval, human_approver)
        line = self._audit.append(
            case_id=case_id,
            agent=agent,
            tool=tool,
            tier=tier,
            decision=decision,
            reason=reason,
            input_payload=payload,
            output_payload={"decision": decision.value, "reason": reason},
        )
        return GateDecision(
            decision=decision,
            reason=reason,
            tier=tier,
            agent=agent,
            tool=tool,
            case_id=case_id,
            action_hash=digest,
            audit_seq=line.seq,
        )

    def record_approval(
        self, case_id: str, approval: Optional[ApprovalRecord], error: Optional[str], tool: str = "approval"
    ) -> int:
        """Log the outcome of an OTP attempt (APPROVED or REJECTED). Returns the audit seq."""
        approved = approval is not None and error is None
        line = self._audit.append(
            case_id=case_id,
            agent="coordinator",
            tool=tool,
            tier=Tier.L3_EXTERNAL,
            decision=Decision.APPROVED if approved else Decision.REJECTED,
            reason=(
                f"OTP approved by {approval.approver}" if approved and approval else f"OTP rejected: {error}"
            ),
            input_payload={"action_hash": approval.action_hash if approval else None},
            output_payload={"ok": approved},
        )
        return line.seq

    # ------------------------------------------------------------------ internals
    def _decide(
        self,
        agent: str,
        tool: str,
        tier: Tier,
        payload: Dict[str, Any],
        approval: Optional[ApprovalRecord],
        human_approver: Optional[str],
    ):
        if tier is Tier.L4_MONEY_MOVEMENT or tool in L4_TOOLS:
            return (
                Decision.BLOCKED,
                "L4 is never automated. Do this in your banking portal.",
                None,
            )
        registered = TOOL_TIERS.get(tool)
        if registered is None:
            return Decision.BLOCKED, f"Unknown tool '{tool}'", None
        if tool not in self._allowlist.get(agent, frozenset()):
            return Decision.BLOCKED, f"Tool '{tool}' is not on the allowlist for '{agent}'", None
        if tier.rank < registered.rank:
            return (
                Decision.BLOCKED,
                f"Tool '{tool}' is {registered.value}; call declared {tier.value}",
                None,
            )

        if registered in (Tier.L0_READ, Tier.L1_ANALYZE):
            return Decision.ALLOWED, "granted source" if registered is Tier.L0_READ else "analysis", None
        if registered is Tier.L2_INTERNAL_WRITE:
            return self._decide_l2(payload, human_approver, tool)
        return self._decide_l3(tool, payload, approval)

    @staticmethod
    def _decide_l2(payload: Dict[str, Any], human_approver: Optional[str], tool: str = ""):
        if tool == "record_credit_decision":
            if human_approver:
                return Decision.ALLOWED, f"credit decision recorded by human reviewer {human_approver}", None
            return Decision.BLOCKED, "a credit decision must be made by a named human reviewer", None
        confidence = payload.get("confidence")
        if confidence == 1.0:
            return Decision.ALLOWED, "confidence 1.0", None
        if human_approver:
            return Decision.ALLOWED, f"fuzzy match approved by {human_approver}", None
        return Decision.AWAITING_APPROVAL, f"confidence {confidence}: accountant approval needed", None

    def _decide_l3(self, tool: str, payload: Dict[str, Any], approval: Optional[ApprovalRecord]):
        digest = action_hash(tool, payload)
        if approval is None:
            return Decision.AWAITING_APPROVAL, "L3 action needs an OTP approval from the Director", digest
        if approval.action_hash != digest or approval.action_type != tool:
            return Decision.REJECTED, "approval is bound to a different action or payload", digest
        if approval.approval_id in self._spent_approvals:
            return Decision.REJECTED, "approval was already used", digest
        if self._clock() > approval.valid_until:
            return Decision.REJECTED, "approval expired", digest
        self._spent_approvals.add(approval.approval_id)
        return Decision.ALLOWED, f"OTP approval by {approval.approver} bound to action_hash", digest
