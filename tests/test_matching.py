"""Matching engine (Step 1.1)."""

from datetime import date
from decimal import Decimal

from core.matching_engine import reconcile, three_way_match
from schemas.document_schemas import (
    BankTxn,
    Currency,
    MatchStatus,
    Money,
    ReconStatus,
)
from tests.fixtures import US_BUYER, make_invoice, matching_po_bl, open_invoices, usd, wire


def test_tier1_exact_match_on_reference():
    txn = wire("9870", "INV-1025")
    result = reconcile(txn, open_invoices())
    assert (result.tier, result.matched_invoices, result.gap) == (1, ["INV-1025"], Decimal("0"))
    assert result.confidence == 1.0 and result.status is ReconStatus.BOOKED


def test_tier2_tolerance_with_35_dollar_fee():
    result = reconcile(wire("9835", "INV-1025"), open_invoices())
    assert result.tier == 2
    assert result.matched_invoices == ["INV-1025"]
    assert result.gap == Decimal("35") and result.gap_reason == "bank_fee"
    assert result.status is ReconStatus.BOOKED


def test_tier2_rejects_gap_above_fee_tolerance():
    result = reconcile(wire("9800", "INV-1025"), open_invoices())  # gap 70 > 50, no subset fits
    assert result.status is ReconStatus.NEEDS_HUMAN
    assert result.tier is None


def test_story_wire_resolves_uniquely_by_subset_sum():
    result = reconcile(wire(), open_invoices())
    assert result.tier == 3
    assert set(result.matched_invoices) == {"INV-1021", "INV-1022", "INV-1024"}
    assert result.gap == Decimal("35") and result.gap_reason == "bank_fee"
    assert result.confidence == 1.0 and result.status is ReconStatus.BOOKED


def test_overpayment_is_not_a_fee_match():
    result = reconcile(wire("48700"), open_invoices())
    assert result.status is ReconStatus.NEEDS_HUMAN


def test_ambiguous_subset_sum_returns_all_candidates_and_needs_human():
    invoices = [make_invoice("INV-2001", "1000"), make_invoice("INV-2002", "1000"), make_invoice("INV-2003", "500")]
    result = reconcile(wire("1000", ""), invoices)
    assert result.status is ReconStatus.NEEDS_HUMAN
    assert sorted(result.candidates) == [["INV-2001"], ["INV-2002"]]
    assert result.matched_invoices == []


def test_subset_sum_only_uses_the_senders_invoices():
    other = make_invoice("INV-3001", "48655", buyer="B-OTHER")
    result = reconcile(wire(), open_invoices() + [other])
    assert set(result.matched_invoices) == {"INV-1021", "INV-1022", "INV-1024"}


def test_subset_sum_never_exceeds_six_invoices():
    invoices = [make_invoice(f"INV-40{i:02d}", "100") for i in range(8)]
    result = reconcile(wire("800", ""), invoices)  # needs 8 invoices
    assert result.status is ReconStatus.NEEDS_HUMAN and result.tier is None


def test_fx_difference_between_currencies_needs_approval():
    jpy_invoice = make_invoice(
        "INV-5001", Money.from_amount(1_750_000, Currency.JPY), currency=Currency.JPY
    )  # 1,750,000 JPY = USD 11,778.85
    txn = BankTxn(
        txn_id="TXN-1", txn_date=date(2026, 10, 19), amount=usd("11760"),
        buyer_id=US_BUYER, reference="INV-5001",
    )
    result = reconcile(txn, [jpy_invoice])
    assert result.gap_reason == "fx_difference" and result.confidence < 1.0
    assert result.status is ReconStatus.NEEDS_HUMAN
    assert result.matched_invoices == ["INV-5001"]


def test_three_way_equal_is_eligible():
    invoice = make_invoice("INV-1030", "60000")
    po, bl = matching_po_bl(invoice)
    result = three_way_match(po, invoice, bl)
    assert result.status is MatchStatus.ELIGIBLE and result.differences == []


def test_three_way_package_shortage_is_flagged_with_readable_difference():
    invoice = make_invoice("INV-1027", "27400", package_count=120)
    po, bl = matching_po_bl(invoice)
    bl = bl.model_copy(update={"package_count": 118})
    result = three_way_match(po, invoice, bl)
    assert result.status is MatchStatus.FLAGGED
    assert result.differences == ["B/L packages 118 vs invoice 120"]


def test_three_way_amount_tolerance_is_one_cent():
    invoice = make_invoice("INV-1", "100.01")
    po, bl = matching_po_bl(invoice)
    ok = po.model_copy(update={"amount": usd("100.00")})
    assert three_way_match(ok, invoice, bl).status is MatchStatus.ELIGIBLE
    far = po.model_copy(update={"amount": usd("99.99")})
    result = three_way_match(far, invoice, bl)
    assert result.status is MatchStatus.FLAGGED
    assert result.differences == ["PO amount USD 99.99 vs invoice USD 100.01"]


def test_three_way_ports_and_quantity_are_checked():
    invoice = make_invoice("INV-1", "100")
    po, bl = matching_po_bl(invoice)
    bl = bl.model_copy(update={"port_of_discharge": "Long Beach", "quantity": 100})
    result = three_way_match(po, invoice, bl)
    assert result.status is MatchStatus.FLAGGED
    assert "B/L quantity 100 vs invoice 120" in result.differences
    assert "B/L port of discharge Long Beach vs invoice Los Angeles" in result.differences


def test_three_way_buyer_mismatch_and_missing_documents_are_blocked():
    invoice = make_invoice("INV-1", "100")
    po, bl = matching_po_bl(invoice)
    assert three_way_match(po.model_copy(update={"buyer_id": "B-X"}), invoice, bl).status is MatchStatus.BLOCKED
    assert three_way_match(None, invoice, bl).status is MatchStatus.BLOCKED
    assert three_way_match(po, invoice, None).status is MatchStatus.BLOCKED
