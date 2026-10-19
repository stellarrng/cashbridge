"""Matching engine: bank reconciliation (3 tiers) and the 3-way match.

Pure Python, no I/O, no LLM. Money is compared in integer minor units or USD cents.

Reconciliation tiers
  1. Exact: the reference names one open invoice and the amount is identical.
  2. Tolerance: the reference names one open invoice and the gap is a bank fee
     (at most USD 50) or an FX difference.
  3. Subset-sum: some combination of the buyer's open invoices (at most 6) sums to
     the amount received within the fee tolerance. All solutions are returned; more
     than one means NEEDS_HUMAN.
"""

from __future__ import annotations

import re
from decimal import Decimal
from itertools import combinations
from typing import List, Optional, Sequence, Tuple

from config.settings import (
    INTERMEDIARY_FEE_TOLERANCE_USD,
    MAX_SUBSET_SIZE,
    THREE_WAY_AMOUNT_TOLERANCE,
)
from schemas.document_schemas import (
    BankTxn,
    BillOfLading,
    CommercialInvoice,
    MatchStatus,
    PurchaseOrder,
    ReconciliationResult,
    ReconStatus,
    ThreeWayResult,
)

_INVOICE_REF = re.compile(r"INV[-\s]?(\d+)", re.IGNORECASE)


def _fee_tolerance_cents() -> int:
    return int(INTERMEDIARY_FEE_TOLERANCE_USD * 100)


def _normalise_invoice_no(raw: str) -> str:
    match = _INVOICE_REF.search(raw)
    return f"INV-{match.group(1)}" if match else raw.strip().upper()


def referenced_invoice_numbers(reference: str) -> List[str]:
    """Return the invoice numbers named in a free-text bank reference, normalised."""
    return [f"INV-{digits}" for digits in _INVOICE_REF.findall(reference)]


def _gap_usd(cents: int) -> Decimal:
    return Decimal(cents) / 100


def _gap_within_tolerance(gap_cents: int, same_currency: bool) -> bool:
    """Bank fees only reduce what arrives; FX differences can go either way."""
    tolerance = _fee_tolerance_cents()
    if same_currency:
        return 0 <= gap_cents <= tolerance
    return abs(gap_cents) <= tolerance


def reconcile(txn: BankTxn, open_invoices: Sequence[CommercialInvoice]) -> ReconciliationResult:
    """Match one incoming transaction to the open invoices of the same buyer."""
    pool = [inv for inv in open_invoices if txn.buyer_id is None or inv.buyer_id == txn.buyer_id]
    by_no = {_normalise_invoice_no(inv.invoice_no): inv for inv in pool}
    received_cents = txn.amount.to_usd_cents()

    named = [no for no in referenced_invoice_numbers(txn.reference) if no in by_no]
    if len(named) == 1:
        invoice = by_no[named[0]]
        same_currency = invoice.currency == txn.amount.currency
        if same_currency and invoice.amount.minor_units == txn.amount.minor_units:
            return ReconciliationResult(
                txn_id=txn.txn_id,
                tier=1,
                matched_invoices=[invoice.invoice_no],
                gap=Decimal("0"),
                confidence=1.0,
                status=ReconStatus.BOOKED,
                reason="Exact match on invoice reference and amount",
            )
        gap_cents = invoice.amount.to_usd_cents() - received_cents
        if _gap_within_tolerance(gap_cents, same_currency):
            return _tolerance_result(txn.txn_id, 2, [invoice.invoice_no], gap_cents, same_currency)

    return _subset_sum(txn, pool, received_cents)


def _tolerance_result(
    txn_id: str, tier: int, invoice_nos: List[str], gap_cents: int, same_currency: bool
) -> ReconciliationResult:
    if same_currency:
        reason_code, confidence = "bank_fee", 1.0
        text = "Gap is within the intermediary bank fee tolerance"
    else:
        reason_code, confidence = "fx_difference", 0.9
        text = "Gap comes from FX conversion; proposed match needs accountant approval"
    if gap_cents == 0 and same_currency:
        reason_code = None
    return ReconciliationResult(
        txn_id=txn_id,
        tier=tier,
        matched_invoices=invoice_nos,
        gap=_gap_usd(gap_cents),
        gap_reason=reason_code,
        confidence=confidence,
        status=ReconStatus.BOOKED if confidence == 1.0 else ReconStatus.NEEDS_HUMAN,
        reason=text,
    )


