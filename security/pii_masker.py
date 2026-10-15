"""
PII Masker — redacts identifiers before text is sent to an external LLM.

WHY THE PREVIOUS PATTERNS WERE UNUSABLE
---------------------------------------
Three of the five regexes were so broad they destroyed the document:

  _SWIFT_PATTERN = r"\\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\\b"  + IGNORECASE

    With IGNORECASE this is "any 8 alphanumeric characters beginning with six
    letters". Ordinary words match: SHIPMENT, CONTRACT, DELIVERY, MATERIAL,
    PAYMENTS. Every such word in an invoice became [SWIFT_REDACTED], and the
    masked text handed to the model was unreadable.

  _TAX_ID_PATTERN = r"\\b(?:MST|EIN|VAT|TIN)?[-:\\s]?\\d{9,13}\\b"

    The label is optional, so this is "any 9-13 digit number". Invoice totals
    in VND (1,250,000,000), container numbers and dates were redacted as tax
    IDs — which silently corrupts the figures an extraction step then reads.

  _PHONE_PATTERN  matched essentially any 6-8 digit number, including amounts.

A masker that eats the amounts is worse than no masker: it produces confident
extraction from mutilated input. The patterns below are either structurally
validated (IBAN check characters, SWIFT with an ISO-3166 country code in
positions 5-6) or label-anchored, and masking order is managed so that one
pattern cannot consume another's match.

WHAT MASKING DOES NOT DO — read before describing this in a pitch
------------------------------------------------------------------
Removing account numbers and names does NOT anonymise a trade document.
Contract values, unit prices, shipment dates, port pairs, HS codes, vessel
names and quantities remain, and in a narrow export sector that combination
frequently identifies the buyer, the supplier and the commercial terms of the
deal. For a competitor, the prices alone are the sensitive part.

Treat this module as reducing the exposure of *direct identifiers*, not as
making the payload safe to send anywhere. Whether a document may be sent to a
third-party model at all is a data-rights question (customer contract terms,
buyer confidentiality clauses, cross-border transfer rules) that must be
answered before this function is called — `mask_pii` returns a
`residual_risk` note to keep that visible at the call site.
"""

import re
from typing import Tuple, Dict, List, Any

# ISO 3166-1 alpha-2 codes that appear in the IBAN/SWIFT corpus we care about.
# Restricting to real country codes is what stops ordinary English words from
# matching the SWIFT shape.
_ISO_COUNTRIES = (
    "AD|AE|AL|AT|AU|AZ|BA|BE|BG|BH|BR|BY|CA|CH|CN|CR|CY|CZ|DE|DK|DO|EE|EG|ES|"
    "FI|FO|FR|GB|GE|GI|GL|GR|GT|HK|HR|HU|IE|IL|IN|IQ|IS|IT|JO|JP|KR|KW|KZ|LB|"
    "LI|LT|LU|LV|MC|MD|ME|MK|MT|MU|MX|MY|NL|NO|NZ|PK|PL|PS|PT|QA|RO|RS|RU|SA|"
    "SE|SG|SI|SK|SM|TH|TN|TR|TW|UA|US|VA|VG|VN|XK"
)

# ── Structurally validated patterns ──────────────────────────────────────────

# IBAN: country code + 2 check digits + 11-30 alphanumerics. Case-sensitive:
# a real IBAN is written uppercase, and allowing lowercase matches prose.
_IBAN_PATTERN = re.compile(
    rf"\b(?:{_ISO_COUNTRIES})\d{{2}}[A-Z0-9]{{11,30}}\b"
)

# SWIFT/BIC. Two forms, because the bare 8-letter shape is not distinctive
# enough on its own:
#
#   (a) label-anchored — "SWIFT: DEUTDEFF", "BIC DEUTDEFF" — always masked;
#   (b) unlabelled, but only the 11-character form or one containing a digit.
#
# An ISO country code in positions 5-6 is necessary but nowhere near
# sufficient: SHIPMENT is SHIP+ME+NT (ME = Montenegro) and DISPATCH is
# DISP+AT+CH (AT = Austria), so a pure structural match still eats ordinary
# trade vocabulary.
#
# KNOWN GAP, stated rather than hidden: an unlabelled all-letter 8-character
# BIC such as a bare "DEUTDEFF" is NOT masked by form (b). Masking it would
# require also masking every 8-letter word in the document. Supply BICs in a
# labelled or structured field so form (a) applies; the ingestion path should
# not rely on free-text sweeping for this.
_SWIFT_LABELLED_PATTERN = re.compile(
    r"\b(?:SWIFT|BIC|SWIFT\s*/\s*BIC)\s*(?:Code|No\.?)?\s*[-:#]?\s*"
    r"([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b"
)
_SWIFT_STRUCTURAL_PATTERN = re.compile(
    rf"\b[A-Z]{{4}}(?:{_ISO_COUNTRIES})"
    rf"(?:[A-Z0-9]{{2}}[A-Z0-9]{{3}}|[A-Z0-9]*\d[A-Z0-9]*)\b"
)

# ── Label-anchored patterns (the digits alone are not distinctive) ───────────

# Tax ID only when actually labelled as one. An unlabelled 10-digit number in a
# trade document is far more likely to be a quantity or an amount.
_TAX_ID_PATTERN = re.compile(
    r"\b(?:MST|EIN|VAT(?:\s*No\.?)?|TIN|Tax\s*(?:ID|Code|No\.?)|"
    r"Tax\s*Identification(?:\s*Number)?)\s*[-:#]?\s*"
    r"([A-Z]{0,2}[-\s]?\d[\d\-\s]{7,16}\d)",
    re.IGNORECASE,
)

