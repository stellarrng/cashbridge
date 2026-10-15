"""
Matching Engine — 3-way match (Invoice/PO/B-L) and multi-currency subset-sum
reconciliation.

FOUR DEFECTS FIXED
------------------
1. THE BUNDLE HASH WAS NOT A FINGERPRINT OF THE BUNDLE.

       raw = f"{invoice_id}|{po_number}|{bl_number}|{datetime.now().date()}"

   It covered three identifiers and today's date. Changing the invoice amount,
   the buyer, the quantities or the dates produced the SAME hash, so the
   "tamper-evident" bundle hash detected no tampering with any figure. It also
   changed by itself at midnight, so the same bundle hashed differently on two
   days and the anti-double-financing registry could be defeated by waiting.
   The hash now covers the content that matters and is time-independent.

2. TOLERANCE WAS APPLIED AFTER USD CONVERSION. A $0.01 tolerance on a JPY
   invoice converted at 0.0067 permits a ~1.5 JPY discrepancy; the check is now
   done in the invoice's own currency before conversion.

3. AMBIGUOUS RECONCILIATION WAS POSTED AS FACT. The subset-sum search returned
   the first subset it found, searching LARGEST subsets first — biased towards
   matching as many invoices as possible, which is the opposite of what a
   reconciler wants. If two different sets of invoices both fit the wire, the
   engine picked one and wrote it to the ledger. It now enumerates all fits,
   prefers the smallest, and returns REVIEW_REQUIRED when more than one fits.

4. EXHAUSTIVE SEARCH WITH NO GUARD. 2^n subsets with no bound on n. Now capped,
   with an explicit refusal rather than a hang.

A VERIFIED_3WAY RESULT IS NOT PROOF THE TRADE IS REAL. Documents forged by one
party agree with one another. What this engine establishes is internal
consistency; what it cannot establish is listed in `checks_not_performed` on
every bundle it returns.

ALL MATCHING IS PURE PYTHON. No LLM makes any matching decision in this module.
"""

import hashlib
import json
from datetime import datetime, timezone
from itertools import combinations
from typing import List, Optional, Tuple

