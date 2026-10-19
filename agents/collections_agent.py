"""Collections agent (minimal): reminder drafting and buyer-reply parsing.

Everything here is deterministic. The LLM may later reword a draft, but dates are parsed by
rules and any number in a draft must pass the number lock. The full reminder ladder
(-3 days, due date, +7 / +15 / +30 days), JA/ZH templates and the OTP-gated first email per
buyer arrive in Step 5.2; this module covers the first rung and reply parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

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


LADDER: List[Tuple[int, str]] = [(-3, "gentle"), (0, "gentle"), (7, "firm"), (15, "firm"), (30, "escalation")]
LANGUAGES = {"US": "en", "JP": "ja", "CN": "zh"}


@dataclass(frozen=True)
class Rung:
    """One step of the reminder ladder: days from the due date, tone and the date to send."""

    offset_days: int
    stage: str
    scheduled_date: date


def ladder(invoice: CommercialInvoice) -> List[Rung]:
    """The five reminders for an invoice: 3 days before, on the due date, then 7, 15 and 30 days after."""
    return [Rung(offset, stage, invoice.due_date + timedelta(days=offset)) for offset, stage in LADDER]


def next_rung(invoice: CommercialInvoice, today: date) -> Optional[Rung]:
    """The first rung on or after ``today``; the last rung if every earlier date has passed."""
    rungs = ladder(invoice)
    return next((r for r in rungs if r.scheduled_date >= today), rungs[-1])


def language_for(invoice: CommercialInvoice) -> str:
    """Draft language by buyer market (English, Japanese or Chinese)."""
    return LANGUAGES.get(invoice.market, "en")


_TEMPLATES = {
    "en": {
        "before": "This is a friendly reminder that invoice {no} for {amount} is due on {due}. If payment is already on its way, please ignore this note and tell us the expected payment date.",
        "today": "Invoice {no} for {amount} falls due today ({due}). If payment has already been sent, please tell us the date so we can match it.",
        "firm": "Invoice {no} for {amount} was due on {due} and is now {days} days overdue. Please arrange payment this week or tell us the date you will pay.",
        "escalation": "Invoice {no} for {amount} was due on {due} and is now {days} days overdue. Unless we hear from you, we will pass this to our finance director and review the terms of future orders.",
        "greeting": "Dear {buyer},", "closing": "Thank you for your business.",
    },
    "ja": {
        "before": "請求書 {no}（{amount}）のお支払期日は {due} です。すでにお手続き済みの場合は、お支払予定日をご連絡ください。",
        "today": "請求書 {no}（{amount}）は本日（{due}）が期日です。送金済みの場合は、照合のため日付をお知らせください。",
        "firm": "請求書 {no}（{amount}）は {due} が期日で、現在 {days} 日が経過しています。今週中にお支払いいただくか、お支払予定日をご連絡ください。",
        "escalation": "請求書 {no}（{amount}）は {due} が期日で、現在 {days} 日が経過しています。ご連絡がない場合は、財務責任者に報告し、今後のお取引条件を見直します。",
        "greeting": "{buyer} 御中", "closing": "今後ともよろしくお願い申し上げます。",
    },
    "zh": {
        "before": "发票 {no}（{amount}）将于 {due} 到期。如已安排付款，请忽略此提醒并告知预计付款日期。",
        "today": "发票 {no}（{amount}）今日（{due}）到期。如已付款，请告知付款日期以便核对。",
        "firm": "发票 {no}（{amount}）已于 {due} 到期，现已逾期 {days} 天。请本周内安排付款，或告知付款日期。",
        "escalation": "发票 {no}（{amount}）已于 {due} 到期，现已逾期 {days} 天。若未收到回复，我们将上报财务总监并重新评估后续订单条款。",
        "greeting": "{buyer} 财务部：", "closing": "感谢您的合作。",
    },
}


def draft_reminder(invoice: CommercialInvoice, rung: Optional[Rung] = None) -> str:
    """Draft one rung of the ladder in the buyer's language (default: the gentle reminder 3 days before).

    The only numbers are the invoice amount, its due date and, for overdue rungs, the days overdue.
    """
    rung = rung or Rung(-3, "gentle", invoice.due_date - timedelta(days=3))
    t = _TEMPLATES[language_for(invoice)]
    key = "before" if rung.offset_days < 0 else "today" if rung.offset_days == 0 else "firm" if rung.stage == "firm" else "escalation"
    body = t[key].format(no=invoice.invoice_no, amount=invoice.amount.display(), due=invoice.due_date.isoformat(), days=rung.offset_days)
    return f"{t['greeting'].format(buyer=invoice.buyer_name)}\n\n{body}\n\n{t['closing']}\n\nSynthetic demo data."
