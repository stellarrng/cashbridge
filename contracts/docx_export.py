"""Formatted, UNSIGNED Word export of a contract draft (no e-signing).

Renders the document model from contracts/drafting.py: A4, Times New Roman, justified articles with numbered
sub-clauses, a parties block, the payment-schedule table with totals, signature blocks, a header that says
"DRAFT FOR LEGAL REVIEW - NOT SIGNED" on every page, "Page X of Y" in the footer, a diagonal DRAFT watermark and a
boxed review notice on page one. Bilingual drafts are set as an English | Vietnamese two-column table so each clause
sits next to its translation, the way bilingual contracts are signed in Vietnam.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

from contracts.drafting import draft

FONT = "Times New Roman"
INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x59, 0x59, 0x59)
ACCENT = RGBColor(0x1F, 0x3A, 0x5F)
HEADER_FILL = "DCE3EC"
NOTICE_FILL = "FFF4E5"


# --------------------------------------------------------------------------- low-level helpers
def _shade(cell, fill: str) -> None:
    cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill}"/>'))


def _borders(table, color: str = "8C8C8C", size: int = 4, inside: bool = True) -> None:
    tbl_pr = table._tbl.tblPr
    edges = ["top", "left", "bottom", "right"] + (["insideH", "insideV"] if inside else [])
    xml = "".join(f'<w:{e} w:val="single" w:sz="{size}" w:space="0" w:color="{color}"/>' for e in edges)
    tbl_pr.append(parse_xml(f'<w:tblBorders {nsdecls("w")}>{xml}</w:tblBorders>'))


def _no_borders(table) -> None:
    xml = "".join(f'<w:{e} w:val="nil"/>' for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
    table._tbl.tblPr.append(parse_xml(f'<w:tblBorders {nsdecls("w")}>{xml}</w:tblBorders>'))


def _widths(table, cms: List[float]) -> None:
    table.autofit = False
    grid = table._tbl.tblGrid
    for i, col in enumerate(grid.findall(qn("w:gridCol"))):
        col.set(qn("w:w"), str(int(Cm(cms[i]).twips)))
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            cell.width = Cm(cms[i])


def _repeat_header(row) -> None:
    row._tr.get_or_add_trPr().append(parse_xml(f'<w:tblHeader {nsdecls("w")} w:val="true"/>'))


def _keep_row(row) -> None:
    row._tr.get_or_add_trPr().append(parse_xml(f'<w:cantSplit {nsdecls("w")} w:val="true"/>'))


def _field(paragraph, instr: str) -> None:
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, None), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
            run._r.append(el)
        elif text:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = f" {text} "
            run._r.append(el)
        else:
            t = OxmlElement("w:t")
            t.text = "1"
            run._r.append(t)
    run.font.size = Pt(8.5)
    run.font.color.rgb = MUTED


def _para(container, text: str = "", *, bold=False, italic=False, size=None, color=None, align=None,
          before=0, after=4, indent=None, hanging=None, keep_next=False, caps=False):
    p = container.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before, fmt.space_after = Pt(before), Pt(after)
    if align is not None:
        fmt.alignment = align
    if indent is not None:
        fmt.left_indent = Cm(indent)
    if hanging is not None:
        fmt.first_line_indent = Cm(-hanging)
    fmt.keep_with_next = keep_next
    if text:
        r = p.add_run(text)
        r.bold, r.italic, r.font.all_caps = bold, italic, caps
        if size:
            r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
    return p


def _clause(container, no: str, text: str, size: float = 11) -> None:
    p = _para(container, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=5, indent=1.1, hanging=1.1)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(1.1))
    r = p.add_run(f"{no}\t")
    r.bold = True
    r.font.size = Pt(size)
    r2 = p.add_run(text)
    r2.font.size = Pt(size)


def _cell_text(cell, text: str, *, bold=False, size=10, align=None, color=None) -> None:
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(1)
    if align is not None:
        p.alignment = align
    r = p.add_run(text)
    r.bold, r.font.size = bold, Pt(size)
    if color is not None:
        r.font.color.rgb = color


def _watermark(section) -> None:
    """Diagonal light-grey DRAFT behind the text of every page (VML text path, as Word itself writes it)."""
    header = section.header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    run = p.add_run()
    pict = parse_xml(
        '<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
        '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" path="m@7,l@8,m@5,21600l@6,21600e">'
        '<v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/>'
        '<v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/>'
        '<v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/>'
        '<v:f eqn="sum @6 0 @5"/></v:formulas><v:path textpathok="t" o:connecttype="custom" '
        'o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/>'
        '<v:textpath on="t" fitshape="t"/><o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>'
        '<v:shape id="CashBridgeDraftWatermark" o:spid="_x0000_s1025" type="#_x0000_t136" '
        'style="position:absolute;margin-left:0;margin-top:0;width:470pt;height:117pt;rotation:315;z-index:-251654144;'
        'mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;'
        'mso-position-vertical-relative:margin" o:allowincell="f" fillcolor="#d9d9d9" stroked="f">'
        '<v:fill opacity=".45"/><v:textpath style="font-family:&quot;Times New Roman&quot;;font-size:1pt" string="DRAFT"/>'
        '</v:shape></w:pict>')
    run._r.append(pict)


# --------------------------------------------------------------------------- document parts
def _setup(doc: Document, result: Dict[str, Any], lang: str) -> None:
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = FONT, Pt(11)
    normal.font.color.rgb = INK
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.line_spacing = 1.12
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
    sec.left_margin, sec.right_margin = Cm(2.5), Cm(2.0)
    sec.header_distance = sec.footer_distance = Cm(1.0)

    vi = lang == "vi"
    head = sec.header.paragraphs[0]
    head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = head.add_run({"vi": f"Hợp đồng số {result['contract_no']}  ·  BẢN DỰ THẢO ĐỂ RÀ SOÁT PHÁP LÝ  ·  CHƯA KÝ",
                      "en": f"Contract No. {result['contract_no']}  ·  DRAFT FOR LEGAL REVIEW  ·  NOT SIGNED",
                      "bilingual": f"Số / No. {result['contract_no']}  ·  DỰ THẢO / DRAFT FOR LEGAL REVIEW  ·  CHƯA KÝ / NOT SIGNED"}[lang])
    r.font.size, r.font.color.rgb = Pt(8.5), MUTED
    _watermark(sec)

    foot = sec.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for label, instr in ((("Trang " if vi else "Trang / Page " if lang == "bilingual" else "Page "), "PAGE"),
                         ((" / " if lang != "en" else " of "), "NUMPAGES")):
        lr = foot.add_run(label)
        lr.font.size, lr.font.color.rgb = Pt(8.5), MUTED
        _field(foot, instr)
    tail = foot.add_run("   ·   " + {"vi": "Bên A ký nháy ____   Bên B ký nháy ____", "en": "Initials: Party A ____   Party B ____",
                                     "bilingual": "Ký nháy / Initials: Bên A ____   Bên B ____"}[lang])
    tail.font.size, tail.font.color.rgb = Pt(8.5), MUTED

    props = doc.core_properties
    title = result["document"]["title"]
    props.title = f"{title['en']} {result['contract_no']} (UNSIGNED DRAFT)"
    props.subject = "Unsigned contract draft for legal review"
    props.author = "CashBridge contract drafting (fixed clause library)"
    props.keywords = "DRAFT; NOT SIGNED; LEGAL REVIEW REQUIRED; SYNTHETIC DEMO"
    props.comments = "Generated from user-entered data. Not legal advice. Not signed."
    props.created = datetime.now(timezone.utc).replace(tzinfo=None)


def _notice(doc: Document, texts: List[str]) -> None:
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _borders(t, color="C77700", size=8, inside=False)
    cell = t.cell(0, 0)
    _shade(cell, NOTICE_FILL)
    for i, text in enumerate(texts):
        if i:
            cell.add_paragraph()
        p = cell.paragraphs[i]
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(text)
        r.font.size, r.font.color.rgb, r.italic = Pt(9), RGBColor(0x5C, 0x37, 0x00), i > 0
    _para(doc, after=6)


def _title_block(doc: Document, d: Dict[str, Any], lang: str) -> None:
    if lang in ("vi", "bilingual"):
        _para(doc, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", bold=True, size=11.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
        _para(doc, "Độc lập - Tự do - Hạnh phúc", bold=True, size=11.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
        _para(doc, "———————", align=WD_ALIGN_PARAGRAPH.CENTER, after=10, color=MUTED)
    titles = [d["title"]["vi"], d["title"]["en"]] if lang == "bilingual" else [d["title"]["vi" if lang == "vi" else "en"]]
    _para(doc, titles[0], bold=True, size=17, color=ACCENT, align=WD_ALIGN_PARAGRAPH.CENTER, after=0, before=4)
    if len(titles) > 1:
        _para(doc, titles[1], bold=True, italic=True, size=12.5, color=ACCENT, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    for L in (("vi", "en") if lang == "bilingual" else ("vi" if lang == "vi" else "en",)):
        _para(doc, d["meta"][L], size=10, color=MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, after=0, italic=L == "en" and lang == "bilingual")
    _para(doc, after=8)


def _txt(x: Any, lang: str) -> str:
    """One string for EN/VI output; 'EN / VI' only where a bilingual value has to fit one cell."""
    if not isinstance(x, dict):
        return str(x)
    if lang == "bilingual":
        return x["vi"] if x["vi"] == x["en"] else f"{x['vi']} / {x['en']}"
    return x[lang]


def _parties(doc: Document, d: Dict[str, Any], lang: str) -> None:
    _para(doc, {"en": "THE PARTIES", "vi": "CÁC BÊN", "bilingual": "CÁC BÊN / THE PARTIES"}[lang], bold=True, size=11.5,
          color=ACCENT, keep_next=True, after=4)
    for party in d["parties"]:
        t = doc.add_table(rows=1 + len(party["rows"]), cols=2)
        _borders(t, color="BFBFBF")
        _widths(t, [5.2, 11.3])
        head = t.rows[0].cells
        merged = head[0].merge(head[1])
        _shade(merged, HEADER_FILL)
        _cell_text(merged, f"{_txt(party['role'], lang)}: ", bold=True, size=10, color=ACCENT)
        r = merged.paragraphs[0].add_run(party["name"])
        r.bold, r.font.size = True, Pt(10.5)
        for i, (label, value) in enumerate(party["rows"], start=1):
            _cell_text(t.cell(i, 0), _txt(label, lang), size=9.5, color=MUTED)
            _cell_text(t.cell(i, 1), value, size=10)
        for row in t.rows:
            _keep_row(row)
        _para(doc, after=6)


def _recitals(doc: Document, d: Dict[str, Any], lang: str) -> None:
    heading = {"en": "RECITALS", "vi": "XÉT RẰNG", "bilingual": "XÉT RẰNG / RECITALS"}[lang]
    _para(doc, heading, bold=True, size=11.5, color=ACCENT, keep_next=True, after=4)
    if lang == "bilingual":
        _bilingual_rows(doc, [(f"({chr(65 + i)})", r) for i, r in enumerate(d["recitals"])])
    else:
        for i, r in enumerate(d["recitals"]):
            _clause(doc, f"({chr(65 + i)})", r[lang])
    _para(doc, after=4)


def _bilingual_rows(doc: Document, rows: List[tuple], heading: Dict[str, str] | None = None) -> None:
    t = doc.add_table(rows=0, cols=2)
    _no_borders(t)
    if heading:
        cells = t.add_row().cells
        for i, L in enumerate(("vi", "en")):
            _cell_text(cells[i], heading[L], bold=True, size=10.5, color=ACCENT)
            cells[i].paragraphs[0].paragraph_format.keep_with_next = True
        _keep_row(t.rows[-1])
    for no, text in rows:
        cells = t.add_row().cells
        for i, L in enumerate(("vi", "en")):
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(f"{no} ")
            r.bold, r.font.size = True, Pt(9.5)
            r2 = p.add_run(text[L])
            r2.font.size = Pt(9.5)
            if L == "en":
                r2.italic = True
        _keep_row(t.rows[-1])
    _widths(t, [8.25, 8.25])


def _articles(doc: Document, d: Dict[str, Any], lang: str) -> None:
    for a in d["articles"]:
        if lang == "bilingual":
            _bilingual_rows(doc, [(c["no"], c["text"]) for c in a["clauses"]],
                            heading={"vi": f"ĐIỀU {a['no']}. {a['title']['vi']}", "en": f"ARTICLE {a['no']}. {a['title']['en']}"})
            _para(doc, after=3)
            continue
        label = "ĐIỀU" if lang == "vi" else "ARTICLE"
        _para(doc, f"{label} {a['no']}.  {a['title'][lang]}", bold=True, size=11.5, color=ACCENT, before=8, after=4, keep_next=True)
        for c in a["clauses"]:
            _clause(doc, c["no"], c["text"][lang])


def _schedule_table(doc: Document, table: Dict[str, Any], lang: str) -> None:
    header, rows, total = table["header"], table["rows"], table["total"]
    t = doc.add_table(rows=1, cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _borders(t)
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        _shade(cell, HEADER_FILL)
        _cell_text(cell, _txt(h, lang), bold=True, size=9.5, color=ACCENT,
                   align=WD_ALIGN_PARAGRAPH.CENTER)
    _repeat_header(t.rows[0])
    right = {2, 3}
    num = lambda v: v["vi" if lang == "vi" else "en"] if isinstance(v, dict) else v  # noqa: E731  amounts: one format per cell
    for row in rows:
        cells = t.add_row().cells
        for i, value in enumerate(row):
            _cell_text(cells[i], num(value) if i == 3 else _txt(value, lang), size=9.5,
                       align=WD_ALIGN_PARAGRAPH.RIGHT if i in right else (WD_ALIGN_PARAGRAPH.CENTER if i == 0 else None))
        _keep_row(t.rows[-1])
    cells = t.add_row().cells
    label = cells[0].merge(cells[1])
    _cell_text(label, _txt(total[0], lang), bold=True, size=9.5)
    _cell_text(cells[2], total[1], bold=True, size=9.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _cell_text(cells[3], num(total[2]), bold=True, size=9.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
    for c in cells:
        _shade(c, "F2F2F2")
    _widths(t, [1.2, 6.0, 1.6, 3.6, 4.1])
    _para(doc, after=4)


def _schedules(doc: Document, d: Dict[str, Any], lang: str) -> None:
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    for s in d["schedules"]:
        if lang == "bilingual":
            heads = [f"PHỤ LỤC {s['no']}. {s['title']['vi']}", f"SCHEDULE {s['no']}. {s['title']['en']}"]
        else:
            heads = [f"{'PHỤ LỤC' if lang == 'vi' else 'SCHEDULE'} {s['no']}.  {s['title'][lang]}"]
        _para(doc, heads[0], bold=True, size=12, color=ACCENT, before=10, after=0 if len(heads) > 1 else 6, keep_next=True)
        if len(heads) > 1:
            _para(doc, heads[1], bold=True, italic=True, size=10.5, color=ACCENT, after=6, keep_next=True)
        if "table" in s:
            _schedule_table(doc, s["table"], lang)
        for i, item in enumerate(s.get("items", []), start=1):
            if lang == "bilingual" and item["en"] != item["vi"]:
                _clause(doc, f"{i}.", item["vi"], size=10.5)
                p = _para(doc, item["en"], italic=True, size=10, color=MUTED, indent=1.1, after=5, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
                p.paragraph_format.keep_together = True
            else:
                _clause(doc, f"{i}.", item["vi" if lang == "vi" else "en"] if lang != "bilingual" else item["vi"], size=10.5)


def _signatures(doc: Document, d: Dict[str, Any], lang: str) -> None:
    _para(doc, after=6)
    intro = {"en": "IN WITNESS WHEREOF the parties have caused this Contract to be signed by their authorised representatives.",
             "vi": "Để làm bằng chứng, đại diện có thẩm quyền của hai bên ký Hợp đồng này.",
             "bilingual": "Để làm bằng chứng, đại diện có thẩm quyền của hai bên ký Hợp đồng này. / IN WITNESS WHEREOF the parties have "
                          "caused this Contract to be signed by their authorised representatives."}[lang]
    _para(doc, intro, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=10, keep_next=True, size=10.5)
    t = doc.add_table(rows=1, cols=2)
    _no_borders(t)
    _keep_row(t.rows[0])
    for i, s in enumerate(d["signatures"]):
        cell = t.cell(0, i)
        _cell_text(cell, _txt(s["role"], lang), bold=True, size=10.5, color=ACCENT, align=WD_ALIGN_PARAGRAPH.CENTER)
        lines = [(s["name"], True, 10.5), ("", False, 10), ("", False, 10), ("", False, 10),
                 ("_______________________________", False, 10),
                 (s["person"] or ("Họ tên: [●]" if lang == "vi" else "Name: [●]"), False, 10),
                 (s["title"] or ("Chức vụ: [●]" if lang == "vi" else "Title: [●]"), False, 10),
                 ({"en": "Date: [●]   Company seal: [●]", "vi": "Ngày: [●]   Đóng dấu: [●]",
                   "bilingual": "Ngày / Date: [●]   Dấu / Seal: [●]"}[lang], False, 9),
                 ({"en": "NOT SIGNED", "vi": "CHƯA KÝ", "bilingual": "CHƯA KÝ / NOT SIGNED"}[lang], True, 9)]
        for text, bold, size in lines:
            p = cell.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(1)
            r = p.add_run(text)
            r.bold, r.font.size = bold, Pt(size)
            if text in ("NOT SIGNED", "CHƯA KÝ", "CHƯA KÝ / NOT SIGNED"):
                r.font.color.rgb = RGBColor(0xB0, 0x2A, 0x2A)
    _widths(t, [8.25, 8.25])


def _review_page(doc: Document, result: Dict[str, Any], lang: str) -> None:
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    sec.header.is_linked_to_previous = sec.footer.is_linked_to_previous = True
    d = result["document"]

    def pick(x: Dict[str, str]) -> List[str]:
        return [x["vi"], x["en"]] if lang == "bilingual" else [x[lang]]

    def heading(vi: str, en: str, size: float = 11, after: int = 3, before: int = 6) -> None:
        for i, text in enumerate(pick({"vi": vi, "en": en})):
            _para(doc, text, bold=i == 0, italic=i > 0, size=size if i == 0 else size - 1, color=ACCENT if size > 11 else None,
                  keep_next=True, after=after if i == len(pick({"vi": vi, "en": en})) - 1 else 0, before=before if i == 0 else 0)

    heading("DANH MỤC RÀ SOÁT TRƯỚC KHI KÝ", "PRE-SIGNATURE REVIEW CHECKLIST", size=12.5, after=2, before=0)
    for text in pick({"vi": "Trang này không thuộc Hợp đồng. Xóa trang này sau khi đã hoàn tất mọi mục.",
                      "en": "This page is not part of the Contract. Remove it once every item is resolved."}):
        _para(doc, text, italic=True, size=9.5, color=MUTED, after=0)
    _para(doc, after=6)
    groups = [(("Thông tin còn thiếu", "Information still missing"), [x for x in d["open_items_detail"] if x["kind"] == "missing"], ("Bổ sung: ", "Enter: ")),
              (("Giá trị mặc định đề xuất cần xác nhận", "Proposed defaults to confirm"), [x for x in d["open_items_detail"] if x["kind"] == "default"],
               ("Xác nhận: ", "Confirm: ")),
              (("Kiểm tra bắt buộc", "Mandatory checks"), d["checklist"], ("", ""))]
    for (vi_title, en_title), items, (vi_pre, en_pre) in groups:
        if not items:
            continue
        heading(vi_title, en_title)
        for item in items:
            texts = pick({"vi": vi_pre + item["vi"], "en": en_pre + item["en"]})
            p = _para(doc, after=2, indent=0.8, hanging=0.6)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(0.8))
            r = p.add_run("☐\t" + texts[0])
            r.font.size = Pt(10.5)
            if len(texts) > 1:
                r2 = p.add_run("  /  " + texts[1])
                r2.italic, r2.font.size, r2.font.color.rgb = True, Pt(9.5), MUTED
    _para(doc, after=8)
    en_note = ("LEGAL REVIEW REQUIRED. NOT SIGNED. CashBridge does not give legal advice and does not sign documents; "
               "a qualified lawyer must approve this draft before it is used.")
    vi_note = ("BẮT BUỘC RÀ SOÁT PHÁP LÝ. CHƯA KÝ. CashBridge không tư vấn pháp lý và không ký văn bản; luật sư có chuyên môn phải "
               "phê duyệt bản dự thảo này trước khi sử dụng.")
    _notice(doc, {"en": [en_note], "vi": [vi_note, "LEGAL REVIEW REQUIRED · NOT SIGNED"], "bilingual": [vi_note, en_note]}[lang])


def render(result: Dict[str, Any]) -> bytes:
    d, lang = result["document"], result["language"]
    doc = Document()
    _setup(doc, result, lang)
    _notice(doc, [d["notice"]["vi"], d["notice"]["en"]] if lang == "bilingual" else [d["notice"][lang]])
    _title_block(doc, d, lang)
    _parties(doc, d, lang)
    _recitals(doc, d, lang)
    _articles(doc, d, lang)
    _signatures(doc, d, lang)
    _schedules(doc, d, lang)
    _review_page(doc, result, lang)
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


def draft_docx_bytes(data: dict[str, Any]) -> bytes:
    """Validate the input, build the clause-library draft and return a formatted .docx (never signed)."""
    return render(draft(data))  # enforces term count, parties, monetary math and bounded text
