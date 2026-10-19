"""Invoice registry: a tamper-evident, hash-chained record of financed invoices.

Each financed invoice becomes one block. A block's hash covers its own fields and the
previous block's hash, so editing or removing an earlier block breaks every later one.
The registry key is canonical (built from invoice fields), so re-scanning or re-saving
the PDF cannot create a second key for the same invoice.

Honest limit: a registry held inside one SME's installation cannot stop the same invoice
being financed at a second lender. In production it must be shared, for example run by a
lender consortium or anchored to the e-invoice authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from schemas.document_schemas import CommercialInvoice

GENESIS_HASH = "0" * 64
Clock = Callable[[], datetime]


class DoubleFinancingBlocked(Exception):
    """Raised when an invoice that is already in the registry is submitted again."""


def invoice_key(invoice: CommercialInvoice) -> str:
    """Canonical key: SHA-256(seller_tax_id | invoice_no | buyer_id | currency | minor units | issue_date)."""
    parts = [
        invoice.seller_tax_id.strip().upper(),
        invoice.invoice_no.strip().upper(),
        invoice.buyer_id.strip().upper(),
        invoice.currency.value.upper(),
        str(invoice.amount.minor_units),
        invoice.issue_date.isoformat(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _block_hash(block: Dict[str, Any]) -> str:
    body = {k: v for k, v in block.items() if k != "block_hash"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvoiceRegistry:
    """File-backed registry. The path is passed in; nothing is read from globals."""

    def __init__(self, path: Path, clock: Clock = _utc_now) -> None:
        self.path = Path(path)
        self._clock = clock

    def blocks(self) -> List[Dict[str, Any]]:
        """All blocks in order (empty list if the file does not exist yet)."""
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def is_registered(self, invoice: CommercialInvoice) -> bool:
        """True if this invoice's canonical key is already in the registry."""
        key = invoice_key(invoice)
        return any(block["invoice_key"] == key for block in self.blocks())

    def register(
        self, invoice: CommercialInvoice, document_bundle_sha256: str, lender_ref: str
    ) -> Dict[str, Any]:
        """Append a block for ``invoice`` or raise DoubleFinancingBlocked."""
        key = invoice_key(invoice)
        chain = self.blocks()
        if any(block["invoice_key"] == key for block in chain):
            raise DoubleFinancingBlocked(
                f"{invoice.invoice_no} is already registered and cannot be financed twice"
            )
        block: Dict[str, Any] = {
            "block_index": len(chain),
            "timestamp_utc": self._clock().astimezone(timezone.utc).isoformat(),
            "invoice_key": key,
            "document_bundle_sha256": document_bundle_sha256,
            "lender_ref": lender_ref,
            "previous_block_hash": chain[-1]["block_hash"] if chain else GENESIS_HASH,
        }
        block["block_hash"] = _block_hash(block)
        chain.append(block)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(chain, indent=2), encoding="utf-8")
        return block

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Return (ok, first_broken_index). Detects edited, reordered or removed blocks."""
        previous = GENESIS_HASH
        for position, block in enumerate(self.blocks()):
            if (
                block.get("block_index") != position
                or block.get("previous_block_hash") != previous
                or block.get("block_hash") != _block_hash(block)
            ):
                return False, position
            previous = block["block_hash"]
        return True, None

    def head_hash(self) -> str:
        """Hash of the newest block (the value to anchor outside this machine)."""
        chain = self.blocks()
        return chain[-1]["block_hash"] if chain else GENESIS_HASH
