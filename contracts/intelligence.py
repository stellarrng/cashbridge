"""Financial contract drafting and evidence-backed risk signals, not a legal opinion.

Untrusted documents are NEVER executable instructions and are not forwarded to any LLM.
All amounts and payment percentages are extracted with explicit patterns and their
confidence is labelled; document authenticity cannot be confirmed by OCR.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from security.injection_guard import scan

MAX_CHARS = 50000
_PERCENT = re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%')
_AMOUNT = re.compile(r'(?:USD\s*|US\$\s*|\$\s*)(\d[\d,]*(?:\.\d{1,2})?)', re.IGNORECASE)
# Vietnamese convention: 60.000,00 USD (dot thousands, comma decimals, currency after the number).
_AMOUNT_VI = re.compile(r'(?<![\d.,])(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{2})\s*USD\b')
_INVOICE = re.compile(r'\b(?:INV|INVOICE)[- #:]*(\d{3,12})\b', re.IGNORECASE)
_TAX = re.compile(r'\b(?:tax\s*id|tax\s*number|vat\s*id)\s*[:#]?\s*([A-Z0-9\-]{7,20})', re.IGNORECASE)
_BANK_CHANGE = re.compile(r'(?:change|replace|switch|update|different|new)\s+(?:the\s+)?(?:bank\s+)?(?:account|beneficiary|payment\s+details)', re.IGNORECASE)
_BANK = re.compile(r'\b(?:bank\s+account|beneficiary\s+account|account\s+number)\b', re.IGNORECASE)
_AMBIGUOUS = re.compile(r'\b(?:as\s+soon\s+as\s+possible|at\s+our\s+discretion|when\s+convenient)\b', re.IGNORECASE)
_PAYMENT = re.compile(r'\b(?:payment|paid|deposit|advance|milestone|on\s+delivery|upon\s+acceptance|thanh\s+toán|tạm\s+ứng|đặt\s+cọc)\b', re.IGNORECASE)
# A schedule line such as "Milestone 2: ... - 70% - ..." or "Đợt 2: ...": when a document has them, they ARE the
# payment schedule and other percentages (interest, retention, VAT, liability caps) are not instalments.
_SCHEDULE_LINE = re.compile(r'^\s*(?:milestone|instalment|installment|đợt)\s*\d+\s*[:.)]', re.IGNORECASE)
# Percentages that are rates or caps, not instalments, on a payment line without a schedule.
_NOT_INSTALMENT = re.compile(r'\b(?:interest|per\s+annum|p\.a\.|retention|retain|vat|value-added|tax|liability|penalty|liquidated|'
                             r'security|guarantee|insurance|lãi|năm|giữ\s+lại|thuế|trách\s+nhiệm|phạt|bảo\s+đảm|bảo\s+lãnh|bảo\s+hiểm)\b', re.IGNORECASE)
_TERMINATION = re.compile(r'\b(?:termination|terminate|cancel|cancellation|chấm\s+dứt|hủy\s+bỏ|huỷ\s+bỏ)\b', re.IGNORECASE)


def _text(value: Any, name: str, limit: int = MAX_CHARS) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be non-empty text')
    if len(value) > limit:
        raise ValueError(f'{name} exceeds {limit} characters')
    return value.strip()


def _money(value: Any, name: str) -> float:
    import math
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a positive amount')
    try: v = float(value)
    except (ValueError, TypeError) as exc: raise ValueError(f'{name} must be a positive amount') from exc
    if not math.isfinite(v) or not 0 < v <= 1e10:
        raise ValueError(f'{name} must be a positive finite amount')
    return round(v,2)


def analyze(text: str, invoice_amount_usd: float | None = None) -> Dict[str, Any]:
    content = _text(text, 'contract text')
    money = [float(m.replace(',', '')) for m in _AMOUNT.findall(content)]
    money += [float(m.replace('.', '').replace(',', '.')) for m in _AMOUNT_VI.findall(content)]
    percentages = [float(x) for x in _PERCENT.findall(content)]
    # Extract payment phases only on lines mentioning a payment event; don't count taxes, penalties etc.
    milestones: List[Dict[str, Any]] = []
    lines = content.splitlines()
    scheduled = [i for i, line in enumerate(lines) if _SCHEDULE_LINE.match(line) and _PERCENT.search(line)]
    for idx, line in enumerate(lines):
        if scheduled:
            if idx not in scheduled:
                continue
            found = list(_PERCENT.finditer(line))[:1]  # one instalment per schedule line
        else:
            if not _PAYMENT.search(line) or _NOT_INSTALMENT.search(line):
                continue
            found = list(_PERCENT.finditer(line))
        for m in found:
            milestones.append({'line': idx + 1, 'percentage': float(m.group(1)), 'evidence': line[:240]})
    flags = []
    def flag(code: str, severity: str, description: str, evidence: str):
        flags.append({'code': code, 'severity': severity, 'description': description, 'evidence': evidence})
    # Override / role-change / tool-name patterns are scanned over the whole document (so an instruction split across
    # lines is still caught). The "send/transfer ... payment" pattern is scanned per line: across a line break it
    # matched ordinary contract wording ("...by bank transfer." / "ARTICLE 4. PAYMENT") in every real contract.
    hits = [h for h in scan(content) if h != 'action_command']
    hits += ['action_command'] if any('action_command' in scan(line) for line in lines) else []
    if hits:
        flag('UNTRUSTED_INSTRUCTIONS', 'high', 'Document contains instruction-like text; never execute it.',
             'Prompt-injection pattern in document: ' + ', '.join(hits))
    if _BANK_CHANGE.search(content):
        flag('BENEFICIARY_CHANGE', 'high', 'Bank-account change wording needs independent callback verification.', 'Bank-detail change wording')
    if _AMBIGUOUS.search(content):
        flag('VAGUE_TERM', 'medium', 'Ambiguous timing or unilateral discretion should be reviewed.', 'Vague contractual language')
    total_pct = round(sum(x['percentage'] for x in milestones), 2)
    if milestones and abs(total_pct - 100) > 0.01:
        flag('PAYMENT_PERCENTAGES', 'medium', 'Payment milestone percentages do not sum to 100%.', f'{total_pct}% across marked milestones')
    if not _PAYMENT.search(content):
        flag('MISSING_PAYMENT_CLAUSE', 'medium', 'No recognizable payment wording found.', 'No payment terms found')
    if not _TERMINATION.search(content):
        flag('TERMINATION_NOT_DETECTED', 'low', 'No termination provision detected by simple rules.', 'Section not detected')
    if invoice_amount_usd is not None:
        invoice = _money(invoice_amount_usd, 'invoice_amount_usd')
        if money and not any(abs(m-invoice) < .01 for m in money):
            flag('AMOUNT_MISMATCH', 'high', 'Invoice amount differs from amounts explicitly stated in the contract.', f'Invoice ${invoice:,.2f} vs detected amounts {money[:5]}')
    return {
        'synthetic_demo': True, 'status': 'REQUIRES_HUMAN_REVIEW', 'source': 'submitted document text',
        'document_length_chars': len(content), 'extracted': {
            'amounts_usd': money[:30], 'percentages': percentages[:30],
            'payment_milestones': milestones[:25], 'payment_percentage_sum': total_pct if milestones else None,
            'invoice_ids': sorted(set('INV-' + value for value in _INVOICE.findall(content))),
            'tax_ids': sorted(set(_TAX.findall(content))), 'bank_details_mentioned': bool(_BANK.search(content)),
        },
        'flags': flags, 'risk_signal_count': len(flags),
        'limitations': ['Signals are rule-based flags, NOT proof of fraud, document authenticity, or legal enforceability.',
                        'Simple OCR/text pattern recognition can miss clauses; all extracted terms need human verification.',
                        'Uploaded text is treated as untrusted input; no transactions or legal documents are signed.']
    }


def draft(data: Dict[str, Any]) -> Dict[str, Any]:
    """Unsigned contract draft from the clause library in contracts/drafting.py (EN, VI or bilingual)."""
    from contracts.drafting import draft as _draft
    return _draft(data)


def reconcile(data: Dict[str, Any]) -> Dict[str, Any]:
    contract = analyze(_text(data.get('contract_text'), 'contract_text'))
    invoice = _text(data.get('invoice_text'), 'invoice_text')
    invoice_amounts = [float(v.replace(',','')) for v in _AMOUNT.findall(invoice)]
    contract_amounts = contract['extracted']['amounts_usd']
    invoice_ids = sorted(set('INV-' + x for x in _INVOICE.findall(invoice)))
    discrepancy = bool(invoice_amounts and contract_amounts and
                       not any(abs(x-y) <= 0.01 for x in invoice_amounts for y in contract_amounts))
    return {'synthetic_demo': True, 'invoice_ids': invoice_ids,
            'contract_amounts_usd': contract_amounts, 'invoice_amounts_usd': invoice_amounts,
            'amount_mismatch': discrepancy,
            'flags': contract['flags'] + ([{'code':'AMOUNT_MISMATCH','severity':'high',
                        'description':'No invoice amount matches a contract amount', 'evidence':'Parsed amounts'}] if discrepancy else []),
            'status': 'MANUAL_VERIFICATION_REQUIRED',
            'limitations': 'Text amounts alone cannot prove invoice legitimacy or detect financing across institutions.'}