# Bank account only when labelled. Same reasoning as tax IDs.
_ACCOUNT_PATTERN = re.compile(
    r"\b(?:A/C|Acct\.?|Account)\s*(?:No\.?|Number|#)?\s*[-:#]?\s*"
    r"(\d[\d\-\s]{5,18}\d)",
    re.IGNORECASE,
)

# Phone only with an explicit label or a leading international dialling code.
# The previous unanchored version matched monetary amounts.
_PHONE_LABELLED_PATTERN = re.compile(
    r"\b(?:Tel|Phone|Mobile|Fax|Hotline|Contact)\s*[-:.]?\s*"
    r"(\+?\d[\d\s().\-]{6,18}\d)",
    re.IGNORECASE,
)
_PHONE_E164_PATTERN = re.compile(r"(?<![\w.])\+\d{1,3}[\s.\-]?\d{6,14}(?![\w.])")

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# ── Tokens ───────────────────────────────────────────────────────────────────

IBAN_TOKEN = "[IBAN_REDACTED]"
SWIFT_TOKEN = "[SWIFT_REDACTED]"
TAX_ID_TOKEN = "[TAX_ID_REDACTED]"
ACCOUNT_TOKEN = "[ACCOUNT_REDACTED]"
EMAIL_TOKEN = "[EMAIL_REDACTED]"
PHONE_TOKEN = "[PHONE_REDACTED]"

RESIDUAL_RISK_NOTE = (
    "Direct identifiers are masked. Commercial terms are not masked: prices, "
    "quantities, shipment dates, port pairs, vessel and buyer names all remain, "
    "and together they frequently identify the counterparty and the deal. "
    "Masking is not anonymisation. Confirm data-use rights before transmitting "
    "to any external model. Known gap: an unlabelled 8-letter BIC is not "
    "detected in free text."
)


def _mask_group(pattern: re.Pattern, text: str, token: str) -> Tuple[str, int]:
    """Replace only the captured group, keeping its label intact for context."""
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        if m.groups():
            start, end = m.span(1)
            return m.group(0)[: start - m.start()] + token + m.group(0)[end - m.start():]
        return token

    return pattern.sub(repl, text), count


def mask_pii(text: str) -> Tuple[str, int]:
    """
    Redact direct identifiers from text destined for an external model.

    Args:
        text: Raw text, typically extracted document or email content.

    Returns:
        (masked_text, number_of_replacements).

    Note:
        See `mask_pii_detailed` for a per-category breakdown and the residual
        risk note. Masking is not anonymisation — read the module docstring.
    """
    masked, detail = mask_pii_detailed(text)
    return masked, detail["total_replacements"]


def mask_pii_detailed(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Mask PII and report exactly what was removed.

    Order matters: IBAN before SWIFT (an IBAN's leading characters can look
    like a BIC), and labelled patterns before the bare E.164 phone form.

    Args:
        text: Raw text.

    Returns:
        (masked_text, report) where report carries per-category counts, the
        total, and the residual-risk note.
    """
    if not text:
        return text, {
            "total_replacements": 0,
            "by_category": {},
            "residual_risk": RESIDUAL_RISK_NOTE,
        }

    result = text
    counts: Dict[str, int] = {}

    result, counts["email"] = _mask_group(_EMAIL_PATTERN, result, EMAIL_TOKEN)
    result, counts["iban"] = _mask_group(_IBAN_PATTERN, result, IBAN_TOKEN)
    result, s1 = _mask_group(_SWIFT_LABELLED_PATTERN, result, SWIFT_TOKEN)
    result, s2 = _mask_group(_SWIFT_STRUCTURAL_PATTERN, result, SWIFT_TOKEN)
    counts["swift"] = s1 + s2
    result, counts["tax_id"] = _mask_group(_TAX_ID_PATTERN, result, TAX_ID_TOKEN)
    result, counts["account"] = _mask_group(_ACCOUNT_PATTERN, result, ACCOUNT_TOKEN)
    result, n1 = _mask_group(_PHONE_LABELLED_PATTERN, result, PHONE_TOKEN)
    result, n2 = _mask_group(_PHONE_E164_PATTERN, result, PHONE_TOKEN)
    counts["phone"] = n1 + n2

    return result, {
        "total_replacements": sum(counts.values()),
        "by_category": {k: v for k, v in counts.items() if v},
        "residual_risk": RESIDUAL_RISK_NOTE,
    }


def mask_pii_dict(data: dict) -> dict:
    """
    Recursively mask string values in a nested dict.

    Args:
        data: Payload that may contain identifiers in string values.

    Returns:
        A new dict with string values masked. Numeric values are left alone —
        masking a float is meaningless and the previous digit-matching regexes
        were the reason amounts were being corrupted.
    """
    masked: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            masked[key], _ = mask_pii(value)
        elif isinstance(value, dict):
            masked[key] = mask_pii_dict(value)
        elif isinstance(value, list):
            masked[key] = [
                mask_pii_dict(item)
                if isinstance(item, dict)
                else (mask_pii(item)[0] if isinstance(item, str) else item)
                for item in value
            ]
        else:
            masked[key] = value
    return masked
