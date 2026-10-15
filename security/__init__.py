"""
CashBridge Security module exports.
"""

from security.permission_gatekeeper import (
    request_permission,
    get_audit_log,
    PermissionDeniedError,
    OTPRequiredError,
)
from security.pii_masker import mask_pii, mask_pii_dict
from security.bec_fraud_detector import scan_email
from security.otp_verifier import generate_otp_session, verify_otp

__all__ = [
    "request_permission",
    "get_audit_log",
    "PermissionDeniedError",
    "OTPRequiredError",
    "mask_pii",
    "mask_pii_dict",
    "scan_email",
    "generate_otp_session",
    "verify_otp",
]
