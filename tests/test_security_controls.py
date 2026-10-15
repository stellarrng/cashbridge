"""
Security controls: the permission gate, OTP approval, audit chain, PII masking
and BEC screening.

Several tests here are regression tests against specific defects that were
present in the submitted build; each one names the defect it covers.
"""

import json

import pytest

from config.settings import PermissionLevel, DEMO_OTP, OTP_MAX_ATTEMPTS
from security import permission_gatekeeper as gate
from security import otp_verifier as otp
from security.permission_gatekeeper import (
    request_permission,
    verify_log_integrity,
    append_chained_log,
    PermissionDeniedError,
    OTPRequiredError,
)
from security.pii_masker import mask_pii, mask_pii_detailed, mask_pii_dict
from security.bec_fraud_detector import scan_email


# ─────────────────────────────────────────────────────────────────────────────
# Permission tiers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "level",
    [
        PermissionLevel.L0_READ,
        PermissionLevel.L1_ANALYZE,
        PermissionLevel.L2_INTERNAL_WRITE,
    ],
)
def test_low_tiers_are_auto_approved(level):
    assert request_permission(level, "ACTION", "RESOURCE")["approved"] is True


def test_l4_money_movement_is_always_blocked():
    with pytest.raises(PermissionDeniedError):
        request_permission(
            PermissionLevel.L4_MONEY_MOVEMENT, "TRANSFER_FUNDS", "ACC-1"
        )


def test_l4_block_is_recorded_in_the_audit_log():
    with pytest.raises(PermissionDeniedError):
        request_permission(PermissionLevel.L4_MONEY_MOVEMENT, "TRANSFER_FUNDS", "ACC-1")
    entries = gate.get_audit_log(10)
    assert any(e["status"] == "HARD_BLOCKED" for e in entries)


def test_l3_without_approval_is_refused():
    with pytest.raises(OTPRequiredError):
        request_permission(
            PermissionLevel.L3_EXTERNAL_OTP, "SUBMIT_FUNDING_PACK", "INV-2026-103"
        )


# ─────────────────────────────────────────────────────────────────────────────
# OTP
# ─────────────────────────────────────────────────────────────────────────────

def test_l3_proceeds_with_a_verified_session():
    session = otp.generate_otp_session("SUBMIT_FUNDING_PACK", "INV-2026-103")
    assert otp.verify_otp(session["session_id"], DEMO_OTP)["verified"] is True
    result = request_permission(
        PermissionLevel.L3_EXTERNAL_OTP,
        "SUBMIT_FUNDING_PACK",
        "INV-2026-103",
        otp_session_id=session["session_id"],
    )
    assert result["status"] == "OTP_CONFIRMED"


def test_empty_otp_is_rejected():
    """
    REGRESSION — AUTHENTICATION BYPASS. The old verifier read the expected code
    as `_active_sessions[sid].get("_secret_otp", "")`, a key never written, so
    outside demo mode the expected value was "" and `"".strip() == ""` approved
    any L3 external action with a blank code.
    """
    session = otp.generate_otp_session("SUBMIT_FUNDING_PACK", "INV-1")
    for blank in ("", "   ", None):
        assert otp.verify_otp(session["session_id"], blank)["verified"] is False
    assert otp.is_session_verified(session["session_id"]) is False


def test_wrong_otp_is_rejected_and_attempts_are_capped():
    session = otp.generate_otp_session("SUBMIT_FUNDING_PACK", "INV-1")
    sid = session["session_id"]
    for _ in range(OTP_MAX_ATTEMPTS):
        assert otp.verify_otp(sid, "000000")["verified"] is False
    # Session is burned: even the correct code no longer works.
    assert otp.verify_otp(sid, DEMO_OTP)["verified"] is False


def test_approval_cannot_be_self_asserted_by_the_caller():
    """
    REGRESSION. `request_permission(..., otp_verified=True)` accepted a boolean
    from the caller, so any code path could declare its own human approval.
    The parameter no longer exists; approval must be redeemable.
    """
    import inspect

    params = inspect.signature(request_permission).parameters
    assert "otp_verified" not in params
    assert "otp_session_id" in params

    with pytest.raises(OTPRequiredError):
        request_permission(
            PermissionLevel.L3_EXTERNAL_OTP, "SEND_DUNNING_LETTER", "INV-1",
            otp_session_id="not-a-real-session",
        )


def test_approval_is_bound_to_one_action_and_resource():
    """An OTP shown for one action must not authorise a different one."""
    session = otp.generate_otp_session("SUBMIT_FUNDING_PACK", "INV-2026-103")
    otp.verify_otp(session["session_id"], DEMO_OTP)

    with pytest.raises(OTPRequiredError):
        request_permission(
            PermissionLevel.L3_EXTERNAL_OTP,
            "SEND_DUNNING_LETTER",          # different action
            "INV-2026-103",
            otp_session_id=session["session_id"],
        )
    with pytest.raises(OTPRequiredError):
        request_permission(
            PermissionLevel.L3_EXTERNAL_OTP,
            "SUBMIT_FUNDING_PACK",
            "INV-2026-999",                 # different resource
            otp_session_id=session["session_id"],
        )


