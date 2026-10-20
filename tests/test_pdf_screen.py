"""Risk 04: PDFs with active content are refused before they are parsed or reach a lender."""
import zlib

import pytest

from security.pdf_screen import PdfRefused, findings, screen_pdf
from contracts.extraction import extract_upload


def _pdf(catalog_extra: bytes = b"", extra_objects: bytes = b"") -> bytes:
    return (b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b" >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n" + extra_objects +
            b"trailer\n<< /Root 1 0 R >>\n%%EOF\n")


def _stream(n: int, body: bytes, extra: bytes = b"") -> bytes:
    raw = zlib.compress(body)
    return b"%d 0 obj\n<< /Length %d /Filter /FlateDecode %s >>\nstream\n" % (n, len(raw), extra) + raw + b"\nendstream\nendobj\n"


def test_plain_pdf_and_links_pass():
    assert findings(_pdf()) == []
    assert findings(_pdf(b"/OpenAction [3 0 R /Fit]")) == []  # opening at a page is fine
    assert findings(_pdf(extra_objects=b"4 0 obj\n<< /Type /Annot /Subtype /Link /A << /S /URI /URI (https://example.com) >> >>\nendobj\n")) == []


@pytest.mark.parametrize("payload,reason", [
    (b"/OpenAction << /S /JavaScript /JS (app.alert(1)) >>", "JavaScript"),
    (b"/OpenAction << /S /J#61vaScript /J#53 (app.alert(1)) >>", "JavaScript"),    # hex-escaped names
    (b"/OpenAction << /S /Launch /F (cmd.exe) >>", "launch"),
    (b"/Names << /EmbeddedFiles 9 0 R >>", "embedded files"),
    (b"/AcroForm << /XFA 9 0 R >>", "XFA"),
    (b"/AA << /O << /S /SubmitForm /F (https://x.test) >> >>", "submits data"),
])
def test_active_content_is_refused(payload, reason):
    with pytest.raises(PdfRefused, match=reason):
        screen_pdf(_pdf(payload))


def test_names_hidden_in_a_compressed_object_stream_are_found():
    hidden = _stream(4, b"5 0 << /S /JavaScript /JS (this.exportDataObject()) >>", b"/Type /ObjStm /N 1 /First 4")
    assert "embedded JavaScript" in findings(_pdf(extra_objects=hidden))


def test_encrypted_and_bomb_pdfs_are_refused():
    assert findings(_pdf(extra_objects=b"9 0 obj\n<< /Filter /Standard /V 2 >>\nendobj\n").replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 9 0 R"))
    bomb = _stream(4, b"\0" * 30_000_000)
    assert "screening limit" in findings(_pdf(extra_objects=bomb))[0]


def test_contract_upload_and_evidence_vault_use_the_screen(tmp_path):
    with pytest.raises(ValueError, match="PDF refused"):
        extract_upload("contract.pdf", _pdf(b"/OpenAction << /S /JavaScript /JS (x) >>"))
    from workspace.evidence_vault import EvidenceVault, VaultError
    vault = EvidenceVault(tmp_path, b"k" * 32)
    with pytest.raises(VaultError, match="launch"):
        vault.store("t1", "case-1", "REQ-1", "invoice.pdf", _pdf(b"/OpenAction << /S /Launch /F (a) >>"), "sme.lan")
    assert vault.store("t1", "case-1", "REQ-1", "invoice.pdf", _pdf(), "sme.lan")["mime"] == "application/pdf"


def test_real_pdf_made_by_a_pdf_library_passes():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Invoice INV-1188 USD 260,000")
    assert findings(doc.tobytes(deflate=True)) == []
    doc.embfile_add("payload.exe", b"MZ...")
    assert "embedded files" in findings(doc.tobytes(deflate=True)) or "an embedded file" in findings(doc.tobytes(deflate=True))
