"""Collections agent (minimal): reminder drafting and buyer-reply parsing.

Everything here is deterministic. The LLM may later reword a draft, but dates are parsed by
rules and any number in a draft must pass the number lock. The full reminder ladder
(-3 days, due date, +7 / +15 / +30 days), JA/ZH templates and the OTP-gated first email per
buyer arrive in Step 5.2; this module covers the first rung and reply parsing.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from schemas.document_schemas import CommercialInvoice
from schemas.agent_schemas import PaymentPromise

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_PROMISE = re.compile(
    r"\bwill\s+pay\s+(?:on\s+)?(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s+(?P<year>\d{4}))?",
    re.IGNORECASE,
)
_INVOICE_REF = re.compile(r"INV[-\s]?(\d+)", re.IGNORECASE)


def invoice_in_text(text: str) -> Optional[str]:
    """First invoice number named in ``text``, normalised to ``INV-nnnn``."""
    match = _INVOICE_REF.search(text)
    return f"INV-{match.group(1)}" if match else None


def parse_payment_promise(text: str, invoice_id: str, buyer: str, today: date) -> Optional[PaymentPromise]:
    """Turn "we will pay on Nov 20" into a dated promise. Returns None if no date is stated.

    A date without a year means its next occurrence on or after ``today``.
    """
    match = _PROMISE.search(text)
    if not match:
        return None
    month = _MONTHS.get(match.group("month")[:3].lower())
    if month is None:
        return None
    day = int(match.group("day"))
    try:
        if match.group("year"):
            promised = date(int(match.group("year")), month, day)
        else:
            promised = date(today.year, month, day)
            if promised < today:
                promised = date(today.year + 1, month, day)
    except ValueError:
        return None
    return PaymentPromise(invoice_id=invoice_id, buyer=buyer, promised_date=promised, source_text=text.strip())


def draft_reminder(invoice: CommercialInvoice) -> str:
    """Gentle first reminder. The only numbers are the invoice amount and its due date."""
    return (
        f"Dear {invoice.buyer_name},\n\n"
        f"This is a friendly reminder that invoice {invoice.invoice_no} for {invoice.amount.display()} "
        f"is due on {invoice.due_date.isoformat()}. If payment is already on its way, please ignore this "
        "note and tell us the expected payment date.\n\nThank you for your business.\n\nSynthetic demo data."
    )
