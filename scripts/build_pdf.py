#!/usr/bin/env python3
from __future__ import annotations

import html
import os
import re
from html.parser import HTMLParser
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "index.html"
PDF_PATH = ROOT / "kominka_reform_estimate.pdf"

INK = colors.HexColor("#1f252b")
MUTED = colors.HexColor("#5d6871")
LINE = colors.HexColor("#d8dee3")
SOFT = colors.HexColor("#f5f7f8")
HEAD = colors.HexColor("#20364d")
ACCENT = colors.HexColor("#9d493d")
ACCENT_SOFT = colors.HexColor("#f8ebe8")
GREEN = colors.HexColor("#3f6a56")
GREEN_SOFT = colors.HexColor("#eaf2ee")


class Node:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[Node | str] = []


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def walk(node: Node, tag: str) -> list[Node]:
    found = []
    if node.tag == tag:
        found.append(node)
    for child in node.children:
        if isinstance(child, Node):
            found.extend(walk(child, tag))
    return found


def child_nodes(node: Node, tags: set[str] | None = None) -> list[Node]:
    items = [c for c in node.children if isinstance(c, Node)]
    return [c for c in items if tags is None or c.tag in tags]


def text_content(node: Node | str) -> str:
    if isinstance(node, str):
        return node
    if node.tag == "br":
        return "\n"
    return "".join(text_content(c) for c in node.children)


def inline_text(node: Node | str) -> str:
    if isinstance(node, str):
        return html.escape(node)
    if node.tag in {"strong", "b"}:
        return f"<b>{''.join(inline_text(c) for c in node.children)}</b>"
    if node.tag == "br":
        return "<br/>"
    return "".join(inline_text(c) for c in node.children)


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()
    return value


def plain(node: Node) -> str:
    return clean_text(text_content(node))


def resolve_image(src: str) -> str:
    return str((ROOT / src).resolve())


def image_flowable(src: str, max_width: float, max_height: float) -> Image:
    path = resolve_image(src)
    img = Image(path)
    scale = min(max_width / img.imageWidth, max_height / img.imageHeight)
    img.drawWidth = img.imageWidth * scale
    img.drawHeight = img.imageHeight * scale
    img.hAlign = "CENTER"
    return img


