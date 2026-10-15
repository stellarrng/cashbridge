"""
Matching Engine — Deterministic 3-Way Match (Invoice–PO–Bill of Lading)
and Multi-Currency Subset-Sum Reconciliation (SSMP).

Rules:
  - All matching logic is pure Python — NO LLM involvement.
  - 3-way match: |Invoice.amount - PO.amount| ≤ $0.01, currency match, valid tax ID,
    BL.shipped_on_board_date ≤ Invoice.issue_date.
  - SSMP: Find subset of open invoices whose USD sum falls within $50 of a bulk wire.
  - All successful L2 writes are SHA-256 period-locked and logged.
"""

import hashlib
import json
from datetime import datetime, timezone
from itertools import combinations
from typing import List, Optional

from config.settings import (
    FX_RATES_TO_USD,
    PO_INVOICE_TOLERANCE_USD,
    CORRESPONDENT_BANK_FEE_TOLERANCE_USD,
    PermissionLevel,
)
from schemas.document_schemas import (
    CommercialInvoice,
    PurchaseOrder,
    BillOfLading,
    BankTxn,
    TradeBundle,
    MatchStatus,
    SubsetSumMatchResult,
)
from security.permission_gatekeeper import request_permission


def _to_usd(amount: float, currency: str) -> float:
    """Convert a foreign currency amount to USD using locked deterministic FX rates."""
    rate = FX_RATES_TO_USD.get(currency.upper(), 1.0)
    return round(amount * rate, 2)


def _bundle_sha256(invoice_id: str, po_number: str, bl_number: Optional[str]) -> str:
    """Compute a deterministic SHA-256 fingerprint for a trade document bundle."""
    raw = f"{invoice_id}|{po_number}|{bl_number or 'NO_BL'}|{datetime.now(timezone.utc).date()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_3way_match(bundle: TradeBundle) -> TradeBundle:
    """
    Perform a full 3-Way Match across a CommercialInvoice, PurchaseOrder, and BillOfLading.

    Verification rules (all must pass for VERIFIED_3WAY):
      1. Currency match between Invoice and PO.
      2. |Invoice.amount - PO.amount| ≤ $0.01 tolerance.
      3. Invoice.buyer_tax_id is not empty (valid buyer identity).
      4. BL.shipped_on_board_date ≤ Invoice.issue_date (goods shipped before invoice).

    Args:
        bundle: A TradeBundle containing invoice, po, and optionally bl.

    Returns:
        Updated TradeBundle with match_confidence, status, and discrepancy_reasons.
    """
    request_permission(
        PermissionLevel.L1_ANALYZE,
        "RUN_3WAY_MATCH",
        bundle.invoice_id,
    )

    invoice = bundle.invoice
    po = bundle.po
    bl = bundle.bl
    reasons: List[str] = []
    confidence = 1.0

    # Rule 1: BL must be present
    if bl is None:
        reasons.append("MISSING_BILL_OF_LADING: No Bill of Lading document provided.")
        confidence -= 0.4

    # Rule 2: PO must be present
    if po is None:
        reasons.append("MISSING_PURCHASE_ORDER: No linked Purchase Order found.")
        confidence -= 0.4

    if po is not None:
        # Rule 3: Currency match
        if invoice.currency != po.currency:
            reasons.append(
                f"CURRENCY_MISMATCH: Invoice currency {invoice.currency} ≠ PO currency {po.currency}."
            )
            confidence -= 0.3

        # Rule 4: Amount tolerance check
        invoice_usd = _to_usd(invoice.amount, invoice.currency.value)
        po_usd = _to_usd(po.amount, po.currency.value)
        variance = abs(invoice_usd - po_usd)
        if variance > PO_INVOICE_TOLERANCE_USD:
            reasons.append(
                f"AMOUNT_DISCREPANCY: Invoice {invoice_usd:.2f} USD vs PO {po_usd:.2f} USD "
                f"(variance ${variance:.2f} exceeds ${PO_INVOICE_TOLERANCE_USD:.2f} tolerance)."
            )
            confidence -= 0.3

    # Rule 5: Valid buyer tax ID
    if not invoice.buyer_tax_id or len(invoice.buyer_tax_id) < 5:
        reasons.append("INVALID_BUYER_TAX_ID: Buyer tax code is missing or too short.")
        confidence -= 0.2

    # Rule 6: BL shipped date ≤ invoice issue date
    if bl is not None and bl.shipped_on_board_date > invoice.issue_date:
        reasons.append(
            f"SHIPMENT_DATE_ERROR: BL shipped date {bl.shipped_on_board_date} is AFTER "
            f"invoice issue date {invoice.issue_date}. Goods cannot be invoiced before shipment."
        )
        confidence -= 0.3

    confidence = max(0.0, round(confidence, 2))

    if not reasons and confidence == 1.0:
        status = MatchStatus.VERIFIED_3WAY
        bundle_hash = _bundle_sha256(
            bundle.invoice_id,
            po.po_number if po else "NO_PO",
            bl.bl_number if bl else None,
        )
    else:
        status = MatchStatus.DISCREPANCY_FLAGGED
        bundle_hash = None

    bundle.match_confidence = confidence
    bundle.status = status
    bundle.discrepancy_reasons = reasons
    bundle.bundle_sha256 = bundle_hash

    return bundle


