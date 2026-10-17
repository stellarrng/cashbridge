"""Verifiable Funding Pack: a PDF a lender can check without trusting CashBridge.

Contents: cover page, cover letter, the locked metrics, a summary of the invoice, purchase order and
bill of lading with the 3-way match result, the SHA-256 of every source document and of the bundle, the
registry reference, and a "recompute me" appendix listing the formulas and their inputs.

The bundle hash printed in the PDF is SHA-256 of the canonical JSON of the document hashes and locked
metrics, so anyone holding the source documents can recompute it. Pure Python plus fpdf2; no I/O
other than writing the file you name. Compression is off and the creation date is the time passed in,
so the same pack always produces the same bytes and the text can be searched.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fpdf import FPDF
from pydantic import BaseModel, Field

FOOTER = "Synthetic demo data"
INK, MUTED, RULE = (20, 20, 22), (110, 112, 115), (200, 200, 200)


def bundle_sha256(document_hashes: Dict[str, str], locked_metrics: Dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the document hashes and the locked metrics."""
    canonical = json.dumps(
        {"documents": document_hashes, "metrics": locked_metrics},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocSummary(BaseModel):
    """Key fields of one source document."""

    title: str
    rows: List[List[str]]


class PackData(BaseModel):
    """Everything the PDF prints. Built by the coordinator from engine outputs."""

    pack_id: str
    company: str
    lender: str
    product: str
    generated_at: datetime
    forecast_run: str
    invoice_no: str
    amount_requested: str
    letter_text: str
    locked_metrics: List[List[str]]  # label, value text
    documents: List[DocSummary]
    three_way_status: str
    three_way_differences: List[str] = Field(default_factory=list)
    scan_lines: List[str] = Field(default_factory=list)
    document_hashes: Dict[str, str]
    bundle_sha256: str
    action_hash: str
    registry_check: str
    registry_key: str
    registry_head: str
    registry_block: Optional[Dict[str, Any]] = None
    lender_ref: Optional[str] = None
    attribution: List[List[str]] = Field(default_factory=list)  # driver, amount text
    formulas: List[List[str]] = Field(default_factory=list)  # name, formula and inputs


def _safe(text: Any) -> str:
    """Core PDF fonts are Latin-1: replace anything else with a plain equivalent."""
    text = str(text)
    for old, new in {"–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."}.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


class _Pack(FPDF):
    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"{FOOTER}  |  page {self.page_no()}", align="C")


def _heading(pdf: FPDF, text: str, size: int = 15) -> None:
    pdf.set_font("Helvetica", "B", size)
    pdf.set_text_color(*INK)
    pdf.cell(0, 9, _safe(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*INK)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)