from config.settings import (
    FX_RATES_TO_USD,
    FX_RATE_DATE,
    PO_INVOICE_TOLERANCE_NATIVE,
    PO_INVOICE_TOLERANCE_DEFAULT,
    CORRESPONDENT_BANK_FEE_TOLERANCE_USD,
    SSMP_MAX_OPEN_INVOICES,
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


# Verifications this build cannot perform. Attached to every bundle so that a
# pass is never read as more assurance than it carries.
CHECKS_NOT_PERFORMED = [
    "Buyer existence and standing not verified against any company registry",
    "Invoice not confirmed against the tax authority's e-invoice system",
    "Bill of lading not verified with the carrier — a B/L number is not "
    "authenticated by being well-formed",
    "No check for an existing dispute, cancellation or credit note on the order",
    "No check whether this invoice has been pledged to a funder outside "
    "CashBridge — the registry only sees what passes through this system",
    "Document authenticity not established; a consistent set of forged "
    "documents passes every check above",
]


def _to_usd(amount: float, currency: str) -> float:
    """Convert to USD at the frozen sandbox rate. Rate date is logged, not implied."""
    rate = FX_RATES_TO_USD.get(currency.upper())
    if rate is None:
        raise ValueError(
            f"No FX rate configured for {currency}. Refusing to assume 1.0 — "
            f"an unconverted foreign amount silently corrupts every downstream total."
        )
    return round(amount * rate, 2)


def _native_tolerance(currency: str) -> float:
    return PO_INVOICE_TOLERANCE_NATIVE.get(currency.upper(), PO_INVOICE_TOLERANCE_DEFAULT)


def compute_bundle_hash(
    invoice: CommercialInvoice,
    po: Optional[PurchaseOrder],
    bl: Optional[BillOfLading],
) -> str:
    """
    Content fingerprint of a trade document bundle.

    Covers every field a fraudster would need to change — amounts, currencies,
    parties, dates, document numbers — so that an altered bundle produces a
    different hash. Deliberately excludes the current date, so the same bundle
    always hashes the same and the anti-double-financing registry cannot be
    defeated by resubmitting tomorrow.

    Args:
        invoice: The commercial invoice.
        po: Linked purchase order, if present.
        bl: Linked bill of lading, if present.

    Returns:
        Hex SHA-256 digest.
    """
    payload = {
        "invoice": {
            "id": invoice.invoice_id,
            "po_reference": invoice.po_reference,
            "buyer_name": invoice.buyer_name,
            "buyer_tax_id": invoice.buyer_tax_id,
            "issue_date": str(invoice.issue_date),
            "due_date": str(invoice.due_date),
            "currency": invoice.currency.value,
            "amount": f"{invoice.amount:.2f}",
            "items": [
                {
                    "description": i.description,
                    "quantity": f"{i.quantity:.4f}",
                    "unit_price": f"{i.unit_price:.4f}",
                    "amount": f"{i.amount:.2f}",
                }
                for i in invoice.items
            ],
        },
        "po": None
        if po is None
        else {
            "number": po.po_number,
            "buyer_name": po.buyer_name,
            "buyer_tax_id": po.buyer_tax_id,
            "issue_date": str(po.issue_date),
            "currency": po.currency.value,
            "amount": f"{po.amount:.2f}",
            "payment_terms": po.payment_terms,
            "items": [
                {
                    "description": i.description,
                    "quantity": f"{i.quantity:.4f}",
                    "unit_price": f"{i.unit_price:.4f}",
                    "total": f"{i.total:.2f}",
                }
                for i in po.items
            ],
        },
        "bl": None
        if bl is None
        else {
            "number": bl.bl_number,
            "carrier": bl.carrier,
            "vessel": bl.vessel_name,
            "voyage": bl.voyage_number,
            "pol": bl.port_of_loading,
            "pod": bl.port_of_discharge,
            "shipped_on_board": str(bl.shipped_on_board_date),
            "containers": sorted(bl.container_ids),
            "goods": bl.goods_description,
            "gross_weight_kg": f"{bl.gross_weight_kg:.3f}",
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_3way_match(bundle: TradeBundle) -> TradeBundle:
    """
    Check an invoice, its purchase order and its bill of lading for consistency.

    Outcomes:
        VERIFIED_3WAY       every check passed and nothing needs a human
        DISCREPANCY_FLAGGED a check failed on the evidence present
        REVIEW_REQUIRED     a document is missing, so the check could not be
                            performed at all

    The distinction in the last two matters: "the amounts disagree" is a
    finding, while "there is no purchase order" is an absence of evidence. The
    previous version collapsed both into DISCREPANCY_FLAGGED and deducted
    confidence as if a missing document were a detected defect.

    Args:
        bundle: TradeBundle with invoice and optionally po and bl.

    Returns:
        The bundle with status, confidence, reasons and a content hash
        (set only when the bundle verifies).
    """
    request_permission(PermissionLevel.L1_ANALYZE, "RUN_3WAY_MATCH", bundle.invoice_id)

    invoice = bundle.invoice
    po = bundle.po
    bl = bundle.bl

    discrepancies: List[str] = []
    review: List[str] = []
    performed: List[str] = []
    confidence = 1.0

    # ── Evidence availability ─────────────────────────────────────────────
    if bl is None:
        review.append("MISSING_BILL_OF_LADING: shipment cannot be evidenced.")
    if po is None:
        review.append("MISSING_PURCHASE_ORDER: the order cannot be evidenced.")

    # ── Checks against the purchase order ─────────────────────────────────
    if po is not None:
        performed.append("Invoice/PO currency agreement")
        if invoice.currency != po.currency:
            discrepancies.append(
                f"CURRENCY_MISMATCH: invoice {invoice.currency.value} vs PO "
                f"{po.currency.value}."
            )
            confidence -= 0.3

        performed.append("Invoice/PO amount agreement (native currency)")
        if invoice.currency == po.currency:
            tolerance = _native_tolerance(invoice.currency.value)
            variance = abs(invoice.amount - po.amount)
            if variance > tolerance:
                discrepancies.append(
                    f"AMOUNT_DISCREPANCY: invoice {invoice.amount:,.2f} vs PO "
                    f"{po.amount:,.2f} {invoice.currency.value} (variance "
                    f"{variance:,.2f} exceeds {tolerance:,.2f} tolerance)."
                )
                confidence -= 0.3
        else:
            review.append(
                "AMOUNT_NOT_COMPARABLE: invoice and PO are in different "
                "currencies; comparing them requires an agreed contractual rate, "
                "not a system rate."
            )

        performed.append("Buyer identity consistency between invoice and PO")
        if invoice.buyer_tax_id and po.buyer_tax_id and invoice.buyer_tax_id != po.buyer_tax_id:
            discrepancies.append(
                f"BUYER_MISMATCH: invoice buyer tax ID {invoice.buyer_tax_id} does "
                f"not match PO buyer tax ID {po.buyer_tax_id}."
            )
            confidence -= 0.3

        performed.append("Invoice references the purchase order")
        if invoice.po_reference and invoice.po_reference != po.po_number:
            discrepancies.append(
                f"PO_REFERENCE_MISMATCH: invoice cites {invoice.po_reference}, "
                f"bundle contains PO {po.po_number}."
            )
            confidence -= 0.2

    # ── Checks on the invoice itself ──────────────────────────────────────
    performed.append("Buyer tax ID present and plausibly formed")
    if not invoice.buyer_tax_id or len(invoice.buyer_tax_id) < 5:
        discrepancies.append("INVALID_BUYER_TAX_ID: missing or too short.")
        confidence -= 0.2

    performed.append("Invoice due date is after its issue date")
    if invoice.due_date < invoice.issue_date:
        discrepancies.append(
            f"DATE_ORDER_ERROR: due date {invoice.due_date} precedes issue date "
            f"{invoice.issue_date}."
        )
        confidence -= 0.2

    performed.append("Line items sum to the invoice total")
    if invoice.items:
        line_total = round(sum(i.amount for i in invoice.items), 2)
        tolerance = _native_tolerance(invoice.currency.value)
        if abs(line_total - invoice.amount) > tolerance:
            discrepancies.append(
                f"LINE_ITEM_SUM_MISMATCH: lines total {line_total:,.2f} but the "
                f"invoice states {invoice.amount:,.2f} {invoice.currency.value}."
            )
            confidence -= 0.3

    # ── Checks against the bill of lading ─────────────────────────────────
    if bl is not None:
        performed.append("Shipment date is not after the invoice date")
        if bl.shipped_on_board_date > invoice.issue_date:
            discrepancies.append(
                f"SHIPMENT_DATE_ERROR: B/L shipped {bl.shipped_on_board_date} is "
                f"after invoice issue date {invoice.issue_date}."
            )
            confidence -= 0.3

    confidence = max(0.0, round(confidence, 2))

    # ── Conclude ──────────────────────────────────────────────────────────
    if discrepancies:
        status = MatchStatus.DISCREPANCY_FLAGGED
        bundle_hash = None
    elif review:
        status = MatchStatus.REVIEW_REQUIRED
        bundle_hash = None
    else:
        status = MatchStatus.VERIFIED_3WAY
        bundle_hash = compute_bundle_hash(invoice, po, bl)

    bundle.match_confidence = confidence
    bundle.status = status
    bundle.discrepancy_reasons = discrepancies
    bundle.review_reasons = review
    bundle.bundle_sha256 = bundle_hash
    bundle.checks_performed = performed
    bundle.checks_not_performed = list(CHECKS_NOT_PERFORMED)
    return bundle


def _find_all_subsets(
    wire_usd: float, invoices: List[CommercialInvoice], tolerance: float
) -> List[Tuple[List[CommercialInvoice], float]]:
    """
    Every invoice subset whose total sits within the fee tolerance of the wire.

    A bulk wire arrives net of correspondent bank charges, so the invoice total
    is expected to be at or slightly above the amount received. A wire LARGER
    than the invoice total is not a fee variance — it is an overpayment or a
    wrong match, and is deliberately not accepted here.
    """
    fits: List[Tuple[List[CommercialInvoice], float]] = []
    n = len(invoices)
    for r in range(1, n + 1):
        for subset in combinations(invoices, r):
            total = round(sum(inv.usd_amount for inv in subset), 2)
            variance = round(total - wire_usd, 2)
            if 0 <= variance <= tolerance:
                fits.append((list(subset), variance))
    return fits


def run_subset_sum_reconciliation(
    wire_txn: BankTxn,
    open_invoices: List[CommercialInvoice],
    auto_post: bool = True,
) -> SubsetSumMatchResult:
    """
    Reconcile a bulk incoming wire against open invoices.

    Enumerates every subset that fits within the correspondent-fee tolerance.
    If exactly one fits, it is posted. If several fit, the result is
    REVIEW_REQUIRED with the alternatives listed — writing one of several
    equally valid allocations to the ledger is how reconciliation errors become
    permanent.

    Args:
        wire_txn: Incoming wire to reconcile.
        open_invoices: Unpaid invoices that could account for it.
        auto_post: Write an L2 ledger entry on an unambiguous single match.

    Returns:
        SubsetSumMatchResult, with `requires_human_review` set when the
        allocation is ambiguous or no subset fits.

    Raises:
        ValueError: If the candidate set is too large for exhaustive search.
    """
    request_permission(
        PermissionLevel.L1_ANALYZE, "RUN_SUBSET_SUM_RECONCILIATION", wire_txn.txn_id
    )

    if len(open_invoices) > SSMP_MAX_OPEN_INVOICES:
        raise ValueError(
            f"{len(open_invoices)} open invoices exceeds the exhaustive-search "
            f"limit of {SSMP_MAX_OPEN_INVOICES} (2^n subsets). Narrow the "
            f"candidate set by buyer or date before reconciling, rather than "
            f"silently searching a truncated space."
        )

    wire_usd = wire_txn.usd_amount
    tolerance = CORRESPONDENT_BANK_FEE_TOLERANCE_USD
    fits = _find_all_subsets(wire_usd, open_invoices, tolerance)

    # ── Nothing fits ──────────────────────────────────────────────────────
    if not fits:
        request_permission(
            PermissionLevel.L1_ANALYZE,
            "RECONCILIATION_UNMATCHED",
            wire_txn.txn_id,
            details={"wire_usd": wire_usd, "candidates": len(open_invoices)},
        )
        return SubsetSumMatchResult(
            txn_id=wire_txn.txn_id,
            incoming_wire_amount=wire_usd,
            matched_invoice_ids=[],
            matched_invoices_gross_usd=0.0,
            intermediary_bank_fee_variance_usd=0.0,
            is_valid_match=False,
            reconciliation_status="UNMATCHED",
            candidate_match_count=0,
            requires_human_review=True,
            review_reason=(
                f"No subset of {len(open_invoices)} open invoices sums to within "
                f"${tolerance:.2f} of the ${wire_usd:,.2f} received. The payment "
                f"may be partial, cover an invoice not in the system, or include "
                f"a deduction larger than the fee tolerance."
            ),
        )

    # Prefer the smallest subset, then the smallest fee variance: a wire is
    # far more likely to settle one invoice than an arbitrary basket of six
    # that happens to sum to the same figure.
    fits.sort(key=lambda f: (len(f[0]), f[1]))
    best_subset, best_variance = fits[0]
    matched_ids = [inv.invoice_id for inv in best_subset]

    # ── Ambiguous: more than one allocation fits ──────────────────────────
    if len(fits) > 1:
        alternatives = [[i.invoice_id for i in s] for s, _ in fits[:5]]
        request_permission(
            PermissionLevel.L1_ANALYZE,
            "RECONCILIATION_AMBIGUOUS",
            wire_txn.txn_id,
            details={"wire_usd": wire_usd, "candidate_count": len(fits)},
        )
        return SubsetSumMatchResult(
            txn_id=wire_txn.txn_id,
            incoming_wire_amount=wire_usd,
            matched_invoice_ids=matched_ids,
            matched_invoices_gross_usd=round(sum(i.usd_amount for i in best_subset), 2),
            intermediary_bank_fee_variance_usd=best_variance,
            is_valid_match=False,
            reconciliation_status="REVIEW_REQUIRED",
            candidate_match_count=len(fits),
            alternative_matches=alternatives,
            requires_human_review=True,
            review_reason=(
                f"{len(fits)} different invoice combinations fit this wire within "
                f"tolerance. The allocation is not determined by the amount alone; "
                f"a human must pick using the remittance advice or buyer "
                f"confirmation. Suggested (smallest) allocation shown, NOT posted."
            ),
        )

    # ── Exactly one allocation fits ───────────────────────────────────────
    subset_total = round(sum(i.usd_amount for i in best_subset), 2)
    lock_raw = f"{wire_txn.txn_id}|{'|'.join(sorted(matched_ids))}|{wire_usd:.2f}|{FX_RATE_DATE}"
    period_lock_hash = hashlib.sha256(lock_raw.encode()).hexdigest()

    if auto_post:
        request_permission(
            PermissionLevel.L2_INTERNAL_WRITE,
            "RECONCILE_WIRE_TO_INVOICES",
            wire_txn.txn_id,
            details={
                "matched_invoices": matched_ids,
                "wire_usd": wire_usd,
                "intermediary_fee_variance_usd": best_variance,
                "period_lock_hash": period_lock_hash,
                "fx_rate_date": FX_RATE_DATE,
            },
        )

    status = (
        "RECONCILED_WITH_FEE_VARIANCE" if best_variance > 0 else "RECONCILED_EXACT"
    )
    return SubsetSumMatchResult(
        txn_id=wire_txn.txn_id,
        incoming_wire_amount=wire_usd,
        matched_invoice_ids=matched_ids,
        matched_invoices_gross_usd=subset_total,
        intermediary_bank_fee_variance_usd=best_variance,
        is_valid_match=True,
        reconciliation_status=status,
        candidate_match_count=1,
        requires_human_review=False,
        period_lock_hash=period_lock_hash,
    )
