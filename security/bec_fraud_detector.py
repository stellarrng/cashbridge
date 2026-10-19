"""Business-email-compromise detector.

An email is BLOCKED when any of these is true:
  (a) it asks to change bank, IBAN or SWIFT details,
  (b) the sender domain is a lookalike of a verified contact domain (Levenshtein <= 2,
      a homoglyph swap, or the same name on a different TLD),
  (c) it quotes an account that is not in ``verified_payees``.

It is SUSPICIOUS when the sender domain is simply unknown. The detector only reads the
contact directory; it never updates payee details (that would be L4).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Set

from pydantic import BaseModel

from schemas.document_schemas import Email

_BANK_CHANGE = [
    re.compile(
        r"\b(?:change|changed|changing|update|updated|updating|new|revised|replace|replaced|modify)\b"
        r".{0,40}\b(?:bank|account|iban|swift|beneficiary|payment\s+details|banking\s+details)\b",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"\b(?:bank|account|banking|payment)\s+details\b.{0,40}\b(?:changed|changing|updated|new)\b", re.IGNORECASE | re.DOTALL),
]
_ACCOUNT_IN_TEXT = re.compile(
    r"(?-i:\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?\d{1,3})?\b)|(?:account|acct)(?:\s*(?:number|no\.?))?\s*[:#]?\s*(\d[\d -]{6,22}\d)",
    re.IGNORECASE,
)
_HOMOGLYPHS = str.maketrans({"1": "l", "i": "l", "0": "o", "5": "s"})


class BecVerdict(str, Enum):
    """Outcome of an email check."""

    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    BLOCKED = "BLOCKED"


class BecResult(BaseModel):
    """Verdict, reasons and the data needed for a UI alert card."""

    email_id: str
    sender: str
    subject: str
    verdict: BecVerdict
    reasons: List[str]

    def to_alert(self, alert_id: str) -> Dict[str, Any]:
        """Shape of one UI contract ``alerts`` entry."""
        return {
            "id": alert_id,
            "type": "BEC",
            "severity": "critical" if self.verdict is BecVerdict.BLOCKED else "medium",
            "sender": self.sender,
            "subject": self.subject,
            "reasons": self.reasons,
            "action_hint": "Verify by phone using the number on file. CashBridge never changes payee details.",
        }


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _skeleton(domain: str) -> str:
    return domain.lower().replace("rn", "m").replace("vv", "w").translate(_HOMOGLYPHS)


def is_lookalike(domain: str, verified: str) -> bool:
    """True if ``domain`` imitates ``verified`` without being it."""
    domain, verified = domain.lower(), verified.lower()
    if domain == verified:
        return False
    if levenshtein(domain, verified) <= 2:
        return True
    if _skeleton(domain) == _skeleton(verified):
        return True
    return domain.rsplit(".", 1)[0] == verified.rsplit(".", 1)[0]  # same name, different TLD


def _verified_domains(contacts: Mapping[str, Any]) -> Set[str]:
    domains: Set[str] = set()
    for contact in contacts.get("verified_contacts", []):
        domains.update(d.lower() for d in contact.get("domains", []))
    return domains


def _verified_accounts(contacts: Mapping[str, Any]) -> Set[str]:
    return {_digits_only(p.get("account", "")) for p in contacts.get("verified_payees", [])}


def _digits_only(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def analyze(email: Email, contacts: Mapping[str, Any]) -> BecResult:
    """Check one email against the verified contact directory (read-only)."""
    text = f"{email.subject}\n{email.body}"
    reasons: List[str] = []
    blocked = False

    if any(pattern.search(text) for pattern in _BANK_CHANGE):
        reasons.append("Requests change of bank account")
        blocked = True

    domain = email.sender_domain
    verified = _verified_domains(contacts)
    if domain not in verified:
        for known in sorted(verified):
            if is_lookalike(domain, known):
                reasons.append(f"Lookalike domain of {known}")
                blocked = True
                break

    accounts = _verified_accounts(contacts)
    for match in _ACCOUNT_IN_TEXT.finditer(text):
        quoted = _digits_only(match.group(1) or match.group(0))
        if quoted not in accounts:
            reasons.append("Account not in verified payees")
            blocked = True
            break

    if blocked:
        verdict = BecVerdict.BLOCKED
    elif domain not in verified:
        verdict = BecVerdict.SUSPICIOUS
        reasons.append("Sender domain is not in the verified contact directory")
    else:
        verdict = BecVerdict.CLEAN
    return BecResult(
        email_id=email.email_id,
        sender=email.sender,
        subject=email.subject,
        verdict=verdict,
        reasons=reasons,
    )


# ------------------------------------------------------------------ tax ID helper
_VN_TAX_ID = re.compile(r"^\d{10}(?:-?\d{3})?$")


def is_valid_vn_tax_id(tax_id: str, issuer_registry: Optional[FrozenSet[str]] = None) -> bool:
    """Vietnamese tax code format (10 or 13 digits) and, if given, presence in the issuer registry."""
    candidate = tax_id.strip()
    if not _VN_TAX_ID.match(candidate):
        return False
    if issuer_registry is None:
        return True
    return candidate.replace("-", "") in {t.replace("-", "") for t in issuer_registry}
