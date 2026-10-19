"""Strictly scoped demo bank-review authentication.

This is a server-side role gate for a *synthetic* single-case reviewer view, not
multi-tenant identity management or production bank authentication. Client-side
role toggles never grant access. No default or hardcoded access token exists.
"""
from __future__ import annotations

import hmac
import os
from fastapi import Header, HTTPException


def require_bank_reviewer(authorization: str | None = Header(default=None)) -> None:
    """Require configured bank-review Bearer token; fail closed when unconfigured."""
    expected = os.getenv('CASHBRIDGE_BANK_REVIEW_TOKEN', '').strip()
    if len(expected) < 24:
        raise HTTPException(status_code=503, detail='Bank access is disabled: configure a strong server-side bank reviewer token')
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Bank reviewer Bearer token required', headers={'WWW-Authenticate':'Bearer'})
    candidate = authorization[7:]
    if not hmac.compare_digest(candidate.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail='Insufficient permissions for bank reviewer')
