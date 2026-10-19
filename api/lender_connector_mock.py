"""MOCK lender connector: formats a funding pack into a generic lender JSON payload.

This is the integration point where a white-label bank channel (for example WeBank) would
plug in. It does not call any network service and makes no claim that a real WeBank API
exists. Every payload and reference it produces is labelled MOCK and SYNTHETIC.
"""

from __future__ import annotations

from typing import Any, Dict

from config.settings import PARTNER_FACTOR_NAME
from security.audit_log import sha256_of

SCHEMA = "cashbridge.funding_pack.v1"


def format_payload(pack_payload: Dict[str, Any], lender: str = PARTNER_FACTOR_NAME) -> Dict[str, Any]:
    """Generic lender submission built from the approved pack payload."""
    return {
        "schema": SCHEMA,
        "lender": lender,
        "pack_id": pack_payload["pack_id"],
        "invoice_no": pack_payload["invoice_no"],
        "product": pack_payload["option_id"],
        "requested_amount_usd": pack_payload["amount_usd"],
        "bundle_sha256": pack_payload["bundle_sha256"],
        "mock": True,
        "synthetic": True,
    }


def submit(pack_payload: Dict[str, Any]) -> str:
    """Pretend to submit the pack and return a deterministic MOCK lender reference."""
    return "MOCK-" + sha256_of(format_payload(pack_payload))[:10].upper()
