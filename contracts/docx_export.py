"""Safe, unsigned Word export of a validated contract draft (no e-signing)."""
from __future__ import annotations

from io import BytesIO
from typing import Any
from docx import Document
from docx.shared import Inches, Pt
from contracts.intelligence import draft


def draft_docx_bytes(data: dict[str,Any]) -> bytes:
    result = draft(data)  # enforces term count, parties, monetary math and bounded text
    doc=Document()
    section=doc.sections[0]
    section.top_margin=Inches(.8)
    section.bottom_margin=Inches(.8)
    doc.styles['Normal'].font.name='Calibri'
    doc.styles['Normal'].font.size=Pt(10)
    doc.add_heading('CASHBRIDGE · UNSIGNED CONTRACT DRAFT',level=0)
    doc.add_paragraph('SYNTHETIC DEMONSTRATION · HUMAN LEGAL REVIEW REQUIRED',style='Subtitle')
    for block in result['draft'].split('\n\n'):
        first,*rest=block.split('\n')
        if first[:2].rstrip('.').isdigit() or (first and first[0].isdigit() and '. ' in first[:4]):
            doc.add_heading(first,level=2)
            for item in rest:
                doc.add_paragraph(item)
        else:
            for line in [first,*rest]:doc.add_paragraph(line)
    doc.add_heading('Mandatory review before any use',level=2)
    for item in result['review_checklist']:
        doc.add_paragraph(item,style='List Bullet')
    doc.add_paragraph('NOT SIGNED · No clause has been reviewed or approved by legal counsel.')
    stream=BytesIO();doc.save(stream)
    return stream.getvalue()
