"""
Funding pack PDF — the document a funder actually receives.

This file was flagged in review as the one significant output with no
automated coverage. The pack is not decoration: it is the artefact that
carries the numbers, the disclosures and the scope limits out of the system
and in front of a third party. A wrong figure or a missing limitation here is
worse than the same error on a screen, because the PDF travels without the
person who generated it.

The text assertions read the rendered PDF rather than the code that produced
it, so a layout change that drops a section fails the test.
"""

import re

import pytest
from pypdf import PdfReader

from core.pdf_compiler import generate_funding_pack_pdf
from core.funding_evaluator import evaluate_liquidity_options

VALID_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def read_pdf_text(path) -> str:
    """Rendered text, with whitespace flattened so line wrapping does not matter."""
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return re.sub(r"\s+", " ", text)


@pytest.fixture
def pack(tmp_path):
    """A pack where the chosen facility does NOT close the gap."""
    return generate_funding_pack_pdf(
        pack_id="PACK-TEST-001",
        invoice_id="INV-2026-103",
        buyer_name="Nordic Home Retail",
        buyer_country="United States",
        invoice_amount_usd=65_000.00,
        advance_amount_usd=55_250.00,
        financing_partner="WeBank Partner Supply Chain Factoring",
        apr_pct=11.42,
        total_fee_usd=731.56,
        days_accelerated=45,
        match_status="VERIFIED_3WAY",
        audit_block_index=0,
        document_bundle_sha256=VALID_HASH,
        cash_in_hand_usd=54_518.44,
        cash_need_usd=66_350.00,
        assumptions=[
            "Fee is charged on the advance, not the invoice face value",
            "Reserve is released only when the buyer pays on time",
        ],
        checks_not_performed=[
            "Buyer existence not verified against any company registry",
            "Document authenticity not established",
        ],
        is_mock_partner=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# It renders
# ─────────────────────────────────────────────────────────────────────────────

def test_pack_is_written_to_disk(pack):
    from pathlib import Path

    path = Path(pack["pdf_filepath"])
    assert path.exists()
    assert path.stat().st_size > 1000
    assert path.suffix == ".pdf"


def test_pack_lands_in_the_active_run_directory(pack, isolated_evidence):
    """It must not write into committed evidence, like everything else."""
    from pathlib import Path

    assert Path(pack["pdf_filepath"]).parent == isolated_evidence["dir"]


# ─────────────────────────────────────────────────────────────────────────────
# The numbers on the page
# ─────────────────────────────────────────────────────────────────────────────

def test_invoice_and_buyer_appear(pack):
    text = read_pdf_text(pack["pdf_filepath"])
    assert "INV-2026-103" in text
    assert "Nordic Home Retail" in text
    assert "65,000.00" in text


def test_cash_in_hand_is_shown_not_just_the_gross_advance(pack):
    """
    The figure that matters to the borrower is what they can spend. A pack
    that prints only the gross advance invites the reader to plan around
    $55,250 when $54,518.44 arrives.
    """
    text = read_pdf_text(pack["pdf_filepath"])
    assert "54,518.44" in text
    assert "55,250.00" in text


def test_cost_and_rate_are_shown(pack):
    text = read_pdf_text(pack["pdf_filepath"])
    assert "731.56" in text
    assert "11.42" in text


def test_pack_states_the_gap_is_not_closed(pack):
    """
    The single most consequential line. This facility releases $54,518.44
    against a $66,350.00 need. The pack must say so, and say by how much.
    """
    text = read_pdf_text(pack["pdf_filepath"])
    assert "66,350.00" in text
    assert "NO" in text
    assert "11,831.56" in text


def test_pack_states_when_the_gap_is_closed(tmp_path):
    result = generate_funding_pack_pdf(
        pack_id="PACK-TEST-002", invoice_id="INV-1", buyer_name="Buyer",
        buyer_country="US", invoice_amount_usd=65_000.0, advance_amount_usd=65_000.0,
        financing_partner="Funder", apr_pct=12.0, total_fee_usd=500.0,
        days_accelerated=45, match_status="VERIFIED_3WAY", audit_block_index=0,
        document_bundle_sha256=VALID_HASH, cash_in_hand_usd=64_500.0,
        cash_need_usd=20_000.0, is_mock_partner=False,
    )
    assert "YES" in read_pdf_text(result["pdf_filepath"])


def test_coverage_is_judged_on_cash_in_hand_not_gross_advance():
    """
    REGRESSION GUARD. The gross advance clears the need; the cash actually
    received does not. If the pack judges coverage on the gross figure it
    prints YES on a facility that leaves the business $1,000 short.
    """
    result = generate_funding_pack_pdf(
        pack_id="PACK-TEST-003", invoice_id="INV-1", buyer_name="Buyer",
        buyer_country="US", invoice_amount_usd=65_000.0,
        advance_amount_usd=60_000.0,     # gross clears the 59,000 need
        financing_partner="Funder", apr_pct=12.0, total_fee_usd=2_000.0,
        days_accelerated=45, match_status="VERIFIED_3WAY", audit_block_index=0,
        document_bundle_sha256=VALID_HASH,
        cash_in_hand_usd=58_000.0,       # cash received does not
        cash_need_usd=59_000.0,
    )
    text = read_pdf_text(result["pdf_filepath"])
    assert "short" in text.lower()
    assert "1,000.00" in text


def test_zero_cash_in_hand_does_not_silently_fall_back_to_the_advance():
    """
    `cash_in_hand_usd or advance_amount_usd` treats 0.0 as "not supplied" and
    quietly substitutes the gross advance — so a facility releasing nothing
    would be reported as covering the gap. 0.0 is a real value and must be
    honoured.
    """
    result = generate_funding_pack_pdf(
        pack_id="PACK-TEST-004", invoice_id="INV-1", buyer_name="Buyer",
        buyer_country="US", invoice_amount_usd=65_000.0, advance_amount_usd=55_000.0,
        financing_partner="Funder", apr_pct=12.0, total_fee_usd=0.0,
        days_accelerated=45, match_status="VERIFIED_3WAY", audit_block_index=0,
        document_bundle_sha256=VALID_HASH,
        cash_in_hand_usd=0.0,
        cash_need_usd=10_000.0,
    )
    text = read_pdf_text(result["pdf_filepath"])
    assert "short" in text.lower()
    assert "10,000.00" in text


# ─────────────────────────────────────────────────────────────────────────────
# The disclosures
# ─────────────────────────────────────────────────────────────────────────────

def test_simulated_partner_is_declared_on_the_page(pack):
    text = read_pdf_text(pack["pdf_filepath"])
    assert "SIMULATED TERMS" in text
    assert "no funding agreement exists" in text.lower()


def test_real_partner_pack_omits_the_simulated_banner(tmp_path):
    result = generate_funding_pack_pdf(
        pack_id="PACK-TEST-005", invoice_id="INV-1", buyer_name="Buyer",
        buyer_country="US", invoice_amount_usd=65_000.0, advance_amount_usd=55_000.0,
        financing_partner="Real Funder", apr_pct=12.0, total_fee_usd=500.0,
        days_accelerated=45, match_status="VERIFIED_3WAY", audit_block_index=0,
        document_bundle_sha256=VALID_HASH, is_mock_partner=False,
    )
    assert "SIMULATED TERMS" not in read_pdf_text(result["pdf_filepath"])


def test_duplicate_check_scope_is_stated(pack):
    """The registry sees CashBridge submissions only. The pack must say so."""
    text = read_pdf_text(pack["pdf_filepath"]).lower()
    assert "outside this system" in text


def test_document_check_scope_is_stated(pack):
    """Consistency is not proof the trade occurred."""
    text = read_pdf_text(pack["pdf_filepath"]).lower()
    assert "mutually consistent" in text
    assert "does not establish" in text


def test_pack_is_not_presented_as_a_credit_decision(pack):
    text = read_pdf_text(pack["pdf_filepath"]).lower()
    assert "not a credit decision" in text
    assert "decline" in text


def test_no_automatic_disbursement_notice_is_present(pack):
    text = read_pdf_text(pack["pdf_filepath"])
    assert "L4 NOTICE" in text
    assert "no funds are disbursed automatically" in text.lower()


def test_checks_not_performed_are_printed(pack):
    text = read_pdf_text(pack["pdf_filepath"]).lower()
    assert "verifications not performed" in text
    assert "company registry" in text


def test_assumptions_are_printed(pack):
    text = read_pdf_text(pack["pdf_filepath"]).lower()
    assert "assumptions" in text
    assert "charged on the advance" in text


def test_pack_does_not_claim_the_pdf_is_tamper_evident(pack):
    """
    The PDF is not signed and its own hash is not anchored anywhere, so
    nothing stops a recipient editing it. The bundle hash printed on it
    fingerprints the trade DOCUMENTS, not this file. Claiming otherwise on
    the page would be the kind of overstatement the rest of the pack avoids.
    """
    text = read_pdf_text(pack["pdf_filepath"]).lower()
    assert "tamper-evident" not in text
    assert "tamper evident" not in text


# ─────────────────────────────────────────────────────────────────────────────
# Inputs it must refuse
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_hash", ["", None, "sha256hash", "abc123", "z" * 64])
def test_pack_requires_a_real_document_bundle_hash(bad_hash):
    """
    A pack that cannot be tied to specific documents is not verifiable. The
    shipped seed registry once carried the literal string "sha256hash".
    """
    with pytest.raises(ValueError):
        generate_funding_pack_pdf(
            pack_id="P", invoice_id="I", buyer_name="B", buyer_country="US",
            invoice_amount_usd=1.0, advance_amount_usd=1.0, financing_partner="F",
            apr_pct=1.0, total_fee_usd=0.0, days_accelerated=1,
            match_status="VERIFIED_3WAY", audit_block_index=0,
            document_bundle_sha256=bad_hash,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Against a real evaluator result
# ─────────────────────────────────────────────────────────────────────────────

def test_pack_renders_from_a_live_option_including_a_package():
    """
    End to end: the figures on the page come from the evaluator, not from
    literals in the test. A package has several facilities, and the pack must
    still render coherently from it.
    """
    options = evaluate_liquidity_options("INV-2026-103", 65_000.0, 45, 66_350.0)
    best = options[0]
    assert best.option_type == "COMBINATION"

    result = generate_funding_pack_pdf(
        pack_id="PACK-TEST-006",
        invoice_id=best.eligible_invoice_id,
        buyer_name="Nordic Home Retail",
        buyer_country="United States",
        invoice_amount_usd=best.invoice_gross_amount_usd,
        advance_amount_usd=best.gross_advance_usd,
        financing_partner=best.provider,
        apr_pct=best.effective_apr_pct,
        total_fee_usd=best.total_cost_usd,
        days_accelerated=best.days_financed,
        match_status="VERIFIED_3WAY",
        audit_block_index=0,
        document_bundle_sha256=VALID_HASH,
        cash_in_hand_usd=best.cash_in_hand_usd,
        cash_need_usd=best.cash_need_usd,
        assumptions=best.assumptions,
        checks_not_performed=["Buyer existence not verified"],
        is_mock_partner=best.is_mock_partner,
    )
    text = read_pdf_text(result["pdf_filepath"])
    assert f"{best.cash_in_hand_usd:,.2f}" in text
    assert "YES" in text
    assert "SIMULATED TERMS" in text


# ─────────────────────────────────────────────────────────────────────────────
# Characters real trade data actually contains
# ─────────────────────────────────────────────────────────────────────────────

def test_vietnamese_party_names_do_not_crash_the_pack():
    """
    REGRESSION. The built-in Helvetica face is latin-1 only, and fpdf2 raises
    FPDFUnicodeEncodingException on anything outside it. The pack is for
    Vietnamese exporters, so buyer and supplier names routinely carry
    diacritics — and the module's own assumption strings contained em dashes,
    which crashed pack generation outright.
    """
    result = generate_funding_pack_pdf(
        pack_id="PACK-TEST-007",
        invoice_id="INV-2026-200",
        buyer_name="Công ty TNHH Thương mại Đông Á",
        buyer_country="Việt Nam",
        invoice_amount_usd=65_000.0, advance_amount_usd=55_000.0,
        financing_partner="Ngân hàng — chi nhánh Hải Phòng",
        apr_pct=12.0, total_fee_usd=500.0, days_accelerated=45,
        match_status="VERIFIED_3WAY", audit_block_index=0,
        document_bundle_sha256=VALID_HASH,
        cash_in_hand_usd=54_500.0,
        assumptions=["Phí — tính trên khoản ứng, không phải mệnh giá"],
        checks_not_performed=["Người mua chưa được xác minh"],
        company_name="Pacific Timber & Garment Exports Ltd.",
    )
    text = read_pdf_text(result["pdf_filepath"])
    # Accents are lost to the latin-1 font, but the name is still readable and
    # the pack is produced rather than raising.
    assert "Cong ty TNHH" in text
    assert "INV-2026-200" in text


def test_latin1_transliteration_is_documented_as_lossy():
    from core.pdf_compiler import latin1_safe

    assert latin1_safe("Đông Á") == "ong A" or "ong A" in latin1_safe("Đông Á")
    assert latin1_safe("a — b") == "a - b"
    assert latin1_safe("") == ""
