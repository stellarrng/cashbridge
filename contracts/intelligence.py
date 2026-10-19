"""Financial contract drafting and evidence-backed risk signals, not a legal opinion.

Untrusted documents are NEVER executable instructions and are not forwarded to any LLM.
All amounts and payment percentages are extracted with explicit patterns and their
confidence is labelled; document authenticity cannot be confirmed by OCR.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from security.injection_guard import inspect

MAX_CHARS = 50000
_PERCENT = re.compile(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*%')
_AMOUNT = re.compile(r'(?:USD\s*|US\$\s*|\$\s*)(\d[\d,]*(?:\.\d{1,2})?)', re.IGNORECASE)
_INVOICE = re.compile(r'\b(?:INV|INVOICE)[- #:]*(\d{3,12})\b', re.IGNORECASE)
_TAX = re.compile(r'\b(?:tax\s*id|tax\s*number|vat\s*id)\s*[:#]?\s*([A-Z0-9\-]{7,20})', re.IGNORECASE)
_BANK_CHANGE = re.compile(r'(?:change|replace|switch|update|different|new)\s+(?:the\s+)?(?:bank\s+)?(?:account|beneficiary|payment\s+details)', re.IGNORECASE)
_BANK = re.compile(r'\b(?:bank\s+account|beneficiary\s+account|account\s+number)\b', re.IGNORECASE)
_AMBIGUOUS = re.compile(r'\b(?:as\s+soon\s+as\s+possible|at\s+our\s+discretion|when\s+convenient)\b', re.IGNORECASE)
_PAYMENT = re.compile(r'\b(?:payment|paid|deposit|advance|milestone|on\s+delivery|upon\s+acceptance)\b', re.IGNORECASE)


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
    percentages = [float(x) for x in _PERCENT.findall(content)]
    # Extract payment phases only on lines mentioning a payment event; don't count taxes, penalties etc.
    milestones: List[Dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not _PAYMENT.search(line):
            continue
        for m in _PERCENT.finditer(line):
            percent = float(m.group(1))
            milestones.append({'line': line_number, 'percentage': percent, 'evidence': line[:240]})
    flags = []
    def flag(code: str, severity: str, description: str, evidence: str):
        flags.append({'code': code, 'severity': severity, 'description': description, 'evidence': evidence})
    if inspect(content).suspicious:
        flag('UNTRUSTED_INSTRUCTIONS', 'high', 'Document contains instruction-like text; never execute it.', 'Prompt-injection pattern in document')
    if _BANK_CHANGE.search(content):
        flag('BENEFICIARY_CHANGE', 'high', 'Bank-account change wording needs independent callback verification.', 'Bank-detail change wording')
    if _AMBIGUOUS.search(content):
        flag('VAGUE_TERM', 'medium', 'Ambiguous timing or unilateral discretion should be reviewed.', 'Vague contractual language')
    total_pct = round(sum(x['percentage'] for x in milestones), 2)
    if milestones and abs(total_pct - 100) > 0.01:
        flag('PAYMENT_PERCENTAGES', 'medium', 'Payment milestone percentages do not sum to 100%.', f'{total_pct}% across marked milestones')
    if not _PAYMENT.search(content):
        flag('MISSING_PAYMENT_CLAUSE', 'medium', 'No recognizable payment wording found.', 'No payment terms found')
    if not re.search(r'\b(?:termination|terminate|cancel|cancellation)\b', content, re.IGNORECASE):
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
    kind = _text(data.get('contract_type', 'supply'), 'contract_type', 30).lower()
    if kind not in {'supply','services','construction'}:
        raise ValueError('contract_type must be supply, services, or construction')
    seller = _text(data.get('supplier', ''), 'supplier', 120)
    buyer = _text(data.get('customer', ''), 'customer', 120)
    scope = _text(data.get('scope', ''), 'scope', 1200)
    currency = str(data.get('currency', 'USD')).upper()
    if currency not in {'USD','VND','CNY','EUR'}:
        raise ValueError('Unsupported currency')
    amount = _money(data.get('amount'), 'amount')
    law = _text(data.get('governing_law', 'TO BE CONFIRMED BY COUNSEL'), 'governing_law', 120)
    milestones = data.get('milestones', [{'event':'Advance after signing','percentage':30},
                                         {'event':'Upon delivery','percentage':40},
                                         {'event':'After written acceptance','percentage':30}])
    if not isinstance(milestones, list) or not 1 <= len(milestones) <= 8:
        raise ValueError('Provide between 1 and 8 payment milestones')
    safe = []
    for row in milestones:
        if not isinstance(row, dict): raise ValueError('Each milestone must be an object')
        event = _text(row.get('event',''), 'milestone event', 180)
        pct = _money(row.get('percentage'), 'milestone percentage')
        if pct > 100: raise ValueError('Milestone percentage cannot exceed 100')
        safe.append({'event': event, 'percentage': pct, 'amount': round(amount*pct/100,2)})
    if abs(sum(m['percentage'] for m in safe)-100) > .001:
        raise ValueError('Milestone percentages must total 100')
    # Text generation is deterministic and intentionally marked DRAFT. No untrusted LLM completion.
    label = {'supply':'SUPPLY AGREEMENT','services':'SERVICES AGREEMENT','construction':'CONSTRUCTION SERVICES AGREEMENT'}[kind]
    parts = [f'DRAFT — FOR HUMAN LEGAL REVIEW ONLY\n{label}',
             f'1. PARTIES\nSupplier/Contractor: {seller}\nCustomer/Client: {buyer}',
             f'2. SCOPE\n{scope}',
             f'3. PRICE\nTotal contract consideration: {currency} {amount:,.2f}. Tax treatment to be confirmed.',
             '4. PAYMENT MILESTONES\n' + '\n'.join(f"- {m['event']}: {m['percentage']:g}% ({currency} {m['amount']:,.2f})" for m in safe),
             '5. DELIVERY AND ACCEPTANCE\nDates, specifications, evidence of acceptance and delivery remedies: [REQUIRES NEGOTIATION].',
             '6. INVOICING AND LATE PAYMENT\nInvoice deadline, payment due dates, late fees, dispute procedure: [REQUIRES NEGOTIATION].',
             '7. CONFIDENTIALITY AND DATA PROTECTION\n[APPROPRIATE TERMS REQUIRED].',
             '8. WARRANTIES AND LIABILITY\nScope, limitations, exclusions, warranties: [LEGAL REVIEW REQUIRED].',
             '9. TERMINATION AND DISPUTE RESOLUTION\nGrounds, notice, remedies, forum: [LEGAL REVIEW REQUIRED].',
             f'10. GOVERNING LAW\n{law}. Confirm with qualified counsel.',
             '11. SIGNATURES\nSupplier: [NOT SIGNED]    Customer: [NOT SIGNED]']
    document = '\n\n'.join(parts)
    return {'synthetic_demo': True, 'document_type': kind, 'draft': document, 'milestones': safe,
            'status': 'UNSIGNED_DRAFT_REQUIRES_LEGAL_REVIEW',
            'human_review_required': True, 'review_checklist': ['Confirm party identities and signatory authority',
                'Confirm applicable law and mandatory clauses', 'Negotiate acceptance, cancellation and dispute rules',
                'Verify bank details independently before making payments', 'Have qualified counsel approve before signature']}


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
