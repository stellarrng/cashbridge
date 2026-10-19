"""Canonical SHA-256 evidence sealing and structured auditor highlights.

SHA-256 proves byte equality, NOT encryption or independent proof of authenticity.
The seal covers inputs, findings and reviewer decision; retain originals securely.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def canonical_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def seal_evidence(*, task_kind: str, source: dict[str, Any], findings: dict[str, Any],
                  reviewer_id: str, decision: str, timestamp: str | None = None) -> dict:
    """Create hash after an explicit review: source and findings must be preserved for verification.

    The timestamp is metadata, not a trusted time-stamp authority.
    """
    if decision not in ('accepted', 'accepted_with_exceptions', 'rejected'):
        raise ValueError('Invalid review decision')
    if not reviewer_id or len(reviewer_id) > 100:
        raise ValueError('Reviewer identity required')
    envelope = {
        'schema': 'cashbridge.audit-evidence.v1', 'task_kind': task_kind,
        'source': source, 'findings': findings,
        'reviewer_id': reviewer_id, 'decision': decision,
        'reviewed_at': timestamp or datetime.now(timezone.utc).isoformat(),
    }
    return {'algorithm': 'SHA-256', 'sha256': hashlib.sha256(canonical_bytes(envelope)).hexdigest(),
            'evidence': envelope, 'encrypted': False, 'signature_validated': False}


def verify_evidence(seal: dict) -> bool:
    try:
        return seal['algorithm'] == 'SHA-256' and hashlib.sha256(
            canonical_bytes(seal['evidence'])).hexdigest() == seal['sha256']
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def reconcile_highlights(ledger: list[dict], bank: list[dict]) -> list[dict]:
    """Structured annotations for table UI; never infer fraud from a mismatch alone."""
    bank_map = {r['reference']: r for r in bank}
    ledger_refs = {r['reference'] for r in ledger}
    result = []
    for i, row in enumerate(ledger):
        ref = row['reference']
        matching = bank_map.get(ref)
        if matching is None:
            result.append({'source':'ledger', 'row':i, 'field':'reference',
                           'reference':ref, 'severity':'high', 'reason':'missing_bank_entry'})
            continue
        amount_l = Decimal(str(row['amount']))
        amount_b = Decimal(str(matching['amount']))
        if amount_l != amount_b:
            result.append({'source':'ledger', 'row':i, 'field':'amount',
                           'reference':ref, 'severity':'high', 'reason':'amount_mismatch',
                           'ledger_amount':str(amount_l), 'bank_amount':str(amount_b),
                           'difference':str(amount_l - amount_b)})
    for i, row in enumerate(bank):
        if row['reference'] not in ledger_refs:
            result.append({'source':'bank', 'row':i, 'field':'reference',
                           'reference':row['reference'], 'severity':'medium',
                           'reason':'missing_ledger_entry'})
    return result


def invoice_highlights(invoices: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for i, r in enumerate(invoices):
        vendor = str(r.get('vendor','')).strip().casefold()
        number = str(r.get('invoice_number','')).strip().casefold()
        if not vendor or not number:
            result.append({'source':'invoice','row':i,'field':'invoice_number' if not number else 'vendor',
                           'severity':'high','reason':'missing_identifier'})
        if vendor and number and (vendor, number) in seen:
            result.append({'source':'invoice','row':i,'field':'invoice_number',
                           'severity':'high','reason':'potential_duplicate'})
        seen.add((vendor,number))
    return result


def provenance_highlights(changes: list[dict]) -> list[dict]:
    """Annotate changed or machine-produced values without trusting user-provided labels.

    `origin` is caller-supplied provenance and must be populated by a trusted ingestion
    adapter in production. These highlights NEVER mean the amount was audited.
    """
    if not isinstance(changes, list) or len(changes) > 300:
        raise ValueError('Invalid change list')
    result = []
    allowed = {'human_edit', 'ml_prediction', 'deterministic_calculation', 'ai_suggestion'}
    for idx, event in enumerate(changes):
        if not isinstance(event, dict):
            raise ValueError('Invalid provenance event')
        origin = event.get('origin')
        if origin not in allowed:
            raise ValueError('Invalid origin')
        doc = event.get('document_id')
        field = event.get('field')
        if not isinstance(doc, str) or not 1 <= len(doc) <= 100 or not isinstance(field, str) or not 1 <= len(field) <= 100:
            raise ValueError('Document and field required')
        new = Decimal(str(event.get('new_value')))
        if not new.is_finite():
            raise ValueError('Nonfinite monetary value')
        before = event.get('old_value')
        old = None if before is None else Decimal(str(before))
        if old is not None and not old.is_finite():
            raise ValueError('Nonfinite monetary value')
        if origin == 'human_edit' and old is None:
            raise ValueError('Manual changes require previous value')
        if origin != 'human_edit' and not event.get('method'):
            raise ValueError('Computed/suggested values require method')
        result.append({
            'source': 'provenance', 'row': idx, 'document_id': doc, 'field': field,
            'reason': 'edited_value' if origin == 'human_edit' else 'generated_value',
            'origin': origin, 'severity': 'info',
            'old_value': str(old) if old is not None else None,
            'new_value': str(new),
            'delta': str(new - old) if old is not None else None,
            'method': str(event.get('method', 'manual'))[:120],
            'actor_id': str(event.get('actor_id', 'unverified'))[:100],
            'status': 'requires_review',
            'color_hint': 'blue' if origin == 'human_edit' else 'purple',
            'source_reference': str(event.get('source_reference', ''))[:200],
        })
    return result
