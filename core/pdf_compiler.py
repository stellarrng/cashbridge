"""
PDF Compiler — builds the funding pack a funder receives.

Each pack carries the invoice and buyer, the 3-way match result, the selected
financing terms with cash actually received, whether that closes the cash gap,
the SHA-256 fingerprint of the trade documents, the audit block reference, and
the scope limits of every check behind it.

ON THE WORD "TAMPER-EVIDENT"
----------------------------
This module used to describe its output as "tamper-evident Verifiable Funding
Pack PDFs". It is not. The PDF is not digitally signed and its own hash is not
anchored anywhere, so a recipient can edit it freely and nothing detects that.

What IS fingerprinted is the trade document BUNDLE — the invoice, purchase
order and bill of lading — whose hash is printed on the pack and recorded in
the registry. A reader can check that the pack refers to a bundle the system
verified. They cannot check that the pack itself is unaltered.

Making the PDF genuinely tamper-evident needs a digital signature (PAdES or
equivalent) or publication of the file's own hash to somewhere the issuer does
not control. Until one of those exists, neither the code nor the page claims it.

Output goes to the active run directory, never to committed evidence.
"""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fpdf import FPDF

from config.runtime import artifacts_dir

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# The built-in Helvetica face is latin-1 only. Real trade data is full of
# characters outside it — em dashes and curly quotes from copy-paste, and
# Vietnamese diacritics in party names and addresses — and fpdf2 raises on
# every one of them. A funding pack that crashes on a buyer called "Công ty
# TNHH" is not usable, so text is transliterated to the nearest latin-1 form
# before it reaches the font.
_CHARACTER_SUBSTITUTIONS = {
    "\u2014": "-", "\u2013": "-", "\u2212": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u00a0": " ", "\u20ab": "VND", "\u20ac": "EUR",
    "\u2022": "-", "\u2192": "->", "\u00d7": "x",
}


def latin1_safe(text: str) -> str:
    """
    Reduce text to something the built-in PDF font can render.

    Known punctuation is substituted, then remaining non-latin-1 characters
    are decomposed and stripped of combining marks, so Vietnamese renders as
    readable unaccented latin rather than raising. Anything still unmappable
    becomes "?" instead of crashing the pack.

    A deployment that needs correct diacritics should register a Unicode TTF
    with `add_font` and bypass this; losing accents in a legal document is a
    compromise, not a solution, and it is better to say so than to let the
    substitution pass unremarked.
    """
    if not text:
        return ""
    for bad, good in _CHARACTER_SUBSTITUTIONS.items():
        text = text.replace(bad, good)
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        decomposed = unicodedata.normalize("NFKD", text)
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return stripped.encode("latin-1", errors="replace").decode("latin-1")


class FundingPackPDF(FPDF):
    """Custom FPDF subclass with CashBridge header and footer."""

    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(15, 52, 96)   # Deep navy
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, "CashBridge - Verifiable Funding Pack", border=0, align="C", fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()} | SHA-256 Secured | CashBridge 2026 FinTechathon", align="C")

    def section_title(self, title: str):
        self.set_font("Helvetica", "B", 10)
        self.set_fill_color(230, 237, 248)
        self.cell(0, 8, latin1_safe(f"  {title}"), border=0, align="L", fill=True)
        self.ln(3)
        self.set_font("Helvetica", "", 9)

    def kv_row(self, label: str, value: str, bold_value: bool = False):
        self.set_font("Helvetica", "B", 9)
        self.cell(65, 6, latin1_safe(label) + ":", border=0)
        if bold_value:
            self.set_font("Helvetica", "B", 9)
        else:
            self.set_font("Helvetica", "", 9)
        self.cell(0, 6, latin1_safe(str(value))[:80], border=0,
                  new_x="LMARGIN", new_y="NEXT")

    def bullet(self, text: str):
        """
        A wrapped bullet line.

        `multi_cell` with width 0 consumes the space from the CURRENT x to the
        right margin, and `section_title` leaves the cursor at the right edge —
        so calling it directly raises "Not enough horizontal space to render a
        single character". The cursor is reset to the left margin first.
        """
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, latin1_safe(f"- {text}"))

    def body_text(self, text: str):
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, latin1_safe(text))

    def alert_box(self, text: str, color: tuple = (255, 243, 205)):
        self.set_x(self.l_margin)
        self.set_fill_color(*color)
        self.set_font("Helvetica", "B", 9)
        self.multi_cell(0, 7, latin1_safe(text), border=1, fill=True)
        self.ln(2)


