"""
PII Masker — Redacts Personally Identifiable Information before text is transmitted
to any cloud-based LLM (e.g., OpenAI GPT-4o).

Masked fields:
  - IBAN / bank account numbers  → [IBAN_REDACTED]
  - SWIFT / BIC codes            → [SWIFT_REDACTED]
  - Tax IDs / EIN / VAT          → [TAX_ID_REDACTED]
  - Personal email addresses     → [EMAIL_REDACTED]
  - Phone numbers                → [PHONE_REDACTED]
"""

import re
from typing import Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Regex Patterns
# ─────────────────────────────────────────────────────────────────────────────

# IBAN: 2-letter country code + 2 check digits + up to 30 alphanumeric chars
_IBAN_PATTERN = re.compile(
    r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b",
    re.IGNORECASE,
)

# SWIFT / BIC: 8 or 11 character standard (e.g., BOFAUS3NXXX, DEUTDEDB)
_SWIFT_PATTERN = re.compile(
    r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b",
    re.IGNORECASE,
)

# Tax IDs (Vietnamese MST, US EIN ##-#######, generic VAT prefix)
_TAX_ID_PATTERN = re.compile(
    r"\b(?:MST|EIN|VAT|TIN)?[-:\s]?\d{9,13}\b",
    re.IGNORECASE,
)

# Standard email address
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Phone numbers (international + local formats)
_PHONE_PATTERN = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}\b"
)

# ─────────────────────────────────────────────────────────────────────────────
# Token Replacements
# ─────────────────────────────────────────────────────────────────────────────

IBAN_TOKEN = "[IBAN_REDACTED]"
SWIFT_TOKEN = "[SWIFT_REDACTED]"
TAX_ID_TOKEN = "[TAX_ID_REDACTED]"
EMAIL_TOKEN = "[EMAIL_REDACTED]"
PHONE_TOKEN = "[PHONE_REDACTED]"


def mask_pii(text: str) -> Tuple[str, int]:
    """
    Redact all PII from the input text before it is sent to a cloud LLM.

    Args:
        text: Raw input string potentially containing sensitive information.

    Returns:
        A tuple of (masked_text, count_of_replacements_made).
    """
    total_replacements = 0
    result = text

    # Order matters: mask SWIFT before IBAN to avoid partial overlaps
    result, n = _SWIFT_PATTERN.subn(SWIFT_TOKEN, result)
    total_replacements += n

    result, n = _IBAN_PATTERN.subn(IBAN_TOKEN, result)
    total_replacements += n

    result, n = _EMAIL_PATTERN.subn(EMAIL_TOKEN, result)
    total_replacements += n

    result, n = _TAX_ID_PATTERN.subn(TAX_ID_TOKEN, result)
    total_replacements += n

    result, n = _PHONE_PATTERN.subn(PHONE_TOKEN, result)
    total_replacements += n

    return result, total_replacements


def mask_pii_dict(data: dict) -> dict:
    """
    Recursively mask all string values inside a dictionary (e.g., a JSON payload).

    Args:
        data: Input dict that may contain PII in string values.

    Returns:
        A new dict with all string values masked.
    """
    masked = {}
    for key, value in data.items():
        if isinstance(value, str):
            masked[key], _ = mask_pii(value)
        elif isinstance(value, dict):
            masked[key] = mask_pii_dict(value)
        elif isinstance(value, list):
            masked[key] = [
                mask_pii_dict(item) if isinstance(item, dict)
                else (mask_pii(item)[0] if isinstance(item, str) else item)
                for item in value
            ]
        else:
            masked[key] = value
    return masked
