"""Typesetting kit for the CashBridge technical documentation (ReportLab).

The document is written as a list of blocks (docs/technical/content.py). Pass 1 numbers sections, equations, tables
and figures and records labels; pass 2 renders, replacing [[label]] in any text with the number it resolves to, so
cross-references stay right when a section is inserted. Layout follows the v9 documentation: A4, a Times-metric
serif, running head with a rule, booktabs-style tables, numbered display equations and captions below floats.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, Image, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = Path(__file__).resolve().parent
LIB = Path("/usr/share/fonts/truetype/liberation")


def _fonts() -> None:
    faces = {"Serif": "LiberationSerif-Regular.ttf", "Serif-Bold": "LiberationSerif-Bold.ttf", "Serif-Italic": "LiberationSerif-Italic.ttf",
             "Serif-BoldItalic": "LiberationSerif-BoldItalic.ttf", "Mono": "LiberationMono-Regular.ttf", "Mono-Bold": "LiberationMono-Bold.ttf"}
    for name, file in faces.items():
        pdfmetrics.registerFont(TTFont(name, str(LIB / file)))
    pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="Serif-Bold", italic="Serif-Italic", boldItalic="Serif-BoldItalic")
    pdfmetrics.registerFontFamily("Mono", normal="Mono", bold="Mono-Bold", italic="Mono", boldItalic="Mono-Bold")


_fonts()
INK, GREY, RULE = colors.HexColor("#111111"), colors.HexColor("#555555"), colors.HexColor("#222222")
PAGE_W, PAGE_H = A4
LM, RM, TM, BM = 25 * mm, 25 * mm, 27 * mm, 22 * mm
TEXT_W = PAGE_W - LM - RM

ST = {
    "body": ParagraphStyle("body", fontName="Serif", fontSize=10.6, leading=14.6, alignment=TA_JUSTIFY, spaceAfter=5, textColor=INK),
    "h1": ParagraphStyle("h1", fontName="Serif-Bold", fontSize=17, leading=21, spaceBefore=14, spaceAfter=7, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Serif-Bold", fontSize=12.6, leading=16, spaceBefore=9, spaceAfter=4, keepWithNext=1),
    "h1u": ParagraphStyle("h1u", fontName="Serif-Bold", fontSize=17, leading=21, spaceBefore=6, spaceAfter=10, keepWithNext=1),
    "cell": ParagraphStyle("cell", fontName="Serif", fontSize=9.3, leading=11.6, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="Serif-Bold", fontSize=9.3, leading=11.6, textColor=INK),
    "cap": ParagraphStyle("cap", fontName="Serif", fontSize=9.2, leading=11.8, alignment=TA_JUSTIFY, spaceBefore=3, spaceAfter=9, textColor=INK),
    "eq": ParagraphStyle("eq", fontName="Serif", fontSize=10.6, leading=14, alignment=TA_CENTER),
    "eqn": ParagraphStyle("eqn", fontName="Serif", fontSize=10.6, leading=14, alignment=2),
    "bullet": ParagraphStyle("bullet", fontName="Serif", fontSize=10.6, leading=14.4, alignment=TA_JUSTIFY, leftIndent=14, bulletIndent=3, spaceAfter=3),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8.6, leading=11.2, leftIndent=8, spaceBefore=2, spaceAfter=6),
    "ref": ParagraphStyle("ref", fontName="Serif", fontSize=9.4, leading=12, leftIndent=20, firstLineIndent=-20, spaceAfter=3.2),
    "toc0": ParagraphStyle("toc0", fontName="Serif-Bold", fontSize=10.6, leading=13, leftIndent=0, spaceBefore=7),
    "toc1": ParagraphStyle("toc1", fontName="Serif", fontSize=10.2, leading=12.6, leftIndent=16, spaceBefore=3.6),
}


# --------------------------------------------------------------------------- diagrams (vector, same look as v9)
class Diagram(Flowable):
    """Boxes and arrows drawn at a fixed scale: nodes {id: (x, y, w, h, text, shaded)}, edges [(a, b, label)]."""

    def __init__(self, width: float, height: float, nodes: Dict[str, Tuple], edges: List[Tuple], title: str = "") -> None:
        super().__init__()
        self.width, self.height, self.nodes, self.edges, self.title = width, height, nodes, edges, title

    def wrap(self, aw, ah):
        return self.width, self.height

    def _anchor(self, n, toward):
        x, y, w, h = n[:4]
        cx, cy = x + w / 2, y + h / 2
        tx, ty = toward
        dx, dy = tx - cx, ty - cy
        if dx == 0 and dy == 0:
            return cx, cy
        sx = (w / 2) / abs(dx) if dx else 1e9
        sy = (h / 2) / abs(dy) if dy else 1e9
        s = min(sx, sy)
        return cx + dx * s, cy + dy * s

    def draw(self):
        c = self.canv
        if self.title:
            c.setFont("Serif-Bold", 9); c.drawString(0, self.height - 9, self.title)
        for nid, (x, y, w, h, text, shaded) in self.nodes.items():
            c.setFillColor(colors.HexColor("#f2f2f2") if shaded else colors.white)
            c.setStrokeColor(INK); c.setLineWidth(0.8)
            c.rect(x, y, w, h, stroke=1, fill=1)
            c.setFillColor(INK); c.setFont("Serif", 8.6)
            lines = text.split("\n")
            for i, line in enumerate(lines):
                c.drawCentredString(x + w / 2, y + h / 2 + (len(lines) / 2 - i - 0.75) * 10.2, line)
        for a, b, label in self.edges:
            na, nb = self.nodes[a], self.nodes[b]
            ca = (na[0] + na[2] / 2, na[1] + na[3] / 2); cb = (nb[0] + nb[2] / 2, nb[1] + nb[3] / 2)
            x1, y1 = self._anchor(na, cb); x2, y2 = self._anchor(nb, ca)
            _arrow(c, x1, y1, x2, y2)
            if label:
                c.setFont("Serif-Italic", 8); c.setFillColor(GREY)
                c.drawCentredString((x1 + x2) / 2, (y1 + y2) / 2 + 3, label); c.setFillColor(INK)


def _arrow(c, x1, y1, x2, y2, size=4.2):
    import math
    c.setStrokeColor(INK); c.setLineWidth(0.8); c.line(x1, y1, x2, y2)
    ang = math.atan2(y2 - y1, x2 - x1)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - size * math.cos(ang - 0.38) * 1.6, y2 - size * math.sin(ang - 0.38) * 1.6)
    p.lineTo(x2 - size * math.cos(ang + 0.38) * 1.6, y2 - size * math.sin(ang + 0.38) * 1.6)
    p.close(); c.setFillColor(INK); c.drawPath(p, stroke=0, fill=1)


class Sequence(Flowable):
    """Sequence diagram: actors across the top, messages (src, dst, text) top to bottom; text in italics."""

    def __init__(self, width: float, actors: List[str], messages: List[Tuple[int, int, str]], step: float = 21) -> None:
        super().__init__()
        self.width, self.actors, self.messages, self.step = width, actors, messages, step
        self.height = 36 + step * len(messages) + 8

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        n = len(self.actors)
        bw = min(118, self.width / n - 14)
        xs = [self.width * (i + 0.5) / n for i in range(n)]
        top = self.height
        for x, name in zip(xs, self.actors):
            c.setFillColor(colors.HexColor("#f2f2f2")); c.setStrokeColor(INK); c.setLineWidth(0.8)
            c.rect(x - bw / 2, top - 24, bw, 22, stroke=1, fill=1)
            c.setFillColor(INK); c.setFont("Serif-Bold", 9); c.drawCentredString(x, top - 16, name)
            c.setDash(2, 2); c.setStrokeColor(GREY); c.line(x, top - 24, x, 2); c.setDash()
        for i, (a, b, text) in enumerate(self.messages):
            y = top - 24 - self.step * (i + 1)
            _arrow(c, xs[a], y, xs[b] + (-1 if b > a else 1), y)
            c.setFont("Serif-Italic", 8.6); c.setFillColor(INK)
            tx = min(xs[a], xs[b]) + 6
            c.drawString(tx, y + 3.5, text)


# --------------------------------------------------------------------------- document
class _Doc(BaseDocTemplate):
    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and getattr(f, "_toc", None) is not None:
            level, text, key = f._toc
            self.notify("TOCEntry", (level, text, self.page, key))


def _decor(canvas, doc):
    canvas.saveState()
    canvas.setFont("Serif-Italic", 8.6); canvas.setFillColor(GREY)
    canvas.drawString(LM, PAGE_H - 15 * mm, "CashBridge: Technical Documentation (v9.1)")
    canvas.drawRightString(PAGE_W - RM, PAGE_H - 15 * mm, "FinTechathon Shenzhen 2026, Topic E")
    canvas.setStrokeColor(colors.HexColor("#9a9a9a")); canvas.setLineWidth(0.5)
    canvas.line(LM, PAGE_H - 16.6 * mm, PAGE_W - RM, PAGE_H - 16.6 * mm)
    canvas.setFont("Serif", 9.4); canvas.setFillColor(INK)
    canvas.drawCentredString(PAGE_W / 2, 11 * mm, str(doc.page))
    canvas.restoreState()


class Builder:
    """Two-pass renderer for the block list."""

    def __init__(self, blocks: List[Tuple]) -> None:
        self.blocks = blocks
        self.labels: Dict[str, str] = {}

    # pass 1 -------------------------------------------------------------
    def number(self) -> None:
        s1 = s2 = eq = tab = fig = 0
        app = None
        for b in self.blocks:
            kind = b[0]
            if kind == "appendix":
                app = True
            if kind == "h1":
                if len(b) > 3 and b[3]:
                    continue  # unnumbered (References, appendices)
                s1 += 1; s2 = 0
                if len(b) > 2 and b[2]:
                    self.labels[b[2]] = str(s1)
            elif kind == "h2":
                s2 += 1
                if len(b) > 2 and b[2]:
                    self.labels[b[2]] = f"{s1}.{s2}"
            elif kind == "eq":
                eq += 1
                if len(b) > 2 and b[2]:
                    self.labels[b[2]] = str(eq)
            elif kind == "table":
                tab += 1
                if b[4]:
                    self.labels[b[4]] = str(tab)
            elif kind in ("fig", "figpair", "diagram", "sequence"):
                fig += 1
                lab = b[-1]
                if lab:
                    self.labels[lab] = str(fig)

    def r(self, text: str) -> str:
        def sub(m):
            key = m.group(1)
            if key not in self.labels:
                raise KeyError(f"unknown label {key}")
            return self.labels[key]
        return re.sub(r"\[\[([a-z0-9_:\-]+)\]\]", sub, text)

    # pass 2 -------------------------------------------------------------
    def render(self, out: Path, title_page) -> None:
        self.number()
        story: List[Any] = []
        title_page(story)
        toc = TableOfContents(dotsMinLevel=0)
        toc.levelStyles = [ST["toc0"], ST["toc1"]]
        story += [Paragraph("Contents", ST["h1u"]), toc, PageBreak()]
        s1 = s2 = eq = tab = fig = 0
        for b in self.blocks:
            kind = b[0]
            if kind == "h1":
                unnum = len(b) > 3 and b[3]
                if not unnum:
                    s1 += 1; s2 = 0
                text = b[1] if unnum else f"{s1}&nbsp;&nbsp;{b[1]}"
                story.append(CondPageBreak(60 * mm))
                p = Paragraph(text, ST["h1"]); p._toc = (0, text, f"h{len(story)}")
                story.append(p)
            elif kind == "h2":
                s2 += 1
                text = f"{s1}.{s2}&nbsp;&nbsp;{b[1]}"
                p = Paragraph(text, ST["h2"]); p._toc = (1, text, f"h{len(story)}")
                story.append(p)
            elif kind == "p":
                story.append(Paragraph(self.r(b[1]), ST["body"]))
            elif kind == "bullets":
                for item in b[1]:
                    story.append(Paragraph(self.r(item), ST["bullet"], bulletText="•"))
            elif kind == "code":
                story.append(Preformatted(b[1], ST["code"]))
            elif kind == "eq":
                eq += 1
                t = Table([[Paragraph(self.r(b[1]), ST["eq"]), Paragraph(f"({eq})", ST["eqn"])]], colWidths=[TEXT_W - 34, 34])
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
                story.append(t)
            elif kind == "table":
                tab += 1
                _, header, rows, widths, _lab, caption = b
                t = self._table(header, rows, widths, f"<b>Table {tab}.</b> {self.r(caption)}")
                story.extend(t if isinstance(t, list) else [t])
            elif kind == "fig":
                fig += 1
                _, path, width, caption, _lab = b
                img = Image(str(path), width=width, height=width * _ratio(path))
                story.append(KeepTogether([Spacer(1, 4), img, Paragraph(f"<b>Figure {fig}.</b> {self.r(caption)}", ST["cap"])]))
            elif kind == "figpair":
                fig += 1
                _, left, right, caption, _lab = b
                w = (TEXT_W - 10) / 2
                ims = [Image(str(p), width=w, height=w * _ratio(p)) for p in (left, right)]
                t = Table([ims, [Paragraph("(a)", ST["eq"]), Paragraph("(b)", ST["eq"])]], colWidths=[w + 5, w + 5])
                t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
                story.append(KeepTogether([t, Paragraph(f"<b>Figure {fig}.</b> {self.r(caption)}", ST["cap"])]))
            elif kind in ("diagram", "sequence"):
                fig += 1
                flow, caption = b[1], b[2]
                story.append(KeepTogether([Spacer(1, 4), flow, Spacer(1, 4), Paragraph(f"<b>Figure {fig}.</b> {self.r(caption)}", ST["cap"])]))
            elif kind == "refs":
                for i, ref in enumerate(b[1], start=1):
                    story.append(Paragraph(f"[{i}]&nbsp;&nbsp;{ref}", ST["ref"]))
            elif kind == "pagebreak":
                story.append(PageBreak())
            elif kind == "space":
                story.append(Spacer(1, b[1]))
            elif kind == "appendix":
                pass
            else:
                raise ValueError(kind)
        doc = _Doc(str(out), pagesize=A4, leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
                   title="CashBridge: A Governed, Evidence-Carrying Agent for SME Liquidity and Financing Decisions (v9.1)",
                   author="CashBridge team", subject="Technical documentation, FinTechathon Shenzhen 2026, Topic E")
        frame = Frame(LM, BM, TEXT_W, PAGE_H - TM - BM, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        doc.addPageTemplates([PageTemplate("title", [frame]), PageTemplate("main", [frame], onPage=_decor)])
        doc.multiBuild(story)

    def _table(self, header, rows, widths, caption):
        total = sum(widths)
        ws = [TEXT_W * w / total for w in widths]
        data = [[Paragraph(h, ST["cellh"]) for h in header]] + [[Paragraph(self.r(str(c)), ST["cell"]) for c in r] for r in rows]
        t = Table(data, colWidths=ws, repeatRows=1)
        t.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 1.1, RULE), ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE), ("LINEBELOW", (0, -1), (-1, -1), 1.1, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4)]))
        return KeepTogether([Spacer(1, 3), t, Paragraph(caption, ST["cap"])]) if len(rows) <= 12 else _Split(t, caption)


def _Split(t, caption):
    return [Spacer(1, 3), t, Paragraph(caption, ST["cap"])]


def _ratio(path) -> float:
    from PIL import Image as PI
    with PI.open(path) as im:
        return im.height / im.width
