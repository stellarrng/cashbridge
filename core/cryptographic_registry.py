"""
Cryptographic Registry — hash-chained ledger of pledged invoices.

WHAT THIS DETECTS, AND WHAT IT DOES NOT
---------------------------------------
It detects an invoice being pledged twice *through this system*. That is a real
control and it is worth having.

It does NOT detect an invoice pledged to a funder that does not use CashBridge,
because this registry only sees what passes through it. Describing it as
"anti-double-financing" without that qualifier overstates it: the industry
problem is double financing across funders, which needs a shared registry or a
funder-side check. State the scope when presenting this.

DEFECTS FIXED
-------------
1. DUPLICATE DETECTION BY INVOICE ID ONLY. A party submitting the same trade
   twice simply renumbers the invoice: INV-2026-103 and INV-2026-103-A, same
   PO, same B/L, same goods. The registry is now indexed by document content
   hash as well as by ID, so the same underlying documents are caught under a
   new number.

2. THE INVERSE CASE WAS MISSED TOO. The same invoice ID arriving with a
   DIFFERENT content hash means the documents were altered between
   submissions. That is not a duplicate to block silently — it is a conflict
   that needs a human, and it now raises REVIEW_REQUIRED rather than a plain
   duplicate error.

3. verify_chain_integrity RECOMPUTED EACH BLOCK'S HASH FROM THE BLOCK'S OWN
   STORED `previous_block_hash` FIELD. Rewriting the whole chain therefore
   produced a chain that validated. It now walks forward from genesis, so a
   rewritten chain is caught unless the attacker also controls the externally
   anchored head hash — see `get_chain_head`.

4. REGISTRATION ACCEPTED ANY STRING AS A BUNDLE HASH. The seed file contains
   `"document_bundle_sha256": "sha256hash"`. Registration now requires a real
   64-character digest, so an unverified bundle cannot be pledged.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from config.settings import PermissionLevel
from config.runtime import registry_path
from security.permission_gatekeeper import request_permission

GENESIS_HASH = "0" * 64
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DoubleFinancingError(Exception):
    """Raised when an invoice or an identical document bundle is pledged twice."""


class RegistryConflictError(Exception):
    """
    Raised when the same invoice ID returns with different documents.

    Distinct from DoubleFinancingError: a duplicate is a blocked action, a
    conflict is an unresolved question about which version is genuine.
    """


def _load_registry() -> List[Dict[str, Any]]:
    path = registry_path()
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_registry(chain: List[Dict[str, Any]]) -> None:
    with open(registry_path(), "w", encoding="utf-8") as f:
        json.dump(chain, f, indent=2)


def _compute_block_hash(
    block_index: int,
    timestamp: str,
    invoice_id: str,
    document_bundle_sha256: str,
    financing_partner: str,
    advance_amount_usd: float,
    previous_block_hash: str,
) -> str:
    """
    Hash of a block's full contents.

    The previous version hashed only index, timestamp, invoice ID, bundle hash
    and previous hash — the partner and the amount were outside the hash, so
    either could be edited after the fact without breaking the chain.
    """
    raw = (
        f"{block_index}|{timestamp}|{invoice_id}|{document_bundle_sha256}|"
        f"{financing_partner}|{advance_amount_usd:.2f}|{previous_block_hash}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_invoice_registered(invoice_id: str) -> bool:
    """Whether this invoice ID already appears in the ledger."""
    return any(b.get("invoice_id") == invoice_id for b in _load_registry())


def find_by_bundle_hash(document_bundle_sha256: str) -> Optional[Dict[str, Any]]:
    """
    Find a prior pledge of the same document bundle under any invoice ID.

    This is the check that catches a renumbered resubmission of the same trade.
    """
    for block in _load_registry():
        if block.get("document_bundle_sha256") == document_bundle_sha256:
            return block
    return None


def check_registration(invoice_id: str, document_bundle_sha256: str) -> Dict[str, Any]:
    """
    Pre-flight check before pledging, returning a status rather than raising.

    Args:
        invoice_id: Invoice about to be pledged.
        document_bundle_sha256: Content hash from the verified 3-way match.

    Returns:
        Dict with 'status' in {'CLEAR', 'DUPLICATE_INVOICE_ID',
        'DUPLICATE_DOCUMENTS', 'REVIEW_REQUIRED'}, plus the conflicting block.
    """
    chain = _load_registry()
    by_id = next((b for b in chain if b.get("invoice_id") == invoice_id), None)
    by_hash = next(
        (b for b in chain if b.get("document_bundle_sha256") == document_bundle_sha256),
        None,
    )

    if by_id and by_id.get("document_bundle_sha256") == document_bundle_sha256:
        return {
            "status": "DUPLICATE_INVOICE_ID",
            "conflicting_block": by_id,
            "reason": (
                f"Invoice '{invoice_id}' with identical documents is already "
                f"pledged to {by_id.get('financing_partner')}."
            ),
        }

    if by_id and by_id.get("document_bundle_sha256") != document_bundle_sha256:
        return {
            "status": "REVIEW_REQUIRED",
            "conflicting_block": by_id,
            "reason": (
                f"Invoice '{invoice_id}' is already registered, but with a "
                f"DIFFERENT document bundle hash. The documents were altered "
                f"between submissions, or two different trades share an invoice "
                f"number. Verify with the issuer and the existing funder before "
                f"proceeding — do not resolve this automatically."
            ),
        }

    if by_hash:
        return {
            "status": "DUPLICATE_DOCUMENTS",
            "conflicting_block": by_hash,
            "reason": (
                f"These exact documents are already pledged under invoice "
                f"'{by_hash.get('invoice_id')}' to "
                f"{by_hash.get('financing_partner')}. The same trade is being "
                f"submitted under a different invoice number."
            ),
        }

    return {"status": "CLEAR", "conflicting_block": None, "reason": "No prior pledge found."}


def register_invoice(
    invoice_id: str,
    document_bundle_sha256: str,
    financing_partner: str,
    advance_amount_usd: float,
    actor: str = "SYSTEM_AGENT",
) -> dict:
    """
    Append a pledged invoice to the hash chain.

    Args:
        invoice_id: Invoice being pledged.
        document_bundle_sha256: Content hash from a VERIFIED_3WAY bundle. Must
            be a real 64-character digest.
        financing_partner: Funder receiving the pledge.
        advance_amount_usd: Advance amount.
        actor: Who initiated it.

    Returns:
        The new block.

    Raises:
        ValueError: If the bundle hash is not a valid SHA-256 digest.
        DoubleFinancingError: On a duplicate invoice or duplicate documents.
        RegistryConflictError: If the invoice returns with altered documents.
    """
    if not document_bundle_sha256 or not _SHA256_RE.match(document_bundle_sha256.lower()):
        raise ValueError(
            "document_bundle_sha256 must be a 64-character SHA-256 digest from a "
            "verified 3-way match. Refusing to pledge an invoice whose documents "
            "were never fingerprinted."
        )

    check = check_registration(invoice_id, document_bundle_sha256)

    if check["status"] == "REVIEW_REQUIRED":
        request_permission(
            PermissionLevel.L1_ANALYZE,
            "REGISTRY_CONFLICT_DETECTED",
            invoice_id,
            actor=actor,
            details={"reason": check["reason"]},
        )
        raise RegistryConflictError(check["reason"])

    if check["status"] in ("DUPLICATE_INVOICE_ID", "DUPLICATE_DOCUMENTS"):
        request_permission(
            PermissionLevel.L1_ANALYZE,
            "DOUBLE_FINANCING_BLOCKED",
            invoice_id,
            actor=actor,
            details={"reason": check["reason"], "status": check["status"]},
        )
        raise DoubleFinancingError(f"DOUBLE_FINANCING_BLOCKED: {check['reason']}")

    request_permission(
        PermissionLevel.L2_INTERNAL_WRITE,
        "REGISTER_INVOICE_TO_HASH_CHAIN",
        invoice_id,
        actor=actor,
        details={
            "financing_partner": financing_partner,
            "advance_amount_usd": advance_amount_usd,
            "document_bundle_sha256": document_bundle_sha256,
        },
    )

    chain = _load_registry()
    block_index = len(chain)
    previous_hash = chain[-1]["block_hash"] if chain else GENESIS_HASH
    timestamp = datetime.now(timezone.utc).isoformat()

    block = {
        "block_index": block_index,
        "timestamp_utc": timestamp,
        "invoice_id": invoice_id,
        "document_bundle_sha256": document_bundle_sha256,
        "financing_partner": financing_partner,
        "advance_amount_usd": round(advance_amount_usd, 2),
        "registered_by": actor,
        "previous_block_hash": previous_hash,
        "scope_note": "Visible to CashBridge only; not a cross-funder registry.",
    }
    block["block_hash"] = _compute_block_hash(
        block_index,
        timestamp,
        invoice_id,
        document_bundle_sha256,
        financing_partner,
        round(advance_amount_usd, 2),
        previous_hash,
    )

    chain.append(block)
    _save_registry(chain)
    return block


def get_registry() -> list:
    """Full chain, for display and audit export."""
    return _load_registry()


def get_chain_head() -> str:
    """
    Head hash, for external anchoring.

    A chain verified only against itself proves nothing to a party who does not
    trust the operator. Export this value to the funder, or publish it, so the
    chain can later be shown not to have been rewritten.
    """
    chain = _load_registry()
    return chain[-1]["block_hash"] if chain else GENESIS_HASH


def verify_chain_integrity(expected_head_hash: Optional[str] = None) -> dict:
    """
    Walk the chain from genesis and report the first inconsistency.

    Args:
        expected_head_hash: A previously anchored head hash. Supplying it is
            what turns self-consistency into real tamper evidence: without it,
            a party who can rewrite the whole file can produce a valid chain.

    Returns:
        Dict with 'is_valid', 'block_count', 'head_hash', 'first_violation'
        and 'anchor_checked'.
    """
    chain = _load_registry()
    if not chain:
        return {
            "is_valid": True,
            "block_count": 0,
            "head_hash": GENESIS_HASH,
            "first_violation": None,
            "anchor_checked": False,
        }

    running_prev = GENESIS_HASH
    for i, block in enumerate(chain):
        def fail(msg: str) -> dict:
            return {
                "is_valid": False,
                "block_count": len(chain),
                "head_hash": chain[-1].get("block_hash"),
                "first_violation": msg,
                "anchor_checked": expected_head_hash is not None,
            }

        if block.get("block_index") != i:
            return fail(f"Block at position {i} claims index {block.get('block_index')}.")

        # Compare against the hash computed by walking forward, not against the
        # value the block stores about its own predecessor.
        if block.get("previous_block_hash") != running_prev:
            return fail(
                f"Block {i}: previous_block_hash does not match the actual "
                f"preceding block — a block was removed, inserted or reordered."
            )

        try:
            expected = _compute_block_hash(
                block["block_index"],
                block["timestamp_utc"],
                block["invoice_id"],
                block["document_bundle_sha256"],
                block.get("financing_partner", ""),
                float(block.get("advance_amount_usd", 0.0)),
                running_prev,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return fail(f"Block {i} is malformed: {exc}")

        if expected != block.get("block_hash"):
            return fail(f"Block {i}: contents do not match the recorded hash.")

        running_prev = block["block_hash"]

    if expected_head_hash is not None and running_prev != expected_head_hash:
        return {
            "is_valid": False,
            "block_count": len(chain),
            "head_hash": running_prev,
            "first_violation": (
                "Chain is internally consistent but its head does not match the "
                "externally anchored hash — the whole chain was rewritten."
            ),
            "anchor_checked": True,
        }

    return {
        "is_valid": True,
        "block_count": len(chain),
        "head_hash": running_prev,
        "first_violation": None,
        "anchor_checked": expected_head_hash is not None,
    }
