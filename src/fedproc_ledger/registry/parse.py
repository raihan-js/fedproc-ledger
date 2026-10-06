"""Parse eCFR Title 48 section XML (as returned by the versioner `full` endpoint) into registry fields.

Only explicit text is used: `kind` comes from the prescription sentence ("insert the following clause|provision") or the
closing "(End of clause|provision)" marker and is `unknown` when neither says so or they disagree; it is never guessed.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from fedproc_ledger.registry.dates import normalize_clause_date, trailing_paren_date

_RESERVED = re.compile(r"\[\s*(?:Reserved|Removed(?: and Reserved)?)\s*\]", re.I)
_KIND_WORD = re.compile(r"\b(?:following|this)\s+(provision|clause)s?\b", re.I)
_PRESCRIBED = re.compile(r"\b(?:as\s+prescribed\s+in|prescribed\s+in)\b", re.I)
_REF = re.compile(r"\b\d{1,4}\.\d{1,4}(?:-\d{1,4})?(?:\([A-Za-z0-9]{1,4}\))*")
_ALT = re.compile(r"^\s*(Alternate\s+[IVXLC]+)\b\s*(?:\(([^)]*)\))?", re.I)
_END = re.compile(r"\(\s*End of (provision|clause)\s*\)", re.I)


@dataclass
class ParsedSection:
    number: str
    heading: str
    title: str
    reserved: bool
    prescription: str | None = None
    prescribed_in: list[str] = field(default_factory=list)
    kind: str = "unknown"  # provision | clause | unknown
    kind_source: str = "none"  # prescription | end_marker | none
    clause_title: str | None = None
    clause_date: str | None = None  # YYYY-MM
    alternates: list[dict[str, str | None]] = field(default_factory=list)  # [{name, date}]


def _text(e: ET.Element | None) -> str:
    return re.sub(r"\s+", " ", "".join(e.itertext())).strip() if e is not None else ""


def parse_section(el: ET.Element) -> ParsedSection:
    number = el.get("N") or ""
    heading = _text(el.find("HEAD"))
    title = re.sub(rf"^{re.escape(number)}\s*", "", heading).strip().rstrip(".").strip()
    sec = ParsedSection(number=number, heading=heading, title=title, reserved=bool(_RESERVED.search(heading)))
    if sec.reserved:
        return sec

    kinds_presc: set[str] = set()
    for child in el:
        if child.tag == "EXTRACT":
            break  # the prescription sentence comes before the clause text
        if child.tag == "P":
            t = _text(child)
            if _PRESCRIBED.search(t) or _KIND_WORD.search(t):
                if sec.prescription is None:
                    sec.prescription = t[:400]
                    head = t.split(":")[0]
                    sec.prescribed_in = _REF.findall(head)
                kinds_presc |= {m.group(1).lower() for m in _KIND_WORD.finditer(t.split(":")[0] + ":")}
    ends = {m.group(1).lower() for m in _END.finditer(_text(el))}
    if len(kinds_presc) == 1 and (not ends or ends == kinds_presc):
        sec.kind, sec.kind_source = next(iter(kinds_presc)), "prescription"
    elif not kinds_presc and len(ends) == 1:
        sec.kind, sec.kind_source = next(iter(ends)), "end_marker"
    # else: unknown (no statement, or the sources disagree)

    extract = el.find("EXTRACT")
    if extract is not None:
        first_hd = next((c for c in extract.iter() if c.tag.startswith("HD")), None)
        sec.clause_title = _text(first_hd) or None
        if sec.clause_title:
            sec.clause_date = trailing_paren_date(sec.clause_title)
        if sec.clause_date is None:
            sec.clause_date = normalize_clause_date(_text(extract)[:200])
    if sec.clause_date is None and sec.prescription is not None:
        # DFARS style: no EXTRACT; the dated title is a plain paragraph after the prescription, e.g.
        # "CONTRACTOR COMPLIANCE WITH ... REQUIREMENTS (NOV 2025)"
        seen_prescription = False
        for child in el:
            if child.tag == "HEAD":
                continue
            t = _text(child)
            if not seen_prescription:
                seen_prescription = child.tag == "P" and t.startswith(sec.prescription[:30])
                continue
            if len(t) <= 250 and not t.startswith("(") and (d := trailing_paren_date(t)):
                sec.clause_title, sec.clause_date = t, d
                break
            if len(t) > 250:
                break
    seen: dict[str, str | None] = {}
    for p in el.iter("P"):
        m = _ALT.match(_text(p))
        if m:
            name = "Alternate " + m.group(1).split()[-1].upper()  # Roman numerals stay upper case: "Alternate II"
            date = normalize_clause_date(m.group(2))
            if name not in seen or (seen[name] is None and date):
                seen[name] = date
    sec.alternates = [{"name": n, "date": d} for n, d in seen.items()]
    return sec


def parse_part_xml(xml: bytes | str) -> dict[str, ParsedSection]:
    root = ET.fromstring(xml)
    out: dict[str, ParsedSection] = {}
    for el in root.iter("DIV8"):
        if el.get("TYPE") == "SECTION" and el.get("N"):
            sec = parse_section(el)
            out[sec.number] = sec
    return out