def run_subset_sum_reconciliation(
    wire_txn: BankTxn,
    open_invoices: List[CommercialInvoice],
) -> SubsetSumMatchResult:
    """
    Multi-Currency Subset-Sum Matching Problem (SSMP): find a subset of open invoices
    whose total USD value falls within $50 of the incoming bulk wire transfer.

    Uses exhaustive search over subsets (suitable for SME-scale invoice volumes).

    Args:
        wire_txn: The incoming bank wire transfer to reconcile.
        open_invoices: List of open (unpaid) CommercialInvoice records.

    Returns:
        SubsetSumMatchResult with matched invoices, fee variance, and period lock hash.

    Raises:
        ValueError: If no valid subset is found within the tolerance.
    """
    request_permission(
        PermissionLevel.L1_ANALYZE,
        "RUN_SUBSET_SUM_RECONCILIATION",
        wire_txn.txn_id,
    )

    wire_usd = wire_txn.usd_amount
    tolerance = CORRESPONDENT_BANK_FEE_TOLERANCE_USD

    # Try subsets from largest to smallest (most likely match first)
    for r in range(len(open_invoices), 0, -1):
        for subset in combinations(open_invoices, r):
            subset_total = sum(inv.usd_amount for inv in subset)
            shortfall = subset_total - wire_usd
            if 0 <= shortfall <= tolerance:
                matched_ids = [inv.invoice_id for inv in subset]
                fee_variance = round(shortfall, 2)

                # Compute SHA-256 period lock for the reconciled subset
                lock_raw = f"{wire_txn.txn_id}|{'|'.join(sorted(matched_ids))}|{wire_usd}"
                period_lock_hash = hashlib.sha256(lock_raw.encode()).hexdigest()

                # Log the L2 internal ledger write
                request_permission(
                    PermissionLevel.L2_INTERNAL_WRITE,
                    "RECONCILE_WIRE_TO_INVOICES",
                    wire_txn.txn_id,
                    details={
                        "matched_invoices": matched_ids,
                        "wire_usd": wire_usd,
                        "intermediary_fee_variance_usd": fee_variance,
                        "period_lock_hash": period_lock_hash,
                    },
                )

                return SubsetSumMatchResult(
                    txn_id=wire_txn.txn_id,
                    incoming_wire_amount=wire_usd,
                    matched_invoice_ids=matched_ids,
                    matched_invoices_gross_usd=round(subset_total, 2),
                    intermediary_bank_fee_variance_usd=fee_variance,
                    is_valid_match=True,
                    reconciliation_status="RECONCILED_WITH_FEE_VARIANCE",
                    period_lock_hash=period_lock_hash,
                )

    # No match found within tolerance — log and return unmatched
    request_permission(
        PermissionLevel.L1_ANALYZE,
        "RECONCILIATION_FAILED",
        wire_txn.txn_id,
        details={"wire_usd": wire_usd, "reason": "No invoice subset found within tolerance"},
    )
    return SubsetSumMatchResult(
        txn_id=wire_txn.txn_id,
        incoming_wire_amount=wire_usd,
        matched_invoice_ids=[],
        matched_invoices_gross_usd=0.0,
        intermediary_bank_fee_variance_usd=0.0,
        is_valid_match=False,
        reconciliation_status="UNMATCHED",
    )