def _subset_sum(
    txn: BankTxn, pool: Sequence[CommercialInvoice], received_cents: int
) -> ReconciliationResult:
    """Tier 3: find every combination of open invoices that explains the amount."""
    candidates = sorted(pool, key=lambda inv: inv.invoice_no)
    cents = {inv.invoice_no: inv.amount.to_usd_cents() for inv in candidates}
    solutions: List[Tuple[Tuple[str, ...], int, bool]] = []
    for size in range(1, min(MAX_SUBSET_SIZE, len(candidates)) + 1):
        for combo in combinations(candidates, size):
            total = sum(cents[inv.invoice_no] for inv in combo)
            same_currency = all(inv.currency == txn.amount.currency for inv in combo)
            gap = total - received_cents
            if _gap_within_tolerance(gap, same_currency):
                solutions.append((tuple(inv.invoice_no for inv in combo), gap, same_currency))

    if not solutions:
        return ReconciliationResult(
            txn_id=txn.txn_id,
            tier=None,
            confidence=0.0,
            status=ReconStatus.NEEDS_HUMAN,
            reason="No combination of open invoices matches within tolerance",
        )
    if len(solutions) > 1:
        return ReconciliationResult(
            txn_id=txn.txn_id,
            tier=3,
            confidence=0.5,
            status=ReconStatus.NEEDS_HUMAN,
            reason=f"{len(solutions)} combinations fit within tolerance; a human must choose",
            candidates=[list(nos) for nos, _, _ in solutions],
        )
    numbers, gap, same_currency = solutions[0]
    return _tolerance_result(txn.txn_id, 3, list(numbers), gap, same_currency)


def three_way_match(
    po: Optional[PurchaseOrder],
    invoice: CommercialInvoice,
    bl: Optional[BillOfLading],
) -> ThreeWayResult:
    """Check a purchase order, invoice and bill of lading against each other.

    BLOCKED: a document is missing or the parties/currency do not agree.
    FLAGGED: amount, quantity, package count or ports differ (differences listed).
    ELIGIBLE: everything agrees.
    """
    blocked: List[str] = []
    flagged: List[str] = []

    if po is None:
        blocked.append("Purchase order missing")
    if bl is None:
        blocked.append("Bill of lading missing")

    if po is not None:
        if po.currency != invoice.currency:
            blocked.append(f"Currency PO {po.currency.value} vs invoice {invoice.currency.value}")
        if po.buyer_id != invoice.buyer_id:
            blocked.append(f"Buyer PO {po.buyer_id} vs invoice {invoice.buyer_id}")
        if po.seller_tax_id != invoice.seller_tax_id:
            blocked.append(f"Seller tax ID PO {po.seller_tax_id} vs invoice {invoice.seller_tax_id}")
        if po.currency == invoice.currency:
            tolerance_minor = int(THREE_WAY_AMOUNT_TOLERANCE * (Decimal(10) ** invoice.amount.digits))
            if abs(po.amount.minor_units - invoice.amount.minor_units) > tolerance_minor:
                flagged.append(
                    f"PO amount {po.amount.display()} vs invoice {invoice.amount.display()}"
                )
        if po.quantity != invoice.quantity:
            flagged.append(f"PO quantity {po.quantity} vs invoice {invoice.quantity}")

    if bl is not None:
        if bl.buyer_id != invoice.buyer_id:
            blocked.append(f"Buyer B/L {bl.buyer_id} vs invoice {invoice.buyer_id}")
        if bl.quantity != invoice.quantity:
            flagged.append(f"B/L quantity {bl.quantity} vs invoice {invoice.quantity}")
        if bl.package_count != invoice.package_count:
            flagged.append(f"B/L packages {bl.package_count} vs invoice {invoice.package_count}")
        if bl.port_of_loading != invoice.port_of_loading:
            flagged.append(
                f"B/L port of loading {bl.port_of_loading} vs invoice {invoice.port_of_loading}"
            )
        if bl.port_of_discharge != invoice.port_of_discharge:
            flagged.append(
                f"B/L port of discharge {bl.port_of_discharge} vs invoice {invoice.port_of_discharge}"
            )

    if blocked:
        status = MatchStatus.BLOCKED
    elif flagged:
        status = MatchStatus.FLAGGED
    else:
        status = MatchStatus.ELIGIBLE
    return ThreeWayResult(invoice_no=invoice.invoice_no, status=status, differences=blocked + flagged)
