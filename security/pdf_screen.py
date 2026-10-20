"""PDF active-content screen (Security Self-Assessment risk 04: a malicious document reaches the lender).

An invoice, bill of lading or contract has no reason to carry scripts, launch actions, embedded files or forms that
submit data. Before a PDF is read (contract upload) or stored for a lender (evidence vault), its object syntax is
scanned WITHOUT rendering or executing anything:

* names are decoded first (``/J#61vaScript`` is ``/JavaScript``), so hex-escaped names do not slip through;
* Flate-compressed streams, including object streams (``/ObjStm``) where dictionaries can hide, are inflated with a
  hard output cap (a decompression bomb is refused, not expanded);
* encrypted PDFs are refused, because their streams cannot be screened.

Refused: /JavaScript, /JS, /Launch, /EmbeddedFile(s), /RichMedia, /XFA, /AA (automatic actions), /SubmitForm,
/ImportData, /GoToE, /GoToR. Allowed: ordinary links (/URI) and /OpenAction that only opens a page.

This is a screen, not an antivirus: it removes the active-content classes above; it cannot prove a file is harmless
(for example a malformed file aimed at a viewer bug). The lender still opens files only through the sandboxed viewer.
"""

from __future__ import annotations

import re
import zlib
from typing import List

DANGEROUS = {
    "JavaScript": "embedded JavaScript", "JS": "embedded JavaScript", "Launch": "a launch (run program) action",
    "EmbeddedFile": "an embedded file", "EmbeddedFiles": "embedded files", "RichMedia": "rich media (Flash/video)",
    "XFA": "an XFA dynamic form", "AA": "automatic actions", "SubmitForm": "a form that submits data",
    "ImportData": "a data-import action", "GoToE": "a jump into an embedded file", "GoToR": "a jump to another file",
}
_NAME = re.compile(rb"/([A-Za-z0-9#_.+-]{1,64})")
_STREAM = re.compile(rb"stream\r?\n")
MAX_INFLATED = 25_000_000   # total bytes inflated per file
MAX_STREAMS = 5_000


class PdfRefused(ValueError):
    pass


def _decode(name: bytes) -> str:
    return re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), name).decode("latin-1")


def _names(chunk: bytes) -> set:
    return {_decode(m.group(1)) for m in _NAME.finditer(chunk)}


def findings(data: bytes) -> List[str]:
    """Reasons to refuse this PDF (empty list = no active content found)."""
    if not data.startswith(b"%PDF-"):
        return []
    found = set()
    names = _names(data)
    if "Encrypt" in names:
        return ["encryption (an encrypted PDF cannot be screened; save it without a password)"]
    budget = MAX_INFLATED
    for count, m in enumerate(_STREAM.finditer(data)):
        if count >= MAX_STREAMS:
            return ["too many streams to screen"]
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            break
        try:
            d = zlib.decompressobj()
            out = d.decompress(data[start:end], budget + 1)
        except zlib.error:
            continue  # not Flate (image, DCT...) or damaged: its raw bytes were already scanned
        if len(out) > budget:
            return ["a compressed stream that inflates beyond the screening limit"]
        budget -= len(out)
        names |= _names(out)
    for n in names:
        if n in DANGEROUS:
            found.add(DANGEROUS[n])
    return sorted(found)


def screen_pdf(data: bytes) -> None:
    """Raise PdfRefused with a user-readable reason when the PDF carries active content."""
    reasons = findings(data)
    if reasons:
        raise PdfRefused("PDF refused: it contains " + "; ".join(reasons) +
                         ". Print it to a new PDF (or export the pages as images) and upload that instead.")