def test_approval_is_consumed_after_a_single_use():
    session = otp.generate_otp_session("SUBMIT_FUNDING_PACK", "INV-1")
    otp.verify_otp(session["session_id"], DEMO_OTP)
    request_permission(
        PermissionLevel.L3_EXTERNAL_OTP, "SUBMIT_FUNDING_PACK", "INV-1",
        otp_session_id=session["session_id"],
    )
    with pytest.raises(OTPRequiredError):
        request_permission(
            PermissionLevel.L3_EXTERNAL_OTP, "SUBMIT_FUNDING_PACK", "INV-1",
            otp_session_id=session["session_id"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Audit chain
# ─────────────────────────────────────────────────────────────────────────────

def test_fresh_log_is_valid_and_chained():
    for i in range(5):
        request_permission(PermissionLevel.L1_ANALYZE, f"ACTION_{i}", "RES")
    report = verify_log_integrity()
    assert report["is_valid"] is True
    assert report["entry_count"] == 5

    entries = gate.get_audit_log(10)
    assert entries[0]["prev_hash"] == "0" * 64
    for prev, cur in zip(entries, entries[1:]):
        assert cur["prev_hash"] == prev["entry_hash"]


def test_edited_entry_is_detected(isolated_evidence):
    """
    REGRESSION. The old log wrote an independent
    `state_hash = sha256(action|target|timestamp)` per line with no link to any
    other line, so editing a line's details, deleting a line or reordering
    lines left every hash valid. There was no chain.
    """
    for i in range(3):
        request_permission(PermissionLevel.L1_ANALYZE, f"ACTION_{i}", "RES")

    path = isolated_evidence["logs"]
    lines = path.read_text().strip().split("\n")
    tampered = json.loads(lines[1])
    tampered["details"] = {"amount": 999_999}
    lines[1] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n")

    report = verify_log_integrity()
    assert report["is_valid"] is False
    assert "does not match its recorded hash" in report["first_violation"]


def test_deleted_entry_is_detected(isolated_evidence):
    for i in range(4):
        request_permission(PermissionLevel.L1_ANALYZE, f"ACTION_{i}", "RES")

    path = isolated_evidence["logs"]
    lines = path.read_text().strip().split("\n")
    del lines[1]                              # remove the inconvenient entry
    path.write_text("\n".join(lines) + "\n")

    report = verify_log_integrity()
    assert report["is_valid"] is False


def test_chain_head_is_exportable_for_external_anchoring():
    request_permission(PermissionLevel.L1_ANALYZE, "ACTION", "RES")
    head = gate.get_chain_head()
    assert len(head) == 64
    assert head == gate.get_audit_log(1)[0]["entry_hash"]


# ─────────────────────────────────────────────────────────────────────────────
# PII masking
# ─────────────────────────────────────────────────────────────────────────────

def test_real_identifiers_are_masked():
    text = (
        "Please remit to IBAN DE89370400440532013000, SWIFT COBADEFFXXX. "
        "Contact: finance@nordichome.com, Tel: +84 28 3822 9999. "
        "Tax Code: 0101234567."
    )
    masked, report = mask_pii_detailed(text)
    assert "DE89370400440532013000" not in masked
    assert "COBADEFFXXX" not in masked
    assert "finance@nordichome.com" not in masked
    assert "0101234567" not in masked
    assert report["total_replacements"] >= 4


def test_ordinary_words_are_not_mistaken_for_swift_codes():
    """
    REGRESSION. `[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}` with re.IGNORECASE is "any eight
    alphanumerics starting with six letters", so SHIPMENT, CONTRACT, DELIVERY
    and MATERIAL were all replaced with [SWIFT_REDACTED] and the text handed to
    the extraction model was unreadable.
    """
    text = (
        "SHIPMENT under CONTRACT 7781: DELIVERY of MATERIAL per the SCHEDULE. "
        "PAYMENTS on DISPATCH. See ADDENDUM for QUANTITY."
    )
    masked, report = mask_pii_detailed(text)
    assert "[SWIFT_REDACTED]" not in masked
    assert report["total_replacements"] == 0
    for word in ("SHIPMENT", "CONTRACT", "DELIVERY", "MATERIAL", "PAYMENTS"):
        assert word in masked


def test_monetary_amounts_survive_masking():
    """
    REGRESSION. The tax-ID pattern made its label optional, making it "any 9-13
    digit number", and the phone pattern matched any 6-8 digit number. Invoice
    totals were being replaced with [TAX_ID_REDACTED] — which means the
    extraction step then read mutilated figures and reported them confidently.
    """
    text = (
        "Invoice total: 1250000000 VND (USD 65,000.00). Quantity 1200 units at "
        "unit price 54.17. Container MSCU1234567. Order 998877665."
    )
    masked, _ = mask_pii_detailed(text)
    assert "1250000000" in masked
    assert "65,000.00" in masked
    assert "1200" in masked
    assert "998877665" in masked


def test_labelled_tax_id_is_still_caught():
    masked, _ = mask_pii_detailed("Buyer MST: 0313579246 for the shipment.")
    assert "0313579246" not in masked


def test_mask_pii_dict_leaves_numeric_values_alone():
    payload = {
        "invoice_id": "INV-2026-103",
        "amount_usd": 65000.0,
        "buyer": {"email": "ap@nordichome.com", "tax": "Tax ID: 0101234567"},
        "lines": [{"qty": 1200, "note": "contact Tel: +84 909 123 456"}],
    }
    masked = mask_pii_dict(payload)
    assert masked["amount_usd"] == 65000.0
    assert masked["lines"][0]["qty"] == 1200
    assert "ap@nordichome.com" not in masked["buyer"]["email"]
    assert "0101234567" not in masked["buyer"]["tax"]


def test_masking_reports_its_residual_risk():
    _, report = mask_pii_detailed("Unit price 54.17 FOB Haiphong, vessel MV Horizon.")
    assert "not masked" in report["residual_risk"]


# ─────────────────────────────────────────────────────────────────────────────
# BEC screening
# ─────────────────────────────────────────────────────────────────────────────

def test_lookalike_domain_with_bank_change_is_blocked():
    result = scan_email(
        "EMAIL-001",
        "finance@nordichorne.com",          # rn instead of m
        "Updated banking details",
        "Please note our new IBAN DE89370400440532013000 effective immediately.",
    )
    assert result["threat_level"] == "CRITICAL_BLOCK"
    assert result["is_spoofed_domain"] is True


def test_bank_change_from_an_unknown_sender_is_held_for_review():
    """
    REGRESSION. A domain that resembled nothing in the trust list was scored
    SAFE ("No BEC indicators detected"), so the most common real attack — a
    bank-change request from an unrelated address — passed cleanly.
    """
    result = scan_email(
        "EMAIL-002",
        "accounts@totally-unrelated-domain.biz",
        "Change of bank",
        "Our banking details have changed. New IBAN GB33BUKB20201555555555.",
    )
    assert result["threat_level"] == "REVIEW_REQUIRED"
    assert result["flagged_bank_change"] is True
    assert "verify out of band" in result["required_next_action"].lower()


def test_routine_mail_from_a_trusted_buyer_is_not_blocked():
    """
    REGRESSION — FALSE POSITIVE. Any of twelve phrases alone triggered
    CRITICAL_BLOCK, including "please update your records" and "effective
    immediately". A control that blocks ordinary supplier mail gets switched
    off, and then it protects nobody.
    """
    result = scan_email(
        "EMAIL-003",
        "ap@nordichome.com",
        "PO 4471 confirmation - action required",
        "Please update your records: our new buying contact is Mei. "
        "We need the revised packing list urgently, effective immediately.",
    )
    assert result["threat_level"] in ("SAFE", "MEDIUM")
    assert result["threat_level"] != "CRITICAL_BLOCK"


def test_subdomain_of_a_trusted_domain_is_recognised():
    result = scan_email(
        "EMAIL-004", "ap@mail.nordichome.com", "Shipping schedule",
        "Attached is the updated schedule for week 42.",
    )
    assert result["sender_classification"] == "TRUSTED"
    assert result["is_spoofed_domain"] is False


def test_exporters_own_domain_is_spelled_correctly_in_the_trust_list():
    """
    REGRESSION. The trust list contained "pacifictiber.vn", a typo of
    "pacifictimber.vn". A typo in a trust list is a live vulnerability: mail
    from the typo domain was trusted and mail from the real domain was flagged
    as its lookalike.
    """
    from security.bec_fraud_detector import TRUSTED_BUYER_DOMAINS

    assert "pacifictimber.vn" in TRUSTED_BUYER_DOMAINS
    assert "pacifictiber.vn" not in TRUSTED_BUYER_DOMAINS


def test_verification_evasion_escalates_the_verdict():
    result = scan_email(
        "EMAIL-005",
        "cfo@unknown-supplier.com",
        "New wire instructions",
        "Use the new account number below. I am in a meeting all day, "
        "email only please, do not call.",
    )
    assert result["threat_level"] == "CRITICAL_BLOCK"


def test_a_safe_verdict_states_that_it_is_not_proof_of_authenticity():
    result = scan_email(
        "EMAIL-006", "ap@nordichome.com", "Thanks", "Received, thank you."
    )
    assert result["threat_level"] == "SAFE"
    assert "not" in result["reason"].lower()
    assert result["detection_limitations"]
    assert any("SPF" in lim for lim in result["detection_limitations"])