def _para(pdf: FPDF, text: str, size: int = 10, color=INK) -> None:
    pdf.set_font("Helvetica", "", size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, 5.2, _safe(text), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def _table(pdf: FPDF, rows: List[List[str]], widths: List[float], header: Optional[List[str]] = None, mono_col: Optional[int] = None) -> None:
    pdf.set_draw_color(*RULE)
    with pdf.table(col_widths=widths, text_align="LEFT", line_height=5.2, borders_layout="HORIZONTAL_LINES", first_row_as_headings=bool(header)) as table:
        if header:
            row = table.row()
            for cell in header:
                pdf.set_font("Helvetica", "B", 8.5)
                row.cell(_safe(cell))
        for values in rows:
            row = table.row()
            for index, cell in enumerate(values):
                if mono_col is not None and index == mono_col:
                    pdf.set_font("Courier", "", 7.5)
                else:
                    pdf.set_font("Helvetica", "", 9)
                row.cell(_safe(cell))
    pdf.ln(3)


def compile_pack(data: PackData, path: Path) -> Path:
    """Write the Verifiable Funding Pack PDF to ``path`` and return it."""
    pdf = _Pack(format="A4")
    pdf.set_compression(False)
    pdf.set_creation_date(data.generated_at)
    pdf.set_title(_safe(f"Verifiable Funding Pack {data.pack_id}"))
    pdf.set_author("CashBridge (SYNTHETIC demo)")
    pdf.set_subject("Synthetic demo data")
    pdf.set_margins(20, 18, 20)
    pdf.set_auto_page_break(True, margin=20)

    # ---- cover
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, "CASHBRIDGE  |  SYNTHETIC DEMO DATA", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(24)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 12, "Verifiable\nFunding Pack", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 6.5, _safe(f"{data.company}\nfor {data.lender}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    _table(pdf, [
        ["Pack", data.pack_id], ["Invoice", data.invoice_no], ["Product", data.product],
        ["Funds requested", data.amount_requested], ["Prepared", data.generated_at.strftime("%Y-%m-%d %H:%M UTC")],
        ["Forecast run", data.forecast_run],
    ], [45, 125])
    pdf.ln(4)
    _heading(pdf, "How to check this pack", 11)
    _para(pdf, "Every figure in this pack is computed by deterministic code, not written by a language model. Each source document is "
               "fingerprinted with SHA-256. The bundle hash on page 5 covers all document hashes and all locked metrics, so changing any of "
               "them changes the bundle hash. The appendix lists the formulas so the figures can be recomputed by hand.", 9.5, MUTED)

    # ---- letter
    pdf.add_page()
    _heading(pdf, "1. Cover letter")
    _para(pdf, data.letter_text, 10.5)

    # ---- metrics
    pdf.add_page()
    _heading(pdf, "2. Locked metrics")
    _para(pdf, "These figures were frozen when the pack was prepared. The cover letter may state only these numbers.", 9.5, MUTED)
    _table(pdf, data.locked_metrics, [110, 60])

    # ---- documents
    pdf.add_page()
    _heading(pdf, "3. Source documents and 3-way match")
    for doc in data.documents:
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*INK)
        pdf.cell(0, 7, _safe(doc.title), new_x="LMARGIN", new_y="NEXT")
        _table(pdf, doc.rows, [55, 115])
    _para(pdf, f"3-way match result: {data.three_way_status}", 11)
    for line in data.three_way_differences:
        _para(pdf, f"- {line}", 10, (160, 50, 40))
    for line in data.scan_lines:
        _para(pdf, f"Scanned copy: {line}", 9.5, MUTED)

    # ---- hashes and registry
    pdf.add_page()
    _heading(pdf, "4. Fingerprints and registry")
    _table(pdf, [[name.replace("_", " ").title(), digest] for name, digest in data.document_hashes.items()], [35, 135], header=["Document", "SHA-256"], mono_col=1)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, "Bundle SHA-256", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "B", 7.6)
    pdf.cell(0, 6, data.bundle_sha256, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Approval action hash", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", "", 7.6)
    pdf.cell(0, 6, data.action_hash, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Invoice registry (tamper-evident hash chain)", new_x="LMARGIN", new_y="NEXT")
    rows = [["Check", data.registry_check], ["Invoice key (SHA-256)", data.registry_key], ["Registry head before this pack", data.registry_head]]
    if data.registry_block:
        rows += [["Registry block", str(data.registry_block.get("block_index"))], ["Block hash", str(data.registry_block.get("block_hash"))],
                 ["Lender reference (MOCK)", data.lender_ref or ""]]
    _table(pdf, rows, [55, 115])
    _para(pdf, "A registry held inside one company's systems cannot stop the same invoice being financed at a second lender. "
               "In production it must be shared, for example run by a lender consortium or anchored to the e-invoice authority.", 9, MUTED)

    # ---- appendix
    pdf.add_page()
    _heading(pdf, "5. Appendix: recompute me")
    if data.attribution:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "What causes the shortfall", new_x="LMARGIN", new_y="NEXT")
        _table(pdf, data.attribution, [125, 45])
    _table(pdf, data.formulas, [45, 125], header=["Quantity", "Formula and inputs"])
    _para(pdf, f"Bundle SHA-256: {data.bundle_sha256}", 8.5, MUTED)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path


_PRINTED = re.compile(rb"\(([0-9a-f]{64})\)")


def printed_hashes(path: Path) -> List[str]:
    """Every 64-hex string printed in the PDF text, in order (for checking a pack against its sources)."""
    return [m.group(1).decode() for m in _PRINTED.finditer(Path(path).read_bytes())]
