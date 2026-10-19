"""PII masking: replace sensitive values with reversible tokens before any cloud LLM call.

Tokens: [ACCT_n] IBAN and bank accounts, [SWIFT_n] SWIFT/BIC, [TAXID_n] tax IDs,
[EMAIL_n] emails, [PHONE_n] phone numbers, [PERSON_n] names from the contact directory.

The token map stays in process memory and is never logged. ``PiiMasker.last_pair`` keeps
the latest before/after text for the UI "PII inspector".
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

TokenMap = Dict[str, str]

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TAX_LABELLED = re.compile(
    r"(?P<label>(?:tax\s*(?:id|code|no\.?|number)|MST)\s*[:#]?\s*)(?P<value>\d{10}(?:-?\d{3})?)\b",
    re.IGNORECASE,
)
_SWIFT_LABELLED = re.compile(
    r"(?P<label>(?:SWIFT|BIC)(?:\s*code)?\s*[:#]?\s*)(?P<value>[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b"
)
_IBAN = re.compile(
    r"(?:\bIBAN\s*[:#]?\s*)?\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?\d{1,3})?\b"
)
_ACCOUNT_LABELLED = re.compile(
    r"(?:\b(?:account|acct)(?:\s*(?:number|no\.?))?\s*[:#]?\s*)\d[\d -]{6,22}\d", re.IGNORECASE
)
_LONG_DIGITS = re.compile(r"(?<![\d,.])\d{9,19}(?![\d,.])")
_PHONE = re.compile(r"\+\d{1,3}(?:[\s.-]?\d{2,4}){2,4}\b|(?<![\d,.])0\d{2,3}[\s.-]\d{3,4}[\s.-]\d{3,4}\b")


class PiiMasker:
    """Stateful masker; one instance per LLM call keeps tokens consistent."""

    def __init__(self) -> None:
        self.last_pair: Optional[Tuple[str, str]] = None

    def mask(self, text: str, directory: Optional[Mapping[str, Iterable[str]]] = None) -> Tuple[str, TokenMap]:
        """Return (masked_text, token_map). ``directory`` keys: names, emails, phones, tax_ids, accounts, swifts."""
        token_map: TokenMap = {}
        counters: Dict[str, int] = {}
        by_value: Dict[str, str] = {}

        def token_for(kind: str, value: str) -> str:
            if value in by_value:
                return by_value[value]
            counters[kind] = counters.get(kind, 0) + 1
            token = f"[{kind}_{counters[kind]}]"
            by_value[value] = token
            token_map[token] = value
            return token

        masked = text
        directory = directory or {}
        for key, kind in (
            ("accounts", "ACCT"),
            ("swifts", "SWIFT"),
            ("tax_ids", "TAXID"),
            ("emails", "EMAIL"),
            ("phones", "PHONE"),
            ("names", "PERSON"),
        ):
            for value in sorted(directory.get(key, []), key=len, reverse=True):
                if value:
                    masked = re.sub(re.escape(value), lambda _m, k=kind, v=value: token_for(k, v), masked, flags=re.IGNORECASE)

        masked = _EMAIL.sub(lambda m: token_for("EMAIL", m.group(0)), masked)
        masked = _TAX_LABELLED.sub(lambda m: m.group("label") + token_for("TAXID", m.group("value")), masked)
        masked = _SWIFT_LABELLED.sub(lambda m: m.group("label") + token_for("SWIFT", m.group("value")), masked)
        masked = _IBAN.sub(lambda m: token_for("ACCT", m.group(0)), masked)
        masked = _ACCOUNT_LABELLED.sub(lambda m: token_for("ACCT", m.group(0)), masked)
        masked = _LONG_DIGITS.sub(lambda m: token_for("ACCT", m.group(0)), masked)
        masked = _PHONE.sub(lambda m: token_for("PHONE", m.group(0)), masked)

        self.last_pair = (text, masked)
        return masked, token_map

    @staticmethod
    def unmask(text: str, token_map: TokenMap) -> str:
        """Put the original values back. Longer tokens first so [ACCT_10] beats [ACCT_1]."""
        for token in sorted(token_map, key=len, reverse=True):
            text = text.replace(token, token_map[token])
        return text

    def inspector(self) -> Dict[str, str]:
        """The last before/after pair in the UI contract ``pii_inspector`` shape."""
        before, after = self.last_pair or ("", "")
        return {"before": before, "after": after}


def mask_all(texts: List[str], directory: Optional[Mapping[str, Iterable[str]]] = None) -> Tuple[List[str], TokenMap]:
    """Mask several texts with one shared token map."""
    masker = PiiMasker()
    joined, token_map = masker.mask("␞".join(texts), directory)
    return joined.split("␞"), token_map
