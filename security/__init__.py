"""CashBridge security module exports."""

from security.permission_gatekeeper import (
    request_permission,
    get_audit_log,
    append_chained_log,
    verify_log_integrity,
    get_chain_head,
    PermissionDeniedError,
    OTPRequiredError,
)
from security.pii_masker import mask_pii, mask_pii_detailed, mask_pii_dict
from security.bec_fraud_detector import scan_email
from security.otp_verifier import (
    generate_otp_session,
    verify_otp,
    consume_approval,
    is_session_verified,
)

__all__ = [
    "request_permission",
    "get_audit_log",
    "append_chained_log",
    "verify_log_integrity",
    "get_chain_head",
    "PermissionDeniedError",
    "OTPRequiredError",
    "mask_pii",
    "mask_pii_detailed",
    "mask_pii_dict",
    "scan_email",
    "generate_otp_session",
    "verify_otp",
    "consume_approval",
    "is_session_verified",
]
