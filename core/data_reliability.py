"""Deterministic, non-probabilistic data-quality gate for financing analysis.

Only bounded metadata / structured amounts, never raw sensitive documents. A high score
is NOT a credit score or assurance that submitted documents are authentic.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_ROWS = 200
REQUIRED = ('bank_statement', 'receivables_aging', 'ledger')

def money(value: Any) -> Decimal:
    if isinstance(value, bool): raise ValueError('Boolean is not a monetary amount')
    try: v = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError): raise ValueError('Invalid monetary amount') from None
    if not v.is_finite() or abs(v) > Decimal('1000000000') or v.as_tuple().exponent < -2:
        raise ValueError('Amount must be finite, within 1 billion and have at most two decimals')
    return v

def assess(payload: dict[str, Any], today: date | None = None, verified_ids: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(payload, dict): raise ValueError('Object expected')
    today = today or date.today()
    docs = payload.get('sources', [])
    if not isinstance(docs, list) or len(docs) > 50: raise ValueError('Invalid source manifest')
    seen: set[str] = set()
    issues: list[dict[str, str]] = []
    def flag(code: str, severity: str, detail: str):
        issues.append({'code': code, 'severity': severity, 'detail': detail})
    valid_types: set[str] = set()
    provenance = 0
    freshness = 0
    for source in docs:
        if not isinstance(source, dict): raise ValueError('Source metadata must be an object')
        typ = source.get('type')
        if not isinstance(typ, str) or len(typ) > 64 or typ not in (*REQUIRED, 'invoice', 'contract', 'purchase_order'):
            raise ValueError('Unknown source type')
        key = str(source.get('source_id',''))
        if not key or len(key)>100 or key in seen: raise ValueError('Source identifier missing/duplicated')
        seen.add(key)
        valid_types.add(typ)
        # A self-declared 'verified' flag is never accepted as proof of external verification.
        if key in verified_ids:  # must come from server-side verification, never browser claims
            provenance += 1
        else:
            flag('UNVERIFIED_SOURCE', 'review', f'{typ} needs independent verification')
        try:
            asof = date.fromisoformat(str(source.get('as_of', '')))
        except ValueError:
            flag('INVALID_DATE', 'block', f'{typ} has no valid as-of date'); continue
        age = (today - asof).days
        if age < 0:
            flag('FUTURE_DATE', 'block', f'{typ} is dated in the future')
        elif age > 90:
            flag('STALE_SOURCE', 'review', f'{typ} was updated {age} days ago')
        else:
            freshness += 1
    missing = [name for name in REQUIRED if name not in valid_types]
    for name in missing: flag('MISSING_SOURCE', 'block', f'Missing {name}')
    ledger = payload.get('ledger_entries', [])
    bank = payload.get('bank_entries', [])
    for part in (ledger, bank):
        if not isinstance(part, list) or len(part) > MAX_ROWS: raise ValueError('Invalid record list')
    def indexed(rows):
        result: dict[str, Decimal] = {}
        for item in rows:
            if not isinstance(item, dict): raise ValueError('Invalid transaction')
            ref = item.get('reference')
            if not isinstance(ref, str) or not ref or len(ref) > 100 or ref in result:
                raise ValueError('Missing or duplicate transaction reference')
            result[ref] = money(item.get('amount'))
        return result
    l, b = indexed(ledger), indexed(bank)
    if not ledger or not bank: flag('RECONCILIATION_NOT_AVAILABLE', 'review', 'Ledger and bank records are needed to reconcile')
    matched = sum(1 for ref, value in l.items() if ref in b and b[ref] == value)
    mismatched = len(set(l) | set(b)) - matched
    if mismatched:
        flag('RECONCILIATION_MISMATCH', 'block', f'{mismatched} transaction references are unmatched or inconsistent')
    # A descriptive index for triage only; not an independently calibrated probability.
    completeness = len(set(REQUIRED) & valid_types) / len(REQUIRED)
    verification = provenance / len(docs) if docs else 0
    current = freshness / len(docs) if docs else 0
    reconcile = matched / len(set(l) | set(b)) if (l or b) else 0
    index = round(100 * (.35*completeness + .20*verification + .20*current + .25*reconcile))
    has_block = any(x['severity']=='block' for x in issues)
    return {'quality_index': index, 'quality_index_is_probability': False,
            'gate': 'BLOCKED_FOR_FINANCING' if has_block else ('REVIEW_REQUIRED' if issues else 'READY_FOR_DRAFT'),
            'allowed_activities': ['inspect', 'correct', 'request_evidence'] + ([] if has_block else ['prepare_draft']),
            'review_required': bool(issues), 'counts': {'sources':len(docs),'matched_transactions':matched,'unmatched_transactions':mismatched},
            'dimensions': {'completeness':round(completeness*100), 'provenance':round(verification*100),
                           'freshness':round(current*100), 'reconciliation':round(reconcile*100)},
            'issues': issues, 'external_authenticity_verified': False,
            'notice': 'A metadata quality check; not a credit decision, document authentication or a model confidence probability.'}
