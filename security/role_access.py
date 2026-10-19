"""Bank-reviewer access for the legacy read-only reviewer endpoint (``GET /api/bank/review``).

Two ways in, both checked on the server:
  1. a signed session of a ``bank_reviewer`` from the lender tenant (security/auth.py), or
  2. the older static demo Bearer token ``CASHBRIDGE_BANK_REVIEW_TOKEN`` (24+ characters).

With neither configured the endpoint fails closed (503). Client-side role toggles never grant access.
This is a synthetic single-case demo control, not production IAM.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException

from security import auth


def require_bank_reviewer(authorization: str | None = Header(default=None)) -> None:
    token = auth.bearer(authorization)
    if token and token.count(".") == 1:
        try:
            principal = auth.get_sessions().verify(token)
        except auth.AuthError:
            principal = None
        if principal is not None:
            if principal.can("bank:read") and principal.tenant_id == auth.LENDER_TENANT:
                return None
            raise HTTPException(status_code=403, detail='Insufficient permissions for bank reviewer')
    expected = os.getenv('CASHBRIDGE_BANK_REVIEW_TOKEN', '').strip()
    if len(expected) < 24:
        raise HTTPException(status_code=503, detail='Bank access is disabled: sign in as a bank reviewer or configure a server-side reviewer token')
    if not token:
        raise HTTPException(status_code=401, detail='Bank reviewer Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
    if not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail='Insufficient permissions for bank reviewer')
    return None
