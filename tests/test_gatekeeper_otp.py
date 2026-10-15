"""Audit log, permission gatekeeper and action-bound OTP (Steps 2.1 and 2.2)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from config.settings import Tier
from config.tool_allowlist import TOOL_ALLOWLIST
from schemas.agent_schemas import Decision
from security.audit_log import AuditLog, verify_chain
from security.otp_verifier import OtpVerifier, action_hash
from security.permission_gatekeeper import PermissionGatekeeper

T0 = datetime(2026, 10, 19, 7, 0, 0, tzinfo=timezone.utc)
SECRET = "JBSWY3DPEHPK3PXP"


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, seconds: int):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def audit(tmp_path, clock):
    return AuditLog(tmp_path / "audit.jsonl", clock=clock)


@pytest.fixture
def gate(audit, clock):
    return PermissionGatekeeper(audit, clock=clock)


@pytest.fixture
def otp(clock):
    return OtpVerifier(secret=SECRET, clock=clock)


PACK_A = {"pack_id": "PACK-A", "invoice": "INV-1030", "amount": 48000}
PACK_B = {"pack_id": "PACK-B", "invoice": "INV-1030", "amount": 48000}


# ------------------------------------------------------------------ audit log
def test_audit_lines_are_chained_and_verify(audit):
    for n in range(3):
        audit.append(case_id="c1", agent="coordinator", tool="read_inbox", tier=Tier.L0_READ,
                     decision=Decision.ALLOWED, reason=f"r{n}", input_payload={"n": n})
    assert audit.verify_chain() == (True, None, 3)
    lines = [json.loads(l) for l in audit.path.read_text().splitlines()]
    assert [l["seq"] for l in lines] == [1, 2, 3]
    assert lines[1]["prev_line_sha256"] == lines[0]["line_sha256"]
    assert set(lines[0]) == {
        "seq", "timestamp_utc", "case_id", "agent", "tool", "tier", "decision", "reason",
        "input_sha256", "output_sha256", "prev_line_sha256", "line_sha256",
    }


def test_tampered_line_is_detected_at_its_seq(audit):
    for n in range(4):
        audit.append(case_id="c1", agent="coordinator", tool="read_inbox", tier=Tier.L0_READ,
                     decision=Decision.ALLOWED, reason=f"r{n}")
    lines = audit.path.read_text().splitlines()
    edited = json.loads(lines[1])
    edited["decision"] = "BLOCKED"
    lines[1] = json.dumps(edited, sort_keys=True)
    audit.path.write_text("\n".join(lines) + "\n")
    assert verify_chain(audit.path) == (False, 2, 2)


def test_deleted_middle_line_is_detected(audit):
    for n in range(4):
        audit.append(case_id="c1", agent="coordinator", tool="read_inbox", tier=Tier.L0_READ,
                     decision=Decision.ALLOWED, reason=f"r{n}")
    lines = audit.path.read_text().splitlines()
    del lines[1]
    audit.path.write_text("\n".join(lines) + "\n")
    assert verify_chain(audit.path)[:2] == (False, 2)


def test_tail_has_tier_monitor_shape(audit):
    audit.append(case_id="c1", agent="coordinator", tool="read_inbox", tier=Tier.L0_READ,
                 decision=Decision.ALLOWED, reason="granted source")
    assert audit.tail(10) == [{
        "seq": 1, "time": "07:00:00", "agent": "coordinator", "tool": "read_inbox",
        "tier": "L0_READ", "decision": "ALLOWED", "reason": "granted source",
    }]


# ----------------------------------------------------------------- gatekeeper
def test_l0_and_l1_are_allowed(gate):
    assert gate.check("coordinator", "read_bank_statements", Tier.L0_READ, "c1").decision is Decision.ALLOWED
    assert gate.check("coordinator", "run_forecast", Tier.L1_ANALYZE, "c1").decision is Decision.ALLOWED


def test_l2_exact_allowed_fuzzy_waits_for_lan(gate):
    assert gate.check("coordinator", "ledger_write", Tier.L2_INTERNAL_WRITE, "c1", {"confidence": 1.0}).decision is Decision.ALLOWED
    fuzzy = gate.check("coordinator", "ledger_write", Tier.L2_INTERNAL_WRITE, "c1", {"confidence": 0.9})
    assert fuzzy.decision is Decision.AWAITING_APPROVAL
    approved = gate.check("coordinator", "ledger_write", Tier.L2_INTERNAL_WRITE, "c1", {"confidence": 0.9}, human_approver="Lan")
    assert approved.decision is Decision.ALLOWED and "Lan" in approved.reason


def test_l4_is_blocked_even_with_approval(gate, otp):
    challenge = otp.issue_challenge("update_payee", {"iban": "X"})
    approval = otp.verify(challenge, otp.current_code()).approval
    for agent in ("coordinator", "cfo_assistant"):
        decision = gate.check(agent, "update_payee", Tier.L4_MONEY_MOVEMENT, "c1", {"iban": "X"}, approval=approval)
        assert decision.decision is Decision.BLOCKED
        assert "banking portal" in decision.reason


def test_disallowed_and_unknown_tools_are_blocked(gate):
    assert gate.check("cfo_assistant", "submit_pack", Tier.L3_EXTERNAL, "c1").decision is Decision.BLOCKED
    assert gate.check("collections_agent", "send_email", Tier.L3_EXTERNAL, "c1").decision is Decision.BLOCKED
    assert gate.check("coordinator", "format_disk", Tier.L0_READ, "c1").decision is Decision.BLOCKED
    assert gate.check("ghost_agent", "read_inbox", Tier.L0_READ, "c1").decision is Decision.BLOCKED


def test_declaring_a_lower_tier_does_not_help(gate):
    decision = gate.check("coordinator", "submit_pack", Tier.L0_READ, "c1", PACK_A)
    assert decision.decision is Decision.BLOCKED


def test_exactly_one_audit_line_per_call(gate, audit):
    gate.check("coordinator", "read_inbox", Tier.L0_READ, "c1")
    gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", PACK_A)
    gate.check("coordinator", "update_payee", Tier.L4_MONEY_MOVEMENT, "c1")
    lines = [json.loads(l) for l in audit.path.read_text().splitlines()]
    assert [l["decision"] for l in lines] == ["ALLOWED", "AWAITING_APPROVAL", "BLOCKED"]
    assert audit.verify_chain()[0]


def test_no_agent_but_coordinator_holds_submit_or_send():
    holders = {a for a, tools in TOOL_ALLOWLIST.items() if {"submit_pack", "send_email"} & tools}
    assert holders == {"coordinator"}


# ------------------------------------------------------------------------ OTP
def test_l3_without_otp_waits(gate):
    decision = gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", PACK_A)
    assert decision.decision is Decision.AWAITING_APPROVAL
    assert decision.action_hash == action_hash("submit_pack", PACK_A)


def test_valid_otp_allows_the_bound_action_once(gate, otp):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    result = otp.verify(challenge, otp.current_code(), action_type="submit_pack", payload=PACK_A)
    assert result.ok and result.error is None
    first = gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", PACK_A, approval=result.approval)
    assert first.decision is Decision.ALLOWED
    again = gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", PACK_A, approval=result.approval)
    assert again.decision is Decision.REJECTED and "already used" in again.reason


def test_approval_for_pack_a_cannot_send_pack_b(gate, otp):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    # Verification step: the code was issued for A, but B is about to run.
    wrong = otp.verify(challenge, otp.current_code(), action_type="submit_pack", payload=PACK_B)
    assert not wrong.ok and wrong.error == "payload_mismatch"
    # Even if an approval for A exists, the gatekeeper refuses it for B.
    approval = otp.verify(challenge, otp.current_code()).approval
    decision = gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", PACK_B, approval=approval)
    assert decision.decision is Decision.REJECTED


def test_editing_the_payload_after_approval_invalidates_it(gate, otp):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    approval = otp.verify(challenge, otp.current_code()).approval
    edited = {**PACK_A, "amount": 52000}
    assert gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", edited, approval=approval).decision is Decision.REJECTED


def test_replayed_code_is_refused(otp):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    code = otp.current_code()
    assert otp.verify(challenge, code).ok
    again = otp.verify(challenge, code)
    assert not again.ok and again.error == "replayed"


def test_code_after_121_seconds_is_expired(otp, clock):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    code = otp.current_code()
    clock.advance(121)
    result = otp.verify(challenge, code)
    assert not result.ok and result.error == "expired"


def test_code_at_119_seconds_is_still_accepted_if_totp_window_matches(clock):
    verifier = OtpVerifier(secret=SECRET, clock=clock)
    challenge = verifier.issue_challenge("submit_pack", PACK_A)
    clock.advance(119)
    assert verifier.verify(challenge, verifier.current_code()).ok


def test_wrong_code_is_invalid(otp):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    wrong = "000000" if otp.current_code() != "000000" else "111111"
    result = otp.verify(challenge, wrong)
    assert not result.ok and result.error == "invalid_code"


def test_approval_expires_for_the_gatekeeper(gate, otp, clock):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    approval = otp.verify(challenge, otp.current_code()).approval
    clock.advance(121)
    assert gate.check("coordinator", "submit_pack", Tier.L3_EXTERNAL, "c1", PACK_A, approval=approval).decision is Decision.REJECTED


def test_record_approval_writes_approved_and_rejected_lines(gate, otp, audit):
    challenge = otp.issue_challenge("submit_pack", PACK_A)
    ok = otp.verify(challenge, otp.current_code())
    gate.record_approval("c1", ok.approval, None)
    bad = otp.verify(challenge, "000000")
    gate.record_approval("c1", None, bad.error)
    decisions = [json.loads(l)["decision"] for l in audit.path.read_text().splitlines()]
    assert decisions == ["APPROVED", "REJECTED"]
