"""
Cryptographic Registry — SHA-256 Hash-Chain Ledger for Anti-Double-Financing.

Maintains an immutable local hash chain (like a blockchain) where every pledged
invoice is recorded. Any attempt to finance an already-registered invoice raises
a DOUBLE_FINANCING_BLOCKED error.

Data stored in: data/execution_evidence/audit_hash_registry.json
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import AUDIT_HASH_REGISTRY_PATH, EXECUTION_EVIDENCE_DIR, PermissionLevel
from security.permission_gatekeeper import request_permission


EXECUTION_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

GENESIS_HASH = "0" * 64  # Genesis block previous hash


class DoubleFinancingError(Exception):
    """Raised when an invoice is submitted for financing a second time."""
    pass


def _load_registry() -> list:
    """Load the full hash-chain registry from disk. Returns empty list if not yet created."""
    if not AUDIT_HASH_REGISTRY_PATH.exists():
        return []
    with open(AUDIT_HASH_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_registry(chain: list) -> None:
    """Persist the updated hash chain to disk."""
    with open(AUDIT_HASH_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(chain, f, indent=2)


def _compute_block_hash(block_index: int, timestamp: str, invoice_id: str,
                        document_bundle_sha256: str, previous_block_hash: str) -> str:
    """Deterministic SHA-256 hash of a block's contents."""
    raw = f"{block_index}|{timestamp}|{invoice_id}|{document_bundle_sha256}|{previous_block_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_invoice_registered(invoice_id: str) -> bool:
    """
    Check if an invoice is already registered in the anti-double-financing ledger.

    Args:
        invoice_id: The invoice to check (e.g., 'INV-2026-103').

    Returns:
        True if the invoice has already been pledged, False if safe to proceed.
    """
    chain = _load_registry()
    return any(block.get("invoice_id") == invoice_id for block in chain)


def register_invoice(
    invoice_id: str,
    document_bundle_sha256: str,
    financing_partner: str,
    advance_amount_usd: float,
    actor: str = "SYSTEM_AGENT",
) -> dict:
    """
    Register an invoice in the immutable SHA-256 hash-chain anti-double-financing ledger.

    This is an L2_INTERNAL_WRITE action (auto-approved). Appends a new block to the chain
    linking to the previous block's hash, creating a tamper-evident audit trail.

    Args:
        invoice_id: Invoice being pledged (e.g., 'INV-2026-103').
        document_bundle_sha256: SHA-256 fingerprint of the full trade document bundle.
        financing_partner: Name of the financing provider.
        advance_amount_usd: USD advance amount being received.
        actor: The system agent or user initiating the registration.

    Returns:
        The newly created block dict.

    Raises:
        DoubleFinancingError: If the invoice is already registered in the ledger.
    """
    # Check for double-financing attempt FIRST
    if is_invoice_registered(invoice_id):
        raise DoubleFinancingError(
            f"DOUBLE_FINANCING_BLOCKED: Invoice '{invoice_id}' is already registered in the "
            f"SHA-256 anti-double-financing ledger. This invoice cannot be pledged again."
        )

    # L2 permission check — auto-approved
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

    block_hash = _compute_block_hash(
        block_index, timestamp, invoice_id, document_bundle_sha256, previous_hash
    )

    new_block = {
        "block_index": block_index,
        "timestamp_utc": timestamp,
        "invoice_id": invoice_id,
        "document_bundle_sha256": document_bundle_sha256,
        "financing_partner": financing_partner,
        "advance_amount_usd": advance_amount_usd,
        "previous_block_hash": previous_hash,
        "block_hash": block_hash,
    }

    chain.append(new_block)
    _save_registry(chain)

    return new_block


def get_registry() -> list:
    """Return the full hash chain registry for display in the UI or audit reports."""
    return _load_registry()


def verify_chain_integrity() -> dict:
    """
    Verify the SHA-256 hash chain has not been tampered with.

    For each block, recomputes the expected hash and compares it to the stored hash.
    Also checks that each block's previous_block_hash matches its predecessor.

    Returns:
        Dict with 'is_valid' (bool), 'block_count', and 'first_violation' (if any).
    """
    chain = _load_registry()
    if not chain:
        return {"is_valid": True, "block_count": 0, "first_violation": None}

    for i, block in enumerate(chain):
        # Recompute expected hash
        expected = _compute_block_hash(
            block["block_index"],
            block["timestamp_utc"],
            block["invoice_id"],
            block["document_bundle_sha256"],
            block["previous_block_hash"],
        )
        if expected != block["block_hash"]:
            return {
                "is_valid": False,
                "block_count": len(chain),
                "first_violation": f"Block {i} hash mismatch — chain may have been tampered with.",
            }

        # Check previous hash linkage
        if i > 0 and block["previous_block_hash"] != chain[i - 1]["block_hash"]:
            return {
                "is_valid": False,
                "block_count": len(chain),
                "first_violation": f"Block {i} previous_block_hash does not match block {i-1}'s hash.",
            }

    return {"is_valid": True, "block_count": len(chain), "first_violation": None}