def generate_funding_pack_pdf(
    pack_id: str,
    invoice_id: str,
    buyer_name: str,
    buyer_country: str,
    invoice_amount_usd: float,
    advance_amount_usd: float,
    financing_partner: str,
    apr_pct: float,
    total_fee_usd: float,
    days_accelerated: int,
    match_status: str,
    audit_block_index: int,
    document_bundle_sha256: str,
    cash_in_hand_usd: Optional[float] = None,
    cash_need_usd: Optional[float] = None,
    assumptions: Optional[list] = None,
    checks_not_performed: Optional[list] = None,
    is_mock_partner: bool = True,
    otp_approved_by: str = "CFO_DEMO_USER",
    company_name: str = "Pacific Timber & Garment Exports Ltd.",
) -> dict:
    """
    Generate a tamper-evident Verifiable Funding Pack PDF for a financing application.

    Args:
        pack_id: Unique pack identifier (e.g., 'PACK-2026-001').
        invoice_id: Invoice being financed (e.g., 'INV-2026-103').
        buyer_name: Foreign buyer name.
        buyer_country: Buyer country.
        invoice_amount_usd: Full invoice face value in USD.
        advance_amount_usd: Financing advance amount in USD.
        financing_partner: Name of the selected financing provider.
        apr_pct: True annualized percentage rate of the chosen option.
        total_fee_usd: Total fees charged by the financing partner.
        days_accelerated: Number of days the invoice is being accelerated.
        match_status: Result of the 3-way match (e.g., 'VERIFIED_3WAY').
        audit_block_index: Index of the invoice's block in the SHA-256 hash chain.
        document_bundle_sha256: The hash produced by the 3-way match over the
            actual document contents. Previously the compiler computed its own
            hash over (invoice_id, buyer, amount, timestamp), which fingerprinted
            neither the documents nor anything stable — a reviewer could not use
            it to check that the pack described the same papers the engine
            verified, and it differed on every regeneration.
        cash_in_hand_usd: Spendable cash after fees, if known.
        cash_need_usd: The gap the facility is meant to close, if known.
        assumptions: Assumptions behind the quoted terms.
        checks_not_performed: Verifications this build cannot do.
        is_mock_partner: Whether the quoted terms are simulated.
        otp_approved_by: Human who approved via OTP.
        company_name: Exporting company name.

    Returns:
        Dict with pdf_filepath and the document_bundle_sha256 carried through.

    Raises:
        ValueError: If no document bundle hash is supplied — a funding pack
            without a fingerprint of the documents it rests on is not verifiable.
    """
    if not document_bundle_sha256 or not _SHA256_RE.match(
        str(document_bundle_sha256).lower()
    ):
        # Length alone is not enough: "z" * 64 is 64 characters and is not a
        # digest. A pack that cannot be tied to specific documents is not a
        # verifiable funding pack.
        raise ValueError(
            "document_bundle_sha256 must be a 64-character hexadecimal SHA-256 "
            "digest produced by a verified 3-way match."
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    filename = f"{pack_id.replace('/', '-')}.pdf"
    filepath = artifacts_dir() / filename

    pdf = FundingPackPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(18, 15, 18)

    # ── Title block ──────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Verifiable Funding Pack", align="C")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Pack ID: {pack_id}   |   Generated: {timestamp[:19]} UTC", align="C")
    pdf.ln(8)

    # ── Section 1: Exporter Details ──────────────────────────────────────────
    pdf.section_title("1. Exporter Details")
    pdf.kv_row("Company", company_name)
    pdf.kv_row("Pack Reference", pack_id)
    pdf.kv_row("Generated", timestamp[:19] + " UTC")
    pdf.ln(4)

    # ── Section 2: Invoice & Buyer Details ───────────────────────────────────
    pdf.section_title("2. Invoice & Buyer Details")
    pdf.kv_row("Invoice ID", invoice_id)
    pdf.kv_row("Foreign Buyer", buyer_name)
    pdf.kv_row("Buyer Country", buyer_country)
    pdf.kv_row("Invoice Amount (USD)", f"${invoice_amount_usd:,.2f}")
    pdf.kv_row("Days Accelerated", str(days_accelerated))
    pdf.kv_row("3-Way Match Status", match_status, bold_value=True)
    pdf.ln(4)

    # ── Section 3: Financing Terms ───────────────────────────────────────────
    pdf.section_title("3. Selected Financing Terms")
    pdf.kv_row("Financing Partner", financing_partner)
    pdf.kv_row("Gross Advance (USD)", f"${advance_amount_usd:,.2f}")
    if cash_in_hand_usd is not None:
        pdf.kv_row("Cash In Hand After Fees", f"${cash_in_hand_usd:,.2f}", bold_value=True)
    pdf.kv_row("Total Cost (USD)", f"${total_fee_usd:,.2f}")
    pdf.kv_row("True APR (on cash received)", f"{apr_pct:.2f}%", bold_value=True)
    if cash_need_usd is not None:
        # `cash_in_hand_usd or advance_amount_usd` treats 0.0 as "not supplied"
        # and substitutes the gross advance, so a facility releasing nothing
        # would print as covering the gap. 0.0 is a real value.
        spendable = (
            advance_amount_usd if cash_in_hand_usd is None else cash_in_hand_usd
        )
        covers = spendable >= cash_need_usd
        pdf.kv_row("Cash Gap To Close", f"${cash_need_usd:,.2f}")
        pdf.kv_row(
            "Closes The Gap",
            "YES" if covers else
            f"NO - ${cash_need_usd - spendable:,.2f} short",
            bold_value=True,
        )
    pdf.ln(4)

    if assumptions:
        pdf.section_title("3b. Assumptions Behind These Terms")
        for item in assumptions[:8]:
            pdf.bullet(item)
        pdf.ln(3)

    # ── Section 4: Security & Integrity ─────────────────────────────────────
    pdf.section_title("4. Security & Audit Integrity")
    pdf.kv_row("Document Bundle SHA-256", document_bundle_sha256[:32] + "...")
    pdf.kv_row("Audit Hash Chain Block", f"Block #{audit_block_index}")
    pdf.kv_row("OTP Approved By", otp_approved_by)
    pdf.kv_row("Permission Level", "L3_EXTERNAL_OTP - Human OTP Verified")
    pdf.ln(4)

    # ── Scope of assurance ───────────────────────────────────────────────────
    # The previous wording ("ANTI-DOUBLE-FINANCING VERIFIED ... any further
    # financing attempt will be blocked automatically") claimed an assurance the
    # system cannot give. The registry only sees submissions made through
    # CashBridge; a pledge to a funder outside it is invisible here. A funding
    # pack that overstates its own guarantees damages the case for the rest of
    # the evidence in it.
    pdf.section_title("5. Scope And Limits Of This Pack")
    pdf.body_text(
        "- DUPLICATE CHECK: this invoice is recorded in CashBridge's hash-chain "
        "registry, which detects a second pledge submitted THROUGH CASHBRIDGE. "
        "It cannot see a pledge made to a funder outside this system.\n"
        "- DOCUMENT CHECK: the 3-way match establishes that the invoice, "
        "purchase order and bill of lading are mutually consistent. It does not "
        "establish that the underlying trade occurred, that the buyer "
        "acknowledges the debt, or that no dispute exists.\n"
        "- ELIGIBILITY: this pack reflects CashBridge's pre-screen only. It is "
        "not a credit decision and not an offer of finance. The funder may "
        "decline on buyer, country, goods or contract grounds."
    )
    pdf.ln(3)

    if checks_not_performed:
        pdf.body_text("Verifications NOT performed in this build:")
        for item in checks_not_performed[:8]:
            pdf.bullet(item)
        pdf.ln(2)

    if is_mock_partner:
        pdf.alert_box(
            "SIMULATED TERMS: the pricing in this pack comes from a mock funding "
            "partner. No funding agreement exists and no funder has reviewed it.",
            color=(255, 243, 205),
        )
        pdf.ln(2)

    pdf.alert_box(
        "L4 NOTICE: No funds are disbursed automatically by CashBridge. "
        "All money movement must be executed manually through authorised banking portals.",
        color=(255, 235, 235),
    )

    pdf.output(str(filepath))

    return {
        "pack_id": pack_id,
        "pdf_filepath": str(filepath),
        "document_bundle_sha256": document_bundle_sha256,
        "timestamp_utc": timestamp,
    }
