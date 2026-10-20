"""Signed source attestations: the only way a data source counts as *independently verified*.

A manifest row can say ``"verified_by": "auditor"`` but that is a claim, not proof. A source is
treated as verified only when an attestation signed with the server-held key
``CASHBRIDGE_ATTESTATION_KEY`` binds the exact ``source_id``, ``type``, ``as_of`` and (when the
manifest provides one) ``content_sha256`` of that source, and the attestation has not expired.

Who signs? Whoever holds the key: in a deployment that is an independent verification step
(an auditor, the bank's document-check desk, an e-invoice registry adapter), run with
``python scripts/attest_source.py``. The browser never sees the key, so it can neither mint nor
alter attestations. Changing ``as_of`` or the document hash after signing invalidates it.

This is HMAC-SHA256 integrity, not a PKI digital signature, and it proves only that the key holder
attested the source. It does not prove the underlying document is authentic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

MIN_KEY_LENGTH = 32
MAX_ATTESTATIONS = 500
MAX_FILE_BYTES = 500_000
SIGNED_FIELDS = ("source_id", "type", "as_of", "content_sha256", "verifier", "verified_at", "expires_on")


class AttestationError(ValueError):
    """The attestation store is missing, unreadable or malformed (callers fail closed)."""


def _canonical(record: Mapping[str, Any]) -> bytes:
    body = {k: ("" if record.get(k) is None else str(record.get(k))) for k in SIGNED_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _check_key(key: str) -> bytes:
    if not isinstance(key, str) or len(key.strip()) < MIN_KEY_LENGTH:
        raise AttestationError(f"attestation key must be at least {MIN_KEY_LENGTH} characters")
    return key.strip().encode()


def sign(record: Mapping[str, Any], key: str) -> Dict[str, Any]:
    """Return ``record`` (signed fields only) plus its ``sig``. Used by the verifier CLI and tests."""
    for field in ("source_id", "type", "as_of", "verifier", "verified_at"):
        if not str(record.get(field) or "").strip():
            raise AttestationError(f"attestation needs {field}")
    date.fromisoformat(str(record["as_of"]))
    body = {k: record.get(k) for k in SIGNED_FIELDS if record.get(k) not in (None, "")}
    body["sig"] = hmac.new(_check_key(key), _canonical(body), hashlib.sha256).hexdigest()
    return body


def verify(record: Mapping[str, Any], key: str) -> bool:
    sig = str(record.get("sig") or "")
    expected = hmac.new(_check_key(key), _canonical(record), hashlib.sha256).hexdigest()
    return len(sig) == 64 and hmac.compare_digest(sig, expected)


def load(path: str | Path) -> List[Dict[str, Any]]:
    """Read an attestation file (JSON list). Raises AttestationError on any problem."""
    try:
        resolved = Path(path).resolve(strict=True)
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise AttestationError("attestation file too large")
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except AttestationError:
        raise
    except (OSError, ValueError) as error:
        raise AttestationError("attestation file unreadable") from error
    if not isinstance(data, list) or len(data) > MAX_ATTESTATIONS or not all(isinstance(x, dict) for x in data):
        raise AttestationError("attestation file must be a JSON list of objects")
    return data


def verified_source_ids(sources: Iterable[Mapping[str, Any]], attestations: Iterable[Mapping[str, Any]], key: str,
                        today: Optional[date] = None) -> Tuple[frozenset, List[Dict[str, str]]]:
    """Source ids whose manifest row is bound by a valid, unexpired signed attestation.

    Returns ``(verified_ids, rejected)`` where ``rejected`` explains each attestation that did not count.
    """
    today = today or datetime.now(timezone.utc).date()
    by_id: Dict[str, Mapping[str, Any]] = {}
    for source in sources:
        if isinstance(source, Mapping) and source.get("source_id"):
            by_id[str(source["source_id"])] = source
    verified = set()
    rejected: List[Dict[str, str]] = []
    for att in attestations:
        sid = str(att.get("source_id") or "")
        if not verify(att, key):
            rejected.append({"source_id": sid, "reason": "bad_signature"})
            continue
        source = by_id.get(sid)
        if source is None:
            continue  # attestation for a source this manifest does not use
        mismatch = [f for f in ("type", "as_of") if str(source.get(f) or "") != str(att.get(f) or "")]
        if att.get("content_sha256") and str(source.get("content_sha256") or "") != str(att["content_sha256"]):
            mismatch.append("content_sha256")
        if mismatch:
            rejected.append({"source_id": sid, "reason": "changed_after_attestation:" + ",".join(mismatch)})
            continue
        expires = att.get("expires_on")
        if expires:
            try:
                if date.fromisoformat(str(expires)) < today:
                    rejected.append({"source_id": sid, "reason": "attestation_expired"})
                    continue
            except ValueError:
                rejected.append({"source_id": sid, "reason": "bad_expiry"})
                continue
        verified.add(sid)
    return frozenset(verified), rejected