def make_styles():
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
    styles = getSampleStyleSheet()
    base = dict(fontName="HeiseiKakuGo-W5", textColor=INK, leading=13.2, wordWrap="CJK")
    styles.add(ParagraphStyle("JPBody", parent=styles["Normal"], fontSize=9.2, **base))
    styles.add(ParagraphStyle("JPBodySmall", parent=styles["JPBody"], fontSize=8.1, leading=11.2))
    styles.add(ParagraphStyle("JPTitle", parent=styles["JPBody"], fontSize=22, leading=28, textColor=HEAD, alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle("JPSubtitle", parent=styles["JPBody"], fontSize=9.2, leading=12.6, textColor=MUTED, alignment=TA_CENTER))
    styles.add(ParagraphStyle("JPSection", parent=styles["JPBody"], fontSize=13.8, leading=18, textColor=colors.white, backColor=HEAD, borderPadding=(6, 7, 6), spaceBefore=10, spaceAfter=8))
    styles.add(ParagraphStyle("JPSubsection", parent=styles["JPBody"], fontSize=11.2, leading=15, textColor=HEAD, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle("JPCaption", parent=styles["JPBody"], fontSize=7.7, leading=9.6, textColor=MUTED, alignment=TA_LEFT))
    styles.add(ParagraphStyle("JPTable", parent=styles["JPBody"], fontSize=7.8, leading=10.5))
    styles.add(ParagraphStyle("JPTableSmall", parent=styles["JPBody"], fontSize=7.0, leading=9.4))
    styles.add(ParagraphStyle("JPTableHead", parent=styles["JPTable"], textColor=HEAD, fontSize=7.7, leading=9.6))
    styles.add(ParagraphStyle("JPFooter", parent=styles["JPBody"], fontSize=7.5, leading=9, textColor=MUTED))
    return styles


def paragraph(node: Node | str, style) -> Paragraph:
    if isinstance(node, str):
        body = html.escape(clean_text(node))
    else:
        body = clean_text(inline_text(node))
    return Paragraph(body, style)


def bullet_list(ul: Node, styles) -> list:
    flow = []
    for li in child_nodes(ul, {"li"}):
        flow.append(Paragraph("・" + clean_text(inline_text(li)), styles["JPBody"]))
    flow.append(Spacer(1, 3))
    return flow


def boxed_text(node: Node, styles, border_color, bg_color) -> Table:
    klass = node.attrs.get("class", "")
    if "source-box" in klass:
        lines = []
        strong_nodes = child_nodes(node, {"strong"})
        title = plain(strong_nodes[0]) if strong_nodes else "参考URL:"
        lines.append(f"<b>{html.escape(title)}</b>")
        for li in walk(node, "li"):
            lines.append("・" + clean_text(inline_text(li)))
        body = "<br/>".join(lines)
    else:
        body = clean_text(inline_text(node))
    table = Table([[Paragraph(body, styles["JPBodySmall"])]], colWidths="100%")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.white),
        ("LINEBEFORE", (0, 0), (0, -1), 3, border_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def image_grid(node: Node, styles, available_width: float) -> Table:
    figures = child_nodes(node, {"figure"})
    cells = []
    col_width = (available_width - 8) / 3
    for fig in figures:
        img_node = child_nodes(fig, {"img"})[0]
        cap_nodes = child_nodes(fig, {"figcaption"})
        cap = plain(cap_nodes[0]) if cap_nodes else ""
        cells.append([
            image_flowable(img_node.attrs["src"], col_width, 42 * mm),
            Paragraph(cap, styles["JPCaption"]),
        ])
    rows = []
    for i in range(0, len(cells), 3):
        row = []
        for cell in cells[i:i + 3]:
            row.append(cell)
        while len(row) < 3:
            row.append("")
        rows.append(row)
    table = Table(rows, colWidths=[col_width] * 3, hAlign="CENTER")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def html_table(node: Node, styles, available_width: float) -> LongTable:
    rows = []
    for tr in walk(node, "tr"):
        row = []
        for cell in child_nodes(tr, {"th", "td"}):
            style = styles["JPTableHead"] if cell.tag == "th" else styles["JPTable"]
            row.append(Paragraph(clean_text(inline_text(cell)), style))
        if row:
            rows.append(row)
    if not rows:
        return LongTable([[""]])
    cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < cols:
            row.append("")
    table_rows = walk(node, "tr")
    header_row = table_rows[0] if table_rows else Node("")
    header_text = [clean_text(inline_text(cell)) for cell in child_nodes(header_row, {"th", "td"})]
    if cols == 5 and "DIY項目" in header_text:
        widths = [0.10, 0.16, 0.34, 0.14, 0.26]
    elif cols == 5:
        widths = [0.18, 0.18, 0.18, 0.22, 0.24]
    elif cols == 4:
        widths = [0.16, 0.19, 0.30, 0.35]
    else:
        widths = [1 / cols] * cols
    col_widths = [available_width * w for w in widths]
    table = LongTable(rows, colWidths=col_widths, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f5")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fbfcfd")) if len(rows) > 3 else ("BACKGROUND", (0, 0), (0, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def summary_grid(metrics: Node, styles, available_width: float) -> Table:
    cells = []
    metric_value_style = ParagraphStyle(
        "MetricValue",
        parent=styles["JPBody"],
        fontSize=11.7,
        leading=14,
        textColor=HEAD,
        alignment=TA_CENTER,
        wordWrap=None,
        splitLongWords=0,
    )
    for metric in child_nodes(metrics, {"div"}):
        klass = metric.attrs.get("class", "")
        if "metric" not in klass:
            continue
        divs = child_nodes(metric, {"div"})
        label = plain(divs[0]) if len(divs) > 0 else ""
        value = plain(divs[1]) if len(divs) > 1 else ""
        cells.append([
            Paragraph(label, styles["JPBodySmall"]),
            Paragraph(f"<b>{html.escape(value)}</b>", metric_value_style),
        ])
    col_widths = [available_width * width for width in (0.235, 0.235, 0.235, 0.295)]
    table = Table([cells], colWidths=col_widths[:len(cells)])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def add_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("HeiseiKakuGo-W5", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 8 * mm, "古民家リフォーム費用予測・プラン資料")
    canvas.drawRightString(A4[0] - doc.rightMargin, 8 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def build_story(root: Node, styles, available_width: float):
    story = []
    main = walk(root, "main")[0]
    for section in child_nodes(main, {"section"}):
        headings = child_nodes(section, {"h2"})
        if headings and plain(headings[0]).startswith("9. DIY") and story:
            story.append(PageBreak())
        for node in child_nodes(section):
            klass = node.attrs.get("class", "")
            if node.tag == "h1":
                story.append(Paragraph(plain(node), styles["JPTitle"]))
            elif node.tag == "p":
                story.append(paragraph(node, styles["JPSubtitle" if "subtitle" in klass else "JPBody"]))
            elif node.tag == "h2":
                story.append(Paragraph(plain(node), styles["JPSection"]))
            elif node.tag == "h3":
                story.append(Paragraph(plain(node), styles["JPSubsection"]))
            elif node.tag == "ul":
                story.extend(bullet_list(node, styles))
            elif node.tag == "img":
                max_height = 115 * mm if "hero-image" in klass else 92 * mm
                story.append(image_flowable(node.attrs["src"], available_width, max_height))
                story.append(Spacer(1, 5))
            elif node.tag == "div" and "summary-grid" in klass:
                story.append(summary_grid(node, styles, available_width))
                story.append(Spacer(1, 6))
            elif node.tag == "div" and "image-grid" in klass:
                story.append(image_grid(node, styles, available_width))
                story.append(Spacer(1, 6))
            elif node.tag == "div" and "decision" in klass:
                story.append(boxed_text(node, styles, GREEN, GREEN_SOFT))
                story.append(Spacer(1, 5))
            elif node.tag == "div" and "note" in klass:
                story.append(boxed_text(node, styles, ACCENT, ACCENT_SOFT))
                story.append(Spacer(1, 5))
            elif node.tag == "div" and "source-box" in klass:
                story.append(boxed_text(node, styles, HEAD, SOFT))
                story.append(Spacer(1, 5))
            elif node.tag == "table":
                story.append(html_table(node, styles, available_width))
                story.append(Spacer(1, 7))
    return story


def main():
    parser = TreeParser()
    parser.feed(HTML_PATH.read_text(encoding="utf-8"))
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=11 * mm,
        bottomMargin=15 * mm,
        title="古民家リフォーム費用予測・プラン資料",
        author="futoshi-yamakawa",
    )
    story = build_story(parser.root, styles, doc.width)
    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)


if __name__ == "__main__":
    main()
