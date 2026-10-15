"""
BEC Fraud Detector — Business Email Compromise Defense Module.

Automatically scans incoming supplier and buyer emails for:
  1. Lookalike / typosquatted sender domains (e.g., nordichorne.com vs nordichome.com)
  2. Fraudulent bank account / IBAN / SWIFT change requests
  3. Suspicious urgency language used in social engineering attacks

When a CRITICAL_BLOCK threat is detected, the system logs the event and
prevents any payment action from proceeding.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import List, Tuple

from security.pii_masker import mask_pii


# ─────────────────────────────────────────────────────────────────────────────
# Known Legitimate Buyer Domains (Trusted Whitelist)
# ─────────────────────────────────────────────────────────────────────────────

TRUSTED_BUYER_DOMAINS = {
    "nordichome.com",
    "sakurafurniture.co.jp",
    "greatwallimports.cn",
    "pacifictiber.vn",
}


# ─────────────────────────────────────────────────────────────────────────────
# BEC Attack Patterns
# ─────────────────────────────────────────────────────────────────────────────

# Keywords strongly associated with SWIFT/bank account change fraud
_BANK_CHANGE_KEYWORDS = [
    "new bank account",
    "updated banking details",
    "change our bank",
    "new iban",
    "new swift",
    "new wire instructions",
    "new payment instructions",
    "redirect payment",
    "updated account number",
    "new routing",
    "please update your records",
    "effective immediately",
]

# Urgency / pressure tactics used in social engineering
_URGENCY_KEYWORDS = [
    "urgent",
    "immediately",
    "as soon as possible",
    "asap",
    "do not delay",
    "action required",
    "time sensitive",
]

# Patterns to extract raw SWIFT and IBAN from email body
_SWIFT_EXTRACTOR = re.compile(r"\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b")
_IBAN_EXTRACTOR = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{4,30})\b")


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute edit distance between two strings for typosquat detection."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insert = prev_row[j + 1] + 1
            delete = curr_row[j] + 1
            replace = prev_row[j] + (c1 != c2)
            curr_row.append(min(insert, delete, replace))
        prev_row = curr_row
    return prev_row[-1]


def _is_spoofed_domain(sender_domain: str) -> Tuple[bool, str]:
    """
    Detect if the sender domain is a lookalike of a known trusted buyer domain.
    Returns (is_spoofed, closest_legit_domain_matched).
    """
    sender_domain = sender_domain.lower().strip()
    if sender_domain in TRUSTED_BUYER_DOMAINS:
        return False, ""
    for legit in TRUSTED_BUYER_DOMAINS:
        dist = _levenshtein_distance(sender_domain, legit)
        # Distance of 1–3 edits on domains of similar length = likely spoofed
        if 0 < dist <= 3 and abs(len(sender_domain) - len(legit)) <= 3:
            return True, legit
    return False, ""


def scan_email(
    email_id: str,
    sender_email: str,
    subject: str,
    body: str,
) -> dict:
    """
    Scan an incoming email for BEC fraud indicators.

    Args:
        email_id: Unique identifier for the email (e.g., 'EMAIL-001').
        sender_email: Full sender address (e.g., 'finance@nordichorne.com').
        subject: Email subject line.
        body: Full email body text.

    Returns:
        A dict with threat_level ('SAFE' | 'MEDIUM' | 'CRITICAL_BLOCK'),
        detected indicators, extracted bank details, and sanitized body text.
    """
    sender_domain = sender_email.split("@")[-1] if "@" in sender_email else sender_email
    combined_text = f"{subject} {body}".lower()
    timestamp = datetime.now(timezone.utc).isoformat()

    suspicious_keywords: List[str] = []
    flagged_bank_change = False

    # 1. Detect domain spoofing
    is_spoofed, matched_legit_domain = _is_spoofed_domain(sender_domain)

    # 2. Detect bank account change language
    for keyword in _BANK_CHANGE_KEYWORDS:
        if keyword in combined_text:
            suspicious_keywords.append(keyword)
            flagged_bank_change = True

    # 3. Detect urgency pressure tactics
    for keyword in _URGENCY_KEYWORDS:
        if keyword in combined_text:
            suspicious_keywords.append(f"[URGENCY] {keyword}")

    # 4. Extract any SWIFT / IBAN mentioned in the email body
    extracted_swift_matches = _SWIFT_EXTRACTOR.findall(body.upper())
    extracted_iban_matches = _IBAN_EXTRACTOR.findall(body.upper())
    extracted_swift = extracted_swift_matches[0] if extracted_swift_matches else None
    extracted_iban = extracted_iban_matches[0] if extracted_iban_matches else None

    # 5. Determine threat level
    if is_spoofed and flagged_bank_change:
        threat_level = "CRITICAL_BLOCK"
        reason = (
            f"CRITICAL BLOCK: Spoofed domain '{sender_domain}' resembles trusted "
            f"buyer '{matched_legit_domain}' AND email contains fraudulent bank "
            f"account change request. Suspected Business Email Compromise (BEC) attack."
        )
    elif is_spoofed:
        threat_level = "CRITICAL_BLOCK"
        reason = (
            f"CRITICAL BLOCK: Sender domain '{sender_domain}' is a lookalike of "
            f"trusted buyer domain '{matched_legit_domain}'. Do NOT respond or transfer funds."
        )
    elif flagged_bank_change:
        threat_level = "CRITICAL_BLOCK"
        reason = (
            "CRITICAL BLOCK: Email contains bank account / SWIFT change instructions. "
            "Always verify out-of-band via a known phone number before acting."
        )
    elif suspicious_keywords:
        threat_level = "MEDIUM"
        reason = "MEDIUM: Urgency language detected. Treat with caution and verify sender."
    else:
        threat_level = "SAFE"
        reason = "No BEC indicators detected."

    # Sanitize the email body (mask PII for logging)
    sanitized_body, _ = mask_pii(body)

    return {
        "scan_id": str(uuid.uuid4()),
        "email_id": email_id,
        "timestamp_utc": timestamp,
        "sender_email": sender_email,
        "sender_domain": sender_domain,
        "is_spoofed_domain": is_spoofed,
        "matched_legit_domain": matched_legit_domain if is_spoofed else None,
        "detected_suspicious_keywords": list(set(suspicious_keywords)),
        "flagged_bank_change": flagged_bank_change,
        "extracted_swift": extracted_swift,
        "extracted_iban": extracted_iban,
        "threat_level": threat_level,
        "reason": reason,
        "sanitized_body": sanitized_body,
    }
