"""HTML report for Checkpoint 3: a page image beside its text_layout with the markers highlighted."""

from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Any

import pymupdf

_MARKER = re.compile(r"(⟦X⟧|⟦ ⟧|⟦\?⟧)")
_CLASS = {"⟦X⟧": "chk", "⟦ ⟧": "unc", "⟦?⟧": "unk"}
CSS = """
body{font:14px system-ui,sans-serif;margin:24px;color:#15171a}h1{font-size:20px}h2{font-size:15px;margin:28px 0 6px}
.row{display:flex;gap:16px;align-items:flex-start;margin-bottom:24px;border-top:1px solid #ddd;padding-top:12px}
.row img{width:46%;border:1px solid #ccc}.txt{flex:1;white-space:pre-wrap;font:12px/1.45 ui-monospace,monospace}
.chk{background:#b7f0c2;border-radius:3px;padding:0 2px}.unc{background:#e2e5e9;border-radius:3px;padding:0 2px}
.unk{background:#ffd9a0;border-radius:3px;padding:0 2px}.meta{color:#555;font-size:12px}table{border-collapse:collapse}
td,th{border:1px solid #ccc;padding:3px 8px;text-align:right}th:first-child,td:first-child{text-align:left}
"""


def highlight(layout: str) -> str:
    """HTML-escape a layout text and wrap each marker in a coloured span."""
    return "".join(
        f'<span class="{_CLASS[part]}">{html.escape(part)}</span>' if part in _CLASS else html.escape(part)
        for part in _MARKER.split(layout)
    )


def page_image_b64(pdf: Path, page: int, dpi: int = 70) -> str:
    with pymupdf.open(pdf) as d:
        png = d[page - 1].get_pixmap(dpi=dpi).tobytes("png")
    return base64.b64encode(png).decode()


def choose_pages(candidates: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Pick up to n pages that between them show every box source: one best page per source first, then the busiest rest."""
    chosen: list[dict[str, Any]] = []
    for source in ("widget", "glyph", "drawing", "lost"):
        best = max(
            (c for c in candidates if c["by_source"].get(source, 0) >= 2 and c not in chosen),
            key=lambda c: (c["checklist"], c["total"]),
            default=None,
        )
        if best:
            chosen.append(best)
    for c in sorted(candidates, key=lambda c: (-c["checklist"], -c["total"])):
        if len(chosen) >= n:
            break
        if c not in chosen:
            chosen.append(c)
    return chosen[:n]


def build_report(rows: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    """rows: [{title, page, layout, image_b64, counts}] -> an HTML document."""
    parts = [
        f"<!doctype html><meta charset='utf-8'><title>Extraction report</title><style>{CSS}</style>",
        "<h1>Layout-aware extraction: checklist pages</h1>",
    ]
    boxes = stats.get("box_counts_by_source_and_state", {})
    parts.append(
        f"<p class='meta'>{stats.get('extracted', 0)} documents, {stats.get('pages', 0)} pages. Box signals by source and state:</p>"
    )
    parts.append(
        "<table><tr><th>source:state</th><th>boxes</th></tr>"
        + "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in boxes.items())
        + "</table>"
    )
    parts.append(
        "<p class='meta'>Green = checked, grey = unchecked, orange = state unknown (a box exists; or a checklist-looking line with no box signal found: source <code>lost</code>).</p>"
    )
    for r in rows:
        parts.append(
            f"<h2>{html.escape(r['title'])} | page {r['page']}</h2><div class='meta'>{html.escape(json.dumps(r['counts']))}</div>"
        )
        parts.append(
            f"<div class='row'><img src='data:image/png;base64,{r['image_b64']}'><div class='txt'>{highlight(r['layout'])}</div></div>"
        )
    return "\n".join(parts)
