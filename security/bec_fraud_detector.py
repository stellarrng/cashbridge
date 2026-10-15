"""
BEC Fraud Detector — screens inbound mail for business email compromise.

WHY THE PREVIOUS THRESHOLDS WERE WRONG IN BOTH DIRECTIONS
----------------------------------------------------------
Too aggressive. Any one of these alone produced CRITICAL_BLOCK:

  * a sender domain within Levenshtein distance 3 of a trusted domain, and
  * any of twelve keyword phrases, including "effective immediately" and
    "please update your records" — phrases that appear constantly in ordinary
    supplier correspondence.

Distance-3 on short domains is very loose: "sakurafurniture.co.jp" and
"sakurafurniture.com" differ by 3, and a legitimate regional domain gets
blocked. A control that blocks routine mail is switched off within a week, and
then it protects nobody.

Too lax. A domain NOT resembling any trusted domain was scored SAFE, so a bank
change request from a completely unrelated address — the most common real BEC
pattern — passed with "No BEC indicators detected".

WHAT CHANGED
------------
  * Evidence is scored and combined; no single weak signal blocks.
  * A bank-detail change from ANY unrecognised sender is at minimum
    REVIEW_REQUIRED, because that is the actual attack.
  * REVIEW_REQUIRED exists between MEDIUM and CRITICAL_BLOCK, so the system can
    say "I cannot decide this" instead of guessing.
  * Known subdomains of trusted domains are recognised rather than flagged.
  * Verification is always out-of-band: the module never asserts an email is
    genuine. Headers here are unauthenticated — there is no SPF, DKIM or DMARC
    check in this build, and a convincing forgery with correct-looking details
    will score SAFE. That limitation is returned in every result.

NOTE: the previous TRUSTED_BUYER_DOMAINS contained "pacifictiber.vn", a typo of
the exporter's own name. A typo in a trust list is a live vulnerability: mail
from the typo domain is trusted, and mail from the real one is flagged as its
lookalike.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any

from security.pii_masker import mask_pii_detailed

# ── Trust list ───────────────────────────────────────────────────────────────
TRUSTED_BUYER_DOMAINS = {
    "nordichome.com",
    "sakurafurniture.co.jp",
    "greatwallimports.cn",
    "pacifictimber.vn",   # was "pacifictiber.vn" — a typo in a trust list is a hole
}

# ── Signals ──────────────────────────────────────────────────────────────────
_BANK_CHANGE_PHRASES = [
    "new bank account", "updated banking details", "change our bank",
    "new iban", "new swift", "new wire instructions", "new payment instructions",
    "redirect payment", "updated account number", "new routing",
    "change of bank", "banking details have changed", "remit to the new account",
]

# Weak on their own — ordinary business language. Only meaningful alongside a
# bank-detail change or a suspicious sender.
_WEAK_PRESSURE_PHRASES = [
    "urgent", "immediately", "as soon as possible", "asap", "do not delay",
    "action required", "time sensitive", "effective immediately",
    "please update your records", "before close of business",
]

# Phrases designed to defeat the out-of-band check itself. These are strong.
_VERIFICATION_EVASION_PHRASES = [
    "do not call", "cannot be reached by phone", "email only",
    "keep this confidential", "do not discuss", "i am in a meeting",
    "unable to take calls", "bypass the usual",
]

_ISO = (
    "AD|AE|AT|AU|BE|BG|BH|BR|CA|CH|CN|CY|CZ|DE|DK|EE|EG|ES|FI|FR|GB|GR|HK|HR|"
    "HU|IE|IL|IN|IT|JP|KR|KW|LT|LU|LV|MT|MX|MY|NL|NO|NZ|PL|PT|QA|RO|SA|SE|SG|"
    "SI|SK|TH|TR|TW|US|VN"
)
_SWIFT_EXTRACTOR = re.compile(rf"\b[A-Z]{{4}}(?:{_ISO})[A-Z0-9]{{2}}(?:[A-Z0-9]{{3}})?\b")
_IBAN_EXTRACTOR = re.compile(rf"\b(?:{_ISO})\d{{2}}[A-Z0-9]{{11,30}}\b")

LIMITATIONS = [
    "No SPF, DKIM or DMARC validation — the sender address is unauthenticated "
    "and trivially forgeable.",
    "No reply-to / display-name mismatch analysis.",
    "No check of whether the account itself is compromised: mail genuinely sent "
    "from a real, trusted, hijacked mailbox will score SAFE.",
    "No attachment or embedded-link inspection.",
    "A SAFE verdict means no indicator was found, not that the message is "
    "genuine. Bank detail changes must always be confirmed by voice on a "
    "number from the contract, never a number in the email.",
]


def _levenshtein(s1: str, s2: str) -> int:
    """Edit distance, for lookalike-domain detection."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def _classify_sender(sender_domain: str) -> Tuple[str, str]:
    """
    Classify the sender domain.

    Returns:
        (classification, matched_trusted_domain) where classification is
        'TRUSTED', 'LOOKALIKE' or 'UNKNOWN'.

    'UNKNOWN' is not innocent — it is simply not yet suspicious on its own. The
    previous implementation treated unknown as safe, which is why a bank change
    request from an unrelated domain scored SAFE.
    """
    d = sender_domain.lower().strip()
    if d in TRUSTED_BUYER_DOMAINS:
        return "TRUSTED", d

    # A subdomain of a trusted domain (mail.nordichome.com) is not a lookalike.
    for legit in TRUSTED_BUYER_DOMAINS:
        if d.endswith("." + legit):
            return "TRUSTED", legit

    # Tighten the lookalike test: distance 1-2 on comparable-length domains.
    # Distance 3 produced false positives on legitimate regional variants.
    for legit in TRUSTED_BUYER_DOMAINS:
        dist = _levenshtein(d, legit)
        if 0 < dist <= 2 and abs(len(d) - len(legit)) <= 2:
            return "LOOKALIKE", legit

    # Same brand token, different TLD or suffix (nordichome.co vs .com).
    for legit in TRUSTED_BUYER_DOMAINS:
        brand = legit.split(".")[0]
        if len(brand) >= 6 and d.split(".")[0] == brand and d != legit:
            return "LOOKALIKE", legit

    return "UNKNOWN", ""


