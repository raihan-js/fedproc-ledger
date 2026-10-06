"""Clause-number candidates over `text_layout` (plan section 8.1): high recall, symbolic, no model.

Starts from VETR's patterns (see patterns.py, which stays an exact port for baseline B0) and adds what VETR misses:
other hyphens and stray spaces inside a number, prefix words, subparagraph references, ranges, plus the context a later
classifier needs on the same line: cited date, alternate, deviation marker and the checkbox marker before the number.
Things that look like non-clauses (money, thousands separators) are still emitted, flagged, so a model can learn
NOT_A_CLAUSE. Recall on gold is measured later and reported; a clause missed here is an end-to-end error.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from fedproc_ledger.registry.dates import normalize_clause_date

# part number -> regulation code. x52 parts of eCFR Title 48 plus the four VETR patterns that eCFR does not carry.
REGULATION_BY_BASE = {
    "52": "FAR",
    "252": "DFARS",
    "352": "HHSAR",
    "452": "AGAR",
    "552": "GSAM",
    "652": "DOSAR",
    "752": "AIDAR",
    "852": "VAAR",
    "952": "DEAR",
    "1052": "CH10",
    "1252": "CH12",
    "1352": "CH13",
    "1452": "CH14",
    "1552": "CH15",
    "1652": "CH16",
    "1852": "NFS",
    "1952": "CH19",
    "2052": "CH20",
    "2152": "CH21",
    "2452": "HUDAR",
    "2852": "CH28",
    "2952": "CH29",
    "3052": "HSAR",
    "3452": "CH34",
    "5152": "AFARS",
    "5252": "NMCARS",
    "5352": "DAFFARS",
    "5452": "DLAD",
    "7052": "SOFARS",
}
_BASES = "|".join(sorted(REGULATION_BY_BASE, key=lambda b: (-len(b), b)))
_HYPHENS = "-‐‑‒–—−"
_PREFIX_WORDS = "|".join(
    (
        "FAR DFARS DFAR GSAM GSAR HHSAR AGAR DOSAR AIDAR DEAR VAAR NFS HSAR HUDAR "
        "AFARS DAFFARS NMCARS SOFARS DLAD Clause Provision Section"
    ).split()
)
_NUMBER = re.compile(
    rf"(?:(?P<prefix>\b(?:{_PREFIX_WORDS}))\s*)?(?<!\d)(?P<base>{_BASES})\s?\.\s?(?P<sec>\d{{3}})"
    rf"(?:\s?[{_HYPHENS}]\s?(?P<suf>\d{{1,4}}))?",
    re.I | re.ASCII,
)
_SUBPARA = re.compile(r"\s?((?:\([A-Za-z0-9]{1,4}\))+)")
_DATE = re.compile(r"\(\s*(?:DEV(?:IATION)?\.?\s+)?([A-Za-z]{3,9}\.?\s+(?:19|20)\d{2})\s*\)")
_DATE_BARE = re.compile(r"^\s*\(\s*([A-Za-z]{3,9}\.?\s+(?:19|20)\d{2})\s*\)")
_ALT_AFTER = re.compile(r"\b(Alternate|Alt\.?)\s+([IVXLC]+)\b", re.I)
_ALT_BEFORE = re.compile(r"(Alternate|Alt\.?)\s+([IVXLC]+)\s*(?:\(([^)]*)\))?\s*(?:of|to)\s*$", re.I)
_DEVIATION = re.compile(r"\(?\s*(?:RFO\s+)?DEV(?:IATION)?\b[^)\n]{0,40}\)?", re.I)
_RANGE = re.compile(
    r"\s*(?:through|thru|to)\s*(?:(?:FAR|DFARS)\s+)?(?:(?P<b>\d{2,4})\s?\.\s?(?P<s>\d{3})\s?[-‐-―]\s?|[-‐-―]\s?)?(?P<e>\d{1,4})\b",
    re.I,
)
_MARKER = re.compile(r"⟦[X ?]⟧")
MAX_RANGE = 60


@dataclass
class Candidate:
    doc_id: str
    page: int
    char_start: int
    char_end: int
    raw: str
    number: str
    regulation: str
    prefix: str | None
    subpara: str | None
    line_text: str
    cited_date: str | None
    alternate: str | None
    deviation_marker: str | None
    box_marker: str | None
    from_range: bool = False
    nonclause_hints: list[str] = field(default_factory=list)
    in_registry: bool | None = None
    registry_status: str | None = None
    cand_id: str = ""

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def _normalise(base: str, sec: str, suf: str | None) -> str:
    return f"{base}.{sec}" + (f"-{suf}" if suf else "")


def _hints(line: str, start: int, end: int) -> list[str]:
    hints = []
    before = line[max(0, start - 3) : start]
    if "$" in line[max(0, start - 2) : start]:
        hints.append("money")
    if re.search(r"\d,$", line[max(0, start - 2) : start]) or re.search(r"\d[.,]\s?$", before):
        hints.append("longer_number")
    if re.match(r"\s?%", line[end : end + 2]):
        hints.append("percent")
    if line[end : end + 1].isdigit():
        hints.append("followed_by_digit")
    if re.match(r"\.\d", line[end : end + 2]):
        hints.append("decimal_continuation")
    return hints


def _range_copies(
    base: Candidate, m: re.Match[str], rng: re.Match[str], line: str, start: int, offset: int
) -> list[Candidate]:
    """Candidates for the numbers inside "52.219-1 through 52.219-4": the middle ones, and the end one if it is written
    short ("through -4") and so has no match of its own. The first number is `base` itself."""
    lo, hi = int(m.group("suf")), int(rng.group("e"))
    if not lo < hi <= lo + MAX_RANGE:
        return []
    span_end = offset + m.end() + rng.end()
    raw = line[start : m.end() + rng.end()]
    numbers = list(range(lo + 1, hi)) + ([] if rng.group("b") else [hi])  # a fully written end is already a match
    return [
        replace(
            base,
            number=_normalise(m.group("base"), m.group("sec"), str(k)),
            char_end=span_end,
            raw=raw,
            subpara=None,
            alternate=None,
            prefix=m.group("prefix") if k != hi else None,
            from_range=True,
            nonclause_hints=[],
        )
        for k in numbers
    ]


def generate_page_candidates(
    doc_id: str, page: int, text_layout: str, registry: Mapping[str, str] | None = None
) -> list[Candidate]:
    """All candidates on one page. `registry` maps a canonical number to its status (active | reserved | removed)."""
    out: list[Candidate] = []
    offset = 0
    lines = text_layout.split("\n")
    for li, line in enumerate(lines):
        matches = list(_NUMBER.finditer(line))
        for mi, m in enumerate(matches):
            start, end = m.start("base"), m.end()
            nxt = matches[mi + 1].start() if mi + 1 < len(matches) else len(line)
            subpara = None
            sp = _SUBPARA.match(line[end:])
            if sp:
                subpara, end = sp.group(1), end + sp.end()
            after = line[end:nxt]
            date = _DATE.search(after)
            cited_date = normalize_clause_date(date.group(1)) if date else None
            if cited_date is None and li + 1 < len(lines):
                nd = _DATE_BARE.match(lines[li + 1])  # the date wrapped onto the next line
                cited_date = normalize_clause_date(nd.group(1)) if nd else None
            alt_after = _ALT_AFTER.search(after)
            alt_before = _ALT_BEFORE.search(line[: m.start()])
            alternate = None
            if alt_after:
                alternate = f"Alternate {alt_after.group(2).upper()}"
            elif alt_before:
                alternate = f"Alternate {alt_before.group(2).upper()}"
                if cited_date is None and alt_before.group(3):
                    cited_date = normalize_clause_date(alt_before.group(3))
            dev = _DEVIATION.search(line)
            markers = list(_MARKER.finditer(line[:start]))
            cand = Candidate(
                doc_id=doc_id,
                page=page,
                char_start=offset + start,
                char_end=offset + end,
                raw=line[start:end],
                number=_normalise(m.group("base"), m.group("sec"), m.group("suf")),
                regulation=REGULATION_BY_BASE[m.group("base")],
                prefix=m.group("prefix"),
                subpara=subpara,
                line_text=line.strip(),
                cited_date=cited_date,
                alternate=alternate,
                deviation_marker=dev.group(0).strip() if dev else None,
                box_marker=markers[-1].group(0) if markers else None,
                nonclause_hints=_hints(line, start, end),
            )
            out.append(cand)
            if m.group("suf") and m.group("suf").isdigit():
                rng = _RANGE.match(line[m.end() :])
                if rng and (
                    not rng.group("b") or (rng.group("b") == m.group("base") and rng.group("s") == m.group("sec"))
                ):
                    out.extend(_range_copies(cand, m, rng, line, start, offset))
        offset += len(line) + 1
    for i, c in enumerate(out):
        c.cand_id = f"{doc_id}-p{page}-{i}"
        if registry is not None:
            c.registry_status = registry.get(c.number)
            c.in_registry = c.registry_status is not None
    return out
