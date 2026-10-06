"""Layout-aware PDF text with explicit checkbox state (plan section 7).

Two views per page: `text_plain` (PyMuPDF reading-order text, roughly what the production extractor sees) and
`text_layout`, the same lines with a marker where a box is: `⟦X⟧` checked, `⟦ ⟧` unchecked, `⟦?⟧` a box whose state
could not be determined. Every box records which of four sources produced it: a form widget, a glyph, a vector drawing,
or `lost` (the line looks like a checklist item but no signal was found). The first three are observed; `lost` is a
heuristic flag and is labelled as such.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pymupdf

CHECKED_M, UNCHECKED_M, UNKNOWN_M = "⟦X⟧", "⟦ ⟧", "⟦?⟧"
MARK = {"X": CHECKED_M, " ": UNCHECKED_M, "?": UNKNOWN_M}

# Unicode names settle the meaning of these (BALLOT BOX WITH X / WITH CHECK; BALLOT BOX; WHITE SQUARE ...); the checked
# and unchecked ballot boxes and the inline white square were also confirmed on rendered real pages (decisions.md).
CHECKED = {"☒", "☑"}  # ☒ ☑
UNCHECKED = {"☐", "□", "◻", "❏", "❑"}  # ☐ □ ◻ ❏ ❑
# Marks that are a checkbox only when they stand where a box would: at the start of a line.
TICKS_AT_LINE_START = {"✓": "X", "✔": "X", "✗": "X", "✘": "X"}  # ✓ ✔ ✗ ✘
FILLED_SQUARE = "■"  # ■ checked at the start of a clause line, otherwise a bullet
# Private-use code points (Wingdings and friends). Only box-shaped ones can be a checkbox, and their meaning (checked or
# not) has not been verified on rendered pages, so their state is unknown. Bullets such as U+F0B7 and U+F0A7 are ignored
# as boxes and logged. Built with chr() so no invisible private-use character sits in the source.
BOX_LIKE_PUA = {chr(c) for c in (0xF06F, 0xF070, 0xF071, 0xF072, 0xF0A8, 0xF0FC, 0xF0FD, 0xF0FE)}


def is_pua(c: str) -> bool:
    return 0xF000 <= ord(c) <= 0xF0FF


_CLAUSE_AFTER = re.compile(r"^\s*(?:\(\w{1,4}\)\s*)*(?:FAR\s+|DFARS\s+)?(?:\d{2,4})\.\d{3}(?:-\d{1,4})?")
_CHECKLIST_LINE = re.compile(
    r"^\s*\((?:\d{1,3}|[a-z])\)\s*(?:\([ivxIVX]+\)\s*)?(?:FAR\s+|DFARS\s+)?(?:52|252)\.\d{3}-\d{1,4}"
)
_CHECKLIST_CONTEXT = re.compile(r"52\.212-5|52\.213-4|252\.212-7001|52\.222-\d+|252\.2\d\d-70\d\d")


@dataclass
class Box:
    state: str  # "X" | " " | "?"
    source: str  # widget | glyph | drawing | lost
    bbox: list[float] | None
    detail: str = ""  # the glyph, the widget type, ...
    confidence: float = 1.0


@dataclass
class Line:
    text_plain: str
    text_layout: str
    bbox: list[float]
    boxes: list[Box] = field(default_factory=list)
    ignored_pua: list[str] = field(default_factory=list)  # private-use code points that are not boxes (bullets)


@dataclass
class PageText:
    page: int
    text_plain: str
    text_layout: str
    lines: list[Line]
    box_counts: dict[str, int]
    scanned: bool
    pua_codepoints: dict[str, int]
    unattached_widgets: int = 0
    pua_ignored: dict[str, int] = field(default_factory=dict)

    def offset_map(self) -> list[list[Any]]:
        """[start, end, bbox] of every line of `text_layout` (line granularity: enough to point at evidence)."""
        out, pos = [], 0
        for ln in self.lines:
            out.append([pos, pos + len(ln.text_layout), ln.bbox])
            pos += len(ln.text_layout) + 1
        return out


def _line_from_chars(chars: list[dict[str, Any]], bbox: tuple[float, ...]) -> Line:
    plain, layout, boxes, ignored = [], [], [], []
    first_text = next((i for i, c in enumerate(chars) if not c["c"].isspace()), 0)
    for i, ch in enumerate(chars):
        c = ch["c"]
        plain.append(c)
        at_start = i == first_text
        state: str | None = None
        detail = c
        if c in CHECKED:
            state = "X"
        elif c in UNCHECKED:
            state = " "
        elif c in TICKS_AT_LINE_START and at_start:
            state = TICKS_AT_LINE_START[c]
        elif c == FILLED_SQUARE and at_start and _CLAUSE_AFTER.match("".join(x["c"] for x in chars[i + 1 :])):
            state = "X"
        elif c in BOX_LIKE_PUA:
            state, detail = "?", f"U+{ord(c):04X}"
        elif is_pua(c):
            ignored.append(f"U+{ord(c):04X}")
        if state is None:
            layout.append(c)
        else:
            layout.append(MARK[state])
            boxes.append(Box(state, "glyph", [round(v, 1) for v in ch["bbox"]], detail, 1.0 if state != "?" else 0.0))
    return Line("".join(plain), "".join(layout), [round(v, 1) for v in bbox], boxes, ignored)


def _widget_checked(value: Any) -> bool:
    return value not in (None, "", "Off", "off", False, 0, "0", "No")


def _attach_widget(lines: list[Line], rect: pymupdf.Rect, state: str, kind: str) -> bool:
    """Prefix the marker to the nearest line to the right of the widget on the same baseline."""
    cy = (rect.y0 + rect.y1) / 2
    best, best_gap = None, 1e9
    for ln in lines:
        x0, y0, x1, y1 = ln.bbox
        if y0 - 2 <= cy <= y1 + 2 and x0 >= rect.x0 - 2:
            gap = x0 - rect.x1
            if -4 <= gap < best_gap and gap <= 80:
                best, best_gap = ln, gap
    if best is None or any(b.source in ("glyph", "widget") and b.state != "?" for b in best.boxes[:1]):
        return False
    best.text_layout = f"{MARK[state]} {best.text_layout}"
    best.boxes.insert(
        0, Box(state, "widget", [round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1)], kind)
    )
    return True


def _small_squares(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str, float]]:
    """Square-ish 5-14 pt paths and what is inside them: (rect, state, confidence). A heuristic; confidence says so."""
    paths = page.get_drawings()
    squares = []
    for p in paths:
        r = p["rect"]
        w, h = r.width, r.height
        if 5 <= w <= 14 and 5 <= h <= 14 and abs(w - h) <= 1.5:
            kinds = [it[0] for it in p["items"]]
            if "re" in kinds or kinds.count("l") >= 4:
                squares.append((r, p))
    out = []
    for r, p in squares:
        region = pymupdf.Rect(r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5)
        inner = [
            q for q in paths if q is not p and region.contains(q["rect"]) and max(q["rect"].width, q["rect"].height) > 1
        ]
        filled = p.get("fill") not in (None, (1, 1, 1), (1.0, 1.0, 1.0))
        diag = any(
            it[0] == "l" and abs(it[1].x - it[2].x) > 1.5 and abs(it[1].y - it[2].y) > 1.5
            for q in inner
            for it in q["items"]
        )
        curve = any(it[0] == "c" for q in inner for it in q["items"])
        if filled or diag or curve:
            out.append((r, "X", 0.7))
        elif not inner:
            out.append((r, " ", 0.7))
    return out


def extract_page(page: pymupdf.Page, number: int) -> PageText:
    raw = page.get_text("rawdict", sort=True)
    lines: list[Line] = []
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for ln in block["lines"]:
            chars = [c for sp in ln["spans"] for c in sp["chars"]]
            if chars and any(not c["c"].isspace() for c in chars):
                lines.append(_line_from_chars(chars, tuple(ln["bbox"])))
    text_plain = page.get_text("text", sort=True)

    unattached = 0
    try:
        for w in page.widgets() or []:
            if w.field_type_string in ("CheckBox", "RadioButton"):
                state = "X" if _widget_checked(w.field_value) else " "
                if not _attach_widget(lines, w.rect, state, w.field_type_string):
                    unattached += 1
    except Exception:  # noqa: BLE001  (a broken form structure must not lose the page's text)
        pass
    for rect, state, conf in _small_squares(page):
        cy = (rect.y0 + rect.y1) / 2
        for ln in lines:
            x0, y0, x1, y1 = ln.bbox
            if y0 - 2 <= cy <= y1 + 2 and -2 <= x0 - rect.x1 <= 14 and not ln.boxes:
                ln.text_layout = f"{MARK[state]} {ln.text_layout}"
                ln.boxes.insert(
                    0,
                    Box(state, "drawing", [round(v, 1) for v in (rect.x0, rect.y0, rect.x1, rect.y1)], "square", conf),
                )
                break
    context = bool(_CHECKLIST_CONTEXT.search(text_plain))
    if context:
        for ln in lines:
            if not ln.boxes and _CHECKLIST_LINE.match(ln.text_plain):
                ln.text_layout = f"{UNKNOWN_M} {ln.text_layout}"
                ln.boxes.append(Box("?", "lost", None, "checklist-looking line without a box signal", 0.0))

    counts = Counter(f"{b.source}:{b.state}" for ln in lines for b in ln.boxes)
    pua = Counter(b.detail for ln in lines for b in ln.boxes if b.detail.startswith("U+"))
    scanned = len(text_plain.strip()) < 20 and bool(page.get_images())
    return PageText(
        number,
        text_plain,
        "\n".join(ln.text_layout for ln in lines),
        lines,
        dict(counts),
        scanned,
        dict(pua),
        unattached,
        dict(Counter(c for ln in lines for c in ln.ignored_pua)),
    )


def extract_pdf(path: Path) -> list[PageText]:
    with pymupdf.open(path) as doc:
        return [extract_page(pg, i + 1) for i, pg in enumerate(doc)]


def page_row(doc_id: str, p: PageText) -> dict[str, Any]:
    import json

    return {
        "doc_id": doc_id,
        "page": p.page,
        "text_plain": p.text_plain,
        "text_layout": p.text_layout,
        "box_signals": json.dumps(
            {
                "counts": p.box_counts,
                "pua": p.pua_codepoints,
                "pua_ignored": p.pua_ignored,
                "unattached_widgets": p.unattached_widgets,
            }
        ),
        "offset_map": json.dumps(p.offset_map()),
        "scanned": p.scanned,
        "boxes": json.dumps([[i, asdict(b)] for i, ln in enumerate(p.lines) for b in ln.boxes]),
    }