def scan_email(email_id: str, sender_email: str, subject: str, body: str) -> dict:
    """
    Score an inbound email for BEC indicators.

    Threat levels:
        SAFE             no indicator found (not a guarantee of authenticity)
        MEDIUM           pressure language only; note it, do not block
        REVIEW_REQUIRED  payment details are being changed, or the sender is
                         suspicious — stop and verify out of band
        CRITICAL_BLOCK   lookalike domain plus a payment-detail change, or
                         evasion of the verification step itself

    Args:
        email_id: Identifier for the message.
        sender_email: Full sender address.
        subject: Subject line.
        body: Message body.

    Returns:
        Dict with threat_level, score, the indicators found, any extracted
        bank details, the required next action, and this build's limitations.
    """
    sender_domain = sender_email.split("@")[-1] if "@" in sender_email else sender_email
    text = f"{subject}\n{body}".lower()
    timestamp = datetime.now(timezone.utc).isoformat()

    sender_class, matched_domain = _classify_sender(sender_domain)

    bank_change_hits = [p for p in _BANK_CHANGE_PHRASES if p in text]
    pressure_hits = [p for p in _WEAK_PRESSURE_PHRASES if p in text]
    evasion_hits = [p for p in _VERIFICATION_EVASION_PHRASES if p in text]

    swifts = _SWIFT_EXTRACTOR.findall(body.upper())
    ibans = _IBAN_EXTRACTOR.findall(body.upper())
    carries_bank_details = bool(swifts or ibans)

    flagged_bank_change = bool(bank_change_hits) or (
        carries_bank_details and sender_class != "TRUSTED"
    )

    # ── Weighted scoring ──────────────────────────────────────────────────
    score = 0
    indicators: List[str] = []

    if sender_class == "LOOKALIKE":
        score += 50
        indicators.append(
            f"Sender domain '{sender_domain}' closely resembles trusted domain "
            f"'{matched_domain}'."
        )
    elif sender_class == "UNKNOWN":
        score += 15
        indicators.append(f"Sender domain '{sender_domain}' is not a known counterparty.")

    if bank_change_hits:
        score += 40
        indicators.append(
            f"Payment-detail change language: {', '.join(bank_change_hits[:3])}."
        )
    if carries_bank_details:
        score += 20
        indicators.append("Message contains bank routing details (IBAN/SWIFT).")
    if evasion_hits:
        score += 35
        indicators.append(
            f"Attempts to prevent out-of-band verification: {', '.join(evasion_hits[:3])}."
        )
    if pressure_hits:
        score += 10
        indicators.append(f"Pressure language: {', '.join(pressure_hits[:3])}.")

    # ── Verdict ───────────────────────────────────────────────────────────
    if sender_class == "LOOKALIKE" and flagged_bank_change:
        level = "CRITICAL_BLOCK"
        reason = (
            f"Lookalike domain '{sender_domain}' (resembling '{matched_domain}') "
            f"combined with a payment-detail change. This is the standard BEC "
            f"pattern. Do not act on these details."
        )
    elif evasion_hits and flagged_bank_change:
        level = "CRITICAL_BLOCK"
        reason = (
            "A payment-detail change accompanied by language discouraging "
            "verification by phone. Legitimate counterparties do not object to "
            "being called back."
        )
    elif sender_class == "LOOKALIKE":
        level = "CRITICAL_BLOCK"
        reason = (
            f"Sender domain '{sender_domain}' is a lookalike of trusted domain "
            f"'{matched_domain}'. Treat all content as hostile."
        )
    elif flagged_bank_change:
        level = "REVIEW_REQUIRED"
        reason = (
            "The message changes payment details. CashBridge cannot determine "
            "whether this is legitimate: a genuine account change and a BEC "
            "attack look identical in the message body. Confirm by voice on a "
            "number taken from the signed contract before any payment is made."
        )
    elif pressure_hits and sender_class == "UNKNOWN":
        level = "MEDIUM"
        reason = (
            "Pressure language from an unrecognised sender. No payment-detail "
            "change detected; proceed with normal caution."
        )
    elif pressure_hits:
        level = "MEDIUM"
        reason = "Pressure language detected from a known sender. Note and proceed."
    else:
        level = "SAFE"
        reason = (
            "No BEC indicator found. This is the absence of a signal, not "
            "evidence that the message is genuine — see limitations."
        )

    next_action = {
        "CRITICAL_BLOCK": "BLOCK: do not reply, do not pay. Escalate and contact "
                          "the counterparty on a known-good number.",
        "REVIEW_REQUIRED": "HOLD: verify out of band by voice before any payment "
                           "or master-data change. Do not reply to this message.",
        "MEDIUM": "PROCEED WITH CAUTION: no payment change requested.",
        "SAFE": "PROCEED under normal controls.",
    }[level]

    sanitized_body, mask_report = mask_pii_detailed(body)

    return {
        "scan_id": str(uuid.uuid4()),
        "email_id": email_id,
        "timestamp_utc": timestamp,
        "sender_email": sender_email,
        "sender_domain": sender_domain,
        "sender_classification": sender_class,
        "matched_trusted_domain": matched_domain or None,
        "is_spoofed_domain": sender_class == "LOOKALIKE",
        "flagged_bank_change": flagged_bank_change,
        "risk_score": score,
        "indicators": indicators,
        "detected_suspicious_keywords": sorted(
            set(bank_change_hits + pressure_hits + evasion_hits)
        ),
        "extracted_swift": swifts[0] if swifts else None,
        "extracted_iban": ibans[0] if ibans else None,
        "threat_level": level,
        "reason": reason,
        "required_next_action": next_action,
        "sanitized_body": sanitized_body,
        "pii_masking_report": mask_report,
        "detection_limitations": list(LIMITATIONS),
    }
