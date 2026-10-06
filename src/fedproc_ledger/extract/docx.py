"""DOCX text with explicit checkbox state (plan section 7.3): same markers and box sources as the PDF extractor.

Sources: `widget` = a content-control checkbox (`w14:checkbox`) or a legacy form checkbox (`w:ffData/w:checkBox`);
`glyph` = a box character in the text; symbol runs (`w:sym`, Wingdings and friends) are code points whose meaning has
not been verified here, so their state is unknown (`⟦?⟧`) and the code point is logged.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import docx
from lxml import etree

from fedproc_ledger.extract.pdf import CHECKED_M, MARK, UNCHECKED_M, Box, Line, PageText, _line_from_chars

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_NS = {"w": W, "w14": W14}
_TRUE = {"1", "true", "on"}


def _q(prefix: str, name: str) -> str:
    return f"{{{_NS[prefix]}}}{name}"


def _checkbox_state(el: etree._Element) -> str | None:
    """'X' / ' ' for a checkbox control or legacy checkbox element, or None if `el` is neither."""
    cb = el.find(".//w14:checkbox", _NS)
    if cb is not None:
        checked = cb.find("w14:checked", _NS)
        return "X" if checked is not None and str(checked.get(_q("w14", "val"), "0")).lower() in _TRUE else " "
    leg = el.find(".//w:ffData/w:checkBox", _NS)
    if leg is not None:
        chk = leg.find("w:checked", _NS)
        if chk is not None:
            return "X" if str(chk.get(_q("w", "val"), "1")).lower() in _TRUE else " "
        dflt = leg.find("w:default", _NS)
        return "X" if dflt is not None and str(dflt.get(_q("w", "val"), "0")).lower() in _TRUE else " "
    return None


def paragraph_line(p: etree._Element) -> Line:
    """One paragraph as a Line: plain text (what `paragraph.text` shows) and layout text with markers."""
    plain: list[str] = []
    layout: list[str] = []
    boxes: list[Box] = []
    for node in p.iter():
        tag = etree.QName(node).localname if isinstance(node.tag, str) else ""
        if tag == "sdt":
            state = _checkbox_state(node)
            if state is not None:
                layout.append(MARK[state])
                boxes.append(Box(state, "widget", None, "content-control checkbox"))
                node.set("fedproc_done", "1")  # its inner glyph text is the same box: do not count it twice
        elif tag == "r" and node.find(".//w:ffData", _NS) is not None:
            state = _checkbox_state(node)
            if state is not None:
                layout.append(MARK[state])
                boxes.append(Box(state, "widget", None, "legacy form checkbox"))
        elif tag == "sym":
            code = (node.get(_q("w", "char")) or "").upper()
            layout.append(MARK["?"])
            boxes.append(Box("?", "glyph", None, f"U+{code or 'XXXX'} {node.get(_q('w', 'font')) or ''}".strip(), 0.0))
        elif tag == "t" and node.text:
            if any(a.get("fedproc_done") for a in node.iterancestors()):
                plain.append(node.text)
                continue
            plain.append(node.text)
            at_line_start = not "".join(layout).strip()
            chars = [{"c": c, "bbox": (0, 0, 0, 0)} for c in node.text]
            if (
                not at_line_start
            ):  # a tick or filled square counts only at the start of the line: pad so it is not first
                chars.insert(0, {"c": "·", "bbox": (0, 0, 0, 0)})
            ln = _line_from_chars(chars, (0, 0, 0, 0))
            layout.append(ln.text_layout if at_line_start else ln.text_layout[1:])
            boxes.extend(Box(b.state, b.source, None, b.detail, b.confidence) for b in ln.boxes)
    text_plain = "".join(plain)
    return Line(text_plain, re.sub(r"[ \t]+$", "", "".join(layout)), [0.0, 0.0, 0.0, 0.0], boxes)


def extract_docx(path: Path) -> list[PageText]:
    """A DOCX has no pages: the whole document is returned as page 1 (body paragraphs and table rows, in order)."""
    d = docx.Document(str(path))
    body = d.element.body
    lines: list[Line] = []
    for child in body.iterchildren():
        name = etree.QName(child).localname
        if name == "p":
            ln = paragraph_line(child)
            if ln.text_plain.strip() or ln.boxes:
                lines.append(ln)
        elif name == "tbl":
            for tr in child.iter(_q("w", "tr")):
                carry: Line | None = None  # a cell holding only a box belongs to the text of the next cell
                for tc in tr.findall("w:tc", _NS):
                    cell = [paragraph_line(p) for p in tc.findall(".//w:p", _NS)]
                    cell = [c for c in cell if c.text_plain.strip() or c.boxes]
                    for ci, c in enumerate(cell):
                        only_box = bool(c.boxes) and not re.sub(
                            r"[\s\u2610\u2611\u2612\u25a1\[\]()xX_]", "", c.text_plain
                        )
                        if only_box and ci == len(cell) - 1 and carry is None:
                            carry = c
                            continue
                        if carry is not None and ci == 0:
                            c = Line(
                                carry.text_plain + " " + c.text_plain,
                                carry.text_layout + " " + c.text_layout,
                                [0.0, 0.0, 0.0, 0.0],
                                carry.boxes + c.boxes,
                            )
                            carry = None
                        lines.append(c)
                if carry is not None:  # a trailing box with nothing after it stays a line of its own
                    lines.append(carry)
    counts = Counter(f"{b.source}:{b.state}" for ln in lines for b in ln.boxes)
    pua: Counter[str] = Counter(b.detail for ln in lines for b in ln.boxes if b.detail.startswith("U+"))
    text_plain = "\n".join(ln.text_plain for ln in lines)
    return [PageText(1, text_plain, "\n".join(ln.text_layout for ln in lines), lines, dict(counts), False, dict(pua))]


__all__: list[Any] = ["extract_docx", "paragraph_line", "CHECKED_M", "UNCHECKED_M"]
