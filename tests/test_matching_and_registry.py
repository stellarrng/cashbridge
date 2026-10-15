"""
Document verification, reconciliation and the anti-double-financing registry.
"""

from datetime import date

import pytest

from schemas.document_schemas import (
    BankTxn,
    BillOfLading,
    CommercialInvoice,
    Currency,
    InvoiceLineItem,
    MatchStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    TradeBundle,
)
from core.matching_engine import (
    run_3way_match,
    run_subset_sum_reconciliation,
    compute_bundle_hash,
)
from core.cryptographic_registry import (
    register_invoice,
    check_registration,
    find_by_bundle_hash,
    verify_chain_integrity,
    get_chain_head,
    DoubleFinancingError,
    RegistryConflictError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_invoice(
    invoice_id="INV-2026-103",
    amount=65_000.0,
    currency=Currency.USD,
    usd_amount=None,
    buyer_tax_id="US-5566778899",
    po_ref="PO-4471",
    issue=date(2026, 9, 1),
    due=date(2026, 10, 16),
    items=None,
):
    return CommercialInvoice(
        invoice_id=invoice_id,
        po_reference=po_ref,
        buyer_name="Nordic Home Retail",
        buyer_tax_id=buyer_tax_id,
        issue_date=issue,
        due_date=due,
        currency=currency,
        amount=amount,
        usd_amount=usd_amount if usd_amount is not None else amount,
        items=items if items is not None else [
            InvoiceLineItem(
                description="Oak dining chairs",
                quantity=1200,
                unit_price=54.1666667,
                amount=amount,
            )
        ],
    )


def make_po(amount=65_000.0, currency=Currency.USD, buyer_tax_id="US-5566778899"):
    return PurchaseOrder(
        po_number="PO-4471",
        buyer_name="Nordic Home Retail",
        buyer_tax_id=buyer_tax_id,
        issue_date=date(2026, 8, 20),
        currency=currency,
        amount=amount,
        items=[
            PurchaseOrderItem(
                description="Oak dining chairs",
                quantity=1200,
                unit_price=54.1666667,
                total=amount,
            )
        ],
    )


def make_bl(shipped=date(2026, 8, 28)):
    return BillOfLading(
        bl_number="MAEU-7781234",
        carrier="Maersk",
        vessel_name="MV Horizon",
        voyage_number="V-204E",
        port_of_loading="Haiphong",
        port_of_discharge="Long Beach",
        shipped_on_board_date=shipped,
        container_ids=["MSCU1234567", "MSCU7654321"],
        goods_description="Oak dining chairs, knocked down",
        gross_weight_kg=18420.5,
    )


# Sentinel so that an explicit `po=None` means "no purchase order" rather than
# "use the default one".
_DEFAULT = object()


def make_bundle(invoice=None, po=_DEFAULT, bl=_DEFAULT):
    invoice = invoice or make_invoice()
    return TradeBundle(
        bundle_id="BND-1",
        invoice_id=invoice.invoice_id,
        invoice=invoice,
        po=make_po() if po is _DEFAULT else po,
        bl=make_bl() if bl is _DEFAULT else bl,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3-way match
# ─────────────────────────────────────────────────────────────────────────────

def test_consistent_bundle_verifies_and_gets_a_hash():
    result = run_3way_match(make_bundle())
    assert result.status == MatchStatus.VERIFIED_3WAY
    assert result.match_confidence == 1.0
    assert result.bundle_sha256 and len(result.bundle_sha256) == 64


def test_verified_bundle_discloses_what_was_not_checked():
    """
    A VERIFIED_3WAY result means the documents agree with each other. It is not
    evidence the trade happened — documents forged by one party agree perfectly.
    Every bundle carries that limitation so a pass is not oversold.
    """
    result = run_3way_match(make_bundle())
    assert result.checks_performed
    assert result.checks_not_performed
    assert any("forged" in c for c in result.checks_not_performed)


def test_amount_mismatch_is_flagged():
    bundle = make_bundle(po=make_po(amount=64_000.0))
    result = run_3way_match(bundle)
    assert result.status == MatchStatus.DISCREPANCY_FLAGGED
    assert any("AMOUNT_DISCREPANCY" in r for r in result.discrepancy_reasons)


def test_missing_document_is_review_required_not_a_discrepancy():
    """
    "The amounts disagree" is a finding; "there is no purchase order" is an
    absence of evidence. The old engine collapsed both into
    DISCREPANCY_FLAGGED and deducted confidence as if a missing document were a
    detected defect.
    """
    result = run_3way_match(make_bundle(po=None))
    assert result.status == MatchStatus.REVIEW_REQUIRED
    assert result.discrepancy_reasons == []
    assert any("MISSING_PURCHASE_ORDER" in r for r in result.review_reasons)


def test_buyer_identity_mismatch_between_invoice_and_po_is_caught():
    bundle = make_bundle(po=make_po(buyer_tax_id="US-0000000000"))
    result = run_3way_match(bundle)
    assert result.status == MatchStatus.DISCREPANCY_FLAGGED
    assert any("BUYER_MISMATCH" in r for r in result.discrepancy_reasons)


def test_line_items_must_sum_to_the_invoice_total():
    invoice = make_invoice(
        items=[InvoiceLineItem(description="Chairs", quantity=1, unit_price=1.0, amount=50_000.0)]
    )
    result = run_3way_match(make_bundle(invoice=invoice))
    assert any("LINE_ITEM_SUM_MISMATCH" in r for r in result.discrepancy_reasons)


def test_shipment_after_invoice_date_is_caught():
    result = run_3way_match(make_bundle(bl=make_bl(shipped=date(2026, 9, 20))))
    assert any("SHIPMENT_DATE_ERROR" in r for r in result.discrepancy_reasons)


def test_jpy_tolerance_is_applied_in_the_native_currency():
    """
    REGRESSION. The old check converted to USD first and compared against a
    $0.01 tolerance. At a JPY rate of 0.0067 that permits roughly a 1.5 JPY
    discrepancy to pass as an exact match.
    """
    invoice = make_invoice(
        invoice_id="INV-2026-JPY",
        amount=3_680_000.0,
        currency=Currency.JPY,
        usd_amount=24_656.0,
        items=[InvoiceLineItem(description="Panels", quantity=1, unit_price=3_680_000.0, amount=3_680_000.0)],
    )
    # 1.5 JPY apart: under the old USD-converted tolerance this verified.
    po = make_po(amount=3_680_001.5, currency=Currency.JPY)
    result = run_3way_match(make_bundle(invoice=invoice, po=po))
    assert result.status == MatchStatus.DISCREPANCY_FLAGGED


# ─────────────────────────────────────────────────────────────────────────────
# Bundle hash
# ─────────────────────────────────────────────────────────────────────────────

def test_bundle_hash_is_stable_across_calls():
    """
    REGRESSION. The old hash preimage included `datetime.now().date()`, so the
    same bundle hashed differently on two different days — breaking both the
    tamper-evidence claim and the duplicate check, which could be defeated by
    resubmitting tomorrow.
    """
    invoice, po, bl = make_invoice(), make_po(), make_bl()
    assert compute_bundle_hash(invoice, po, bl) == compute_bundle_hash(invoice, po, bl)


def test_changing_the_invoice_amount_changes_the_bundle_hash():
    """
    REGRESSION. The old preimage was `invoice_id|po_number|bl_number|today`, so
    altering the amount, the buyer or the quantities left the hash unchanged —
    a "tamper-evident" hash that detected no tampering with any figure.
    """
    base = compute_bundle_hash(make_invoice(), make_po(), make_bl())
    altered = compute_bundle_hash(
        make_invoice(
            amount=95_000.0,
            items=[InvoiceLineItem(description="Oak dining chairs", quantity=1200, unit_price=79.17, amount=95_000.0)],
        ),
        make_po(amount=95_000.0),
        make_bl(),
    )
    assert base != altered


@pytest.mark.parametrize(
    "mutate",
    [
        lambda: compute_bundle_hash(make_invoice(buyer_tax_id="US-9999999999"), make_po(), make_bl()),
        lambda: compute_bundle_hash(make_invoice(issue=date(2026, 9, 5)), make_po(), make_bl()),
        lambda: compute_bundle_hash(make_invoice(), make_po(), make_bl(shipped=date(2026, 8, 1))),
    ],
)
def test_any_material_field_change_changes_the_hash(mutate):
    assert mutate() != compute_bundle_hash(make_invoice(), make_po(), make_bl())


# ─────────────────────────────────────────────────────────────────────────────
# Subset-sum reconciliation
# ─────────────────────────────────────────────────────────────────────────────

def wire(amount, txn_id="TXN-9901"):
    return BankTxn(
        txn_id=txn_id,
        txn_date=date(2026, 10, 16),
        amount=amount,
        currency=Currency.USD,
        usd_amount=amount,
        sender_name="Nordic Home Retail",
        sender_account_masked="****4471",
        sender_swift_masked="[SWIFT_REDACTED]",
        reference_memo="Settlement",
    )


def inv(invoice_id, usd):
    return make_invoice(invoice_id=invoice_id, amount=usd, usd_amount=usd,
                        items=[InvoiceLineItem(description="x", quantity=1, unit_price=usd, amount=usd)])


def test_single_invoice_reconciles_with_a_fee_variance():
    """A $35 correspondent fee deduction is within tolerance."""
    result = run_subset_sum_reconciliation(
        wire(64_965.0), [inv("INV-A", 65_000.0), inv("INV-B", 12_000.0)]
    )
    assert result.is_valid_match is True
    assert result.matched_invoice_ids == ["INV-A"]
    assert result.intermediary_bank_fee_variance_usd == pytest.approx(35.0)
    assert result.requires_human_review is False


def test_smallest_subset_is_preferred_over_a_larger_coincidental_one():
    """
    REGRESSION. The old search iterated `range(len(invoices), 0, -1)` — largest
    subsets first — so it preferred to match as many invoices as possible. A
    wire settling one invoice was reported as settling six that happened to sum
    to the same figure.
    """
    invoices = [inv("INV-BIG", 30_000.0)] + [
        inv(f"INV-S{i}", 10_000.0) for i in range(3)
    ]
    result = run_subset_sum_reconciliation(wire(30_000.0), invoices)
    assert result.matched_invoice_ids == ["INV-BIG"]


def test_ambiguous_allocation_is_not_posted():
    """
    REGRESSION. Two different invoices of equal value both fit the wire. The
    old engine wrote whichever it found first to the ledger; the allocation is
    not determined by the amount alone and must go to a human.
    """
    result = run_subset_sum_reconciliation(
        wire(20_000.0), [inv("INV-X", 20_000.0), inv("INV-Y", 20_000.0)]
    )
    assert result.is_valid_match is False
    assert result.reconciliation_status == "REVIEW_REQUIRED"
    assert result.requires_human_review is True
    assert result.candidate_match_count >= 2
    assert len(result.alternative_matches) >= 2


def test_overpayment_is_not_treated_as_a_fee_variance():
    """
    A wire LARGER than the invoice total is an overpayment or a wrong match,
    not a correspondent fee. It must not reconcile.
    """
    result = run_subset_sum_reconciliation(wire(65_040.0), [inv("INV-A", 65_000.0)])
    assert result.is_valid_match is False
    assert result.requires_human_review is True


def test_variance_beyond_tolerance_is_unmatched_with_a_reason():
    result = run_subset_sum_reconciliation(wire(60_000.0), [inv("INV-A", 65_000.0)])
    assert result.reconciliation_status == "UNMATCHED"
    assert result.requires_human_review is True
    assert "partial" in result.review_reason


def test_oversized_candidate_set_is_refused_not_silently_truncated():
    """2^n exhaustive search needs a bound, and the bound must be visible."""
    invoices = [inv(f"INV-{i}", 1_000.0 + i) for i in range(25)]
    with pytest.raises(ValueError, match="exhaustive-search"):
        run_subset_sum_reconciliation(wire(1_000.0), invoices)


# ─────────────────────────────────────────────────────────────────────────────
# Anti-double-financing registry
# ─────────────────────────────────────────────────────────────────────────────

HASH_A = "a" * 64
HASH_B = "b" * 64


def test_first_registration_succeeds():
    block = register_invoice("INV-2026-103", HASH_A, "WeBank", 55_250.0)
    assert block["block_index"] == 0
    assert block["previous_block_hash"] == "0" * 64
    assert len(block["block_hash"]) == 64


def test_same_invoice_same_documents_is_blocked():
    register_invoice("INV-2026-103", HASH_A, "WeBank", 55_250.0)
    with pytest.raises(DoubleFinancingError):
        register_invoice("INV-2026-103", HASH_A, "OtherFunder", 55_250.0)


def test_renumbered_resubmission_of_the_same_documents_is_blocked():
    """
    REGRESSION. The old check was `any(block["invoice_id"] == invoice_id)`, so
    the same trade resubmitted as INV-2026-103-A — same PO, same B/L, same
    goods — passed cleanly. Indexing by document hash catches it.
    """
    register_invoice("INV-2026-103", HASH_A, "WeBank", 55_250.0)
    with pytest.raises(DoubleFinancingError, match="different invoice number"):
        register_invoice("INV-2026-103-A", HASH_A, "OtherFunder", 55_250.0)


def test_same_invoice_with_altered_documents_requires_review():
    """
    The inverse case, and the one the critique names: one invoice submitted to
    two funders with two different data versions. That is a conflict about
    which version is genuine, not a duplicate to swallow silently.
    """
    register_invoice("INV-2026-103", HASH_A, "WeBank", 55_250.0)
    with pytest.raises(RegistryConflictError, match="altered"):
        register_invoice("INV-2026-103", HASH_B, "OtherFunder", 55_250.0)


def test_check_registration_reports_without_raising():
    register_invoice("INV-2026-103", HASH_A, "WeBank", 55_250.0)
    assert check_registration("INV-NEW", HASH_B)["status"] == "CLEAR"
    assert check_registration("INV-2026-103", HASH_A)["status"] == "DUPLICATE_INVOICE_ID"
    assert check_registration("INV-OTHER", HASH_A)["status"] == "DUPLICATE_DOCUMENTS"
    assert check_registration("INV-2026-103", HASH_B)["status"] == "REVIEW_REQUIRED"


def test_placeholder_bundle_hash_is_refused():
    """
    The shipped seed registry contained
    `"document_bundle_sha256": "sha256hash"` — a literal placeholder. An
    invoice whose documents were never fingerprinted must not be pledgeable.
    """
    for bad in ("sha256hash", "", "abc", "z" * 64):
        with pytest.raises(ValueError):
            register_invoice("INV-X", bad, "WeBank", 1_000.0)


def test_registry_records_its_own_scope_limit():
    """
    The registry sees only what passes through CashBridge. A pledge made to a
    funder outside the platform is invisible to it, and the block says so.
    """
    block = register_invoice("INV-2026-103", HASH_A, "WeBank", 55_250.0)
    assert "not a cross-funder registry" in block["scope_note"]


def test_chain_verifies_and_detects_a_rewritten_block(isolated_evidence):
    import json

    register_invoice("INV-1", HASH_A, "WeBank", 10_000.0)
    register_invoice("INV-2", HASH_B, "WeBank", 20_000.0)
    anchored_head = get_chain_head()
    assert verify_chain_integrity(anchored_head)["is_valid"] is True

    chain = json.loads(isolated_evidence["registry"].read_text())
    chain[0]["advance_amount_usd"] = 999_999.0
    isolated_evidence["registry"].write_text(json.dumps(chain))

    report = verify_chain_integrity()
    assert report["is_valid"] is False
    assert "do not match the recorded hash" in report["first_violation"]


def test_amount_and_partner_are_inside_the_block_hash(isolated_evidence):
    """
    REGRESSION. The old preimage covered only index, timestamp, invoice ID,
    bundle hash and previous hash — the financing partner and the advance
    amount sat outside it and could be edited after the fact without breaking
    the chain.
    """
    import json

    register_invoice("INV-1", HASH_A, "WeBank", 10_000.0)
    chain = json.loads(isolated_evidence["registry"].read_text())
    chain[0]["financing_partner"] = "SomeoneElse"
    isolated_evidence["registry"].write_text(json.dumps(chain))
    assert verify_chain_integrity()["is_valid"] is False


def test_wholesale_rewrite_is_caught_only_by_the_external_anchor(isolated_evidence):
    """
    The honest limitation, made testable. A party who controls the file can
    recompute every hash and produce a self-consistent chain. Only an
    externally anchored head hash detects that — which is why the registry
    exposes one and why the pitch must not call this log immutable.
    """
    import json

    register_invoice("INV-1", HASH_A, "WeBank", 10_000.0)
    register_invoice("INV-2", HASH_B, "WeBank", 20_000.0)
    anchored_head = get_chain_head()

    # Rebuild the chain from genesis with a different amount, recomputing hashes.
    path = isolated_evidence["registry"]
    chain = json.loads(path.read_text())
    from core.cryptographic_registry import _compute_block_hash

    prev = "0" * 64
    for block in chain:
        block["advance_amount_usd"] = 1.0
        block["previous_block_hash"] = prev
        block["block_hash"] = _compute_block_hash(
            block["block_index"], block["timestamp_utc"], block["invoice_id"],
            block["document_bundle_sha256"], block["financing_partner"],
            block["advance_amount_usd"], prev,
        )
        prev = block["block_hash"]
    path.write_text(json.dumps(chain))

    # Self-consistent: no anchor, no detection.
    assert verify_chain_integrity()["is_valid"] is True
    # With the anchor, the rewrite is caught.
    anchored = verify_chain_integrity(anchored_head)
    assert anchored["is_valid"] is False
    assert "rewritten" in anchored["first_violation"]
