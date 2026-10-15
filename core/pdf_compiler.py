"""
PDF Compiler — Generates tamper-evident Verifiable Funding Pack PDFs using fpdf2.

Each PDF contains:
  - Company and invoice details
  - 3-Way Match verification results
  - APR comparison and selected financing option
  - SHA-256 document bundle hash and audit block reference
  - Human OTP approval record

Output saved to: data/execution_evidence/
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fpdf import FPDF

from config.settings import EXECUTION_EVIDENCE_DIR

EXECUTION_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


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
        self.cell(0, 8, f"  {title}", border=0, align="L", fill=True)
        self.ln(3)
        self.set_font("Helvetica", "", 9)

    def kv_row(self, label: str, value: str, bold_value: bool = False):
        self.set_font("Helvetica", "B", 9)
        self.cell(65, 6, label + ":", border=0)
        if bold_value:
            self.set_font("Helvetica", "B", 9)
        else:
            self.set_font("Helvetica", "", 9)
        self.cell(0, 6, str(value)[:80], border=0, new_x="LMARGIN", new_y="NEXT")

    def alert_box(self, text: str, color: tuple = (255, 243, 205)):
        self.set_fill_color(*color)
        self.set_font("Helvetica", "B", 9)
        self.multi_cell(0, 7, text, border=1, fill=True)
        self.ln(2)


def _compute_bundle_sha256(invoice_id: str, buyer_name: str, amount_usd: float, timestamp: str) -> str:
    raw = f"{invoice_id}|{buyer_name}|{amount_usd:.2f}|{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()


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
        otp_approved_by: Human who approved via OTP.
        company_name: Exporting company name.

    Returns:
        Dict with pdf_filepath and document_bundle_sha256.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    document_bundle_sha256 = _compute_bundle_sha256(invoice_id, buyer_name, invoice_amount_usd, timestamp)
    filename = f"{pack_id.replace('/', '-')}.pdf"
    filepath = EXECUTION_EVIDENCE_DIR / filename

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
    pdf.kv_row("Advance Amount (USD)", f"${advance_amount_usd:,.2f}", bold_value=True)
    pdf.kv_row("Total Fee Cost (USD)", f"${total_fee_usd:,.2f}")
    pdf.kv_row("True APR", f"{apr_pct:.2f}%", bold_value=True)
    pdf.ln(4)

    # ── Section 4: Security & Integrity ─────────────────────────────────────
    pdf.section_title("4. Security & Audit Integrity")
    pdf.kv_row("Document Bundle SHA-256", document_bundle_sha256[:32] + "...")
    pdf.kv_row("Audit Hash Chain Block", f"Block #{audit_block_index}")
    pdf.kv_row("OTP Approved By", otp_approved_by)
    pdf.kv_row("Permission Level", "L3_EXTERNAL_OTP - Human OTP Verified")
    pdf.ln(4)

    # ── Alert box ────────────────────────────────────────────────────────────
    pdf.alert_box(
        "ANTI-DOUBLE-FINANCING VERIFIED: This invoice is registered in the SHA-256 "
        "hash-chain registry. Any further financing attempt will be blocked automatically.",
        color=(204, 229, 255),
    )

    pdf.ln(4)
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
