"""RFO (Revolutionary FAR Overhaul) deviation facts for Part 52, from acquisition.gov's FAR Part Deviation Guide.

Only what the pages state is recorded: the model deviation's issuance and update dates, the status of each Part 52
section in the model text ([Reserved] or text, with its title), and the agency deviation PDFs whose file names declare
Part 52 coverage. Anything not parseable is recorded as such, never inferred. Used to LABEL a citation as under
deviation, never to change a ledger.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import unquote, urljoin

GUIDE = "https://www.acquisition.gov/far-overhaul/far-part-deviation-guide"
PART52 = f"{GUIDE}/far-overhaul-part-52"
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_FULL_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b"
)
_MONTH = {
    m: i + 1
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    )
}


def clean(s: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", s))).strip()


def iso_date(text: str) -> str | None:
    m = _FULL_DATE.search(text)
    return f"{m.group(3)}-{_MONTH[m.group(1)]:02d}-{int(m.group(2)):02d}" if m else None


def model_dates(index_html: str) -> dict[str, str | None]:
    """Issuance and update dates of the Part 52 model deviation, from the guide index text."""
    body = clean(re.sub(r"<script.*?</script>|<style.*?</style>", " ", index_html, flags=re.S))
    m = re.search(
        r"Part 52 - Solicitation Provisions and Contract Clauses\s+Issuance Date:\s*"
        r"([A-Za-z]+ \d{1,2}, \d{4})(?:\s+UPDATE:\s*([A-Za-z]+ \d{1,2}, \d{4}))?",
        body,
    )
    return {
        "issued": iso_date(m.group(1)) if m else None,
        "updated": iso_date(m.group(2)) if m and m.group(2) else None,
    }


def part52_sections(part52_html: str) -> list[dict[str, Any]]:
    """One row per section anchor of the RFO Part 52 model text: number, title, status (reserved | text)."""
    rows = []
    for m in re.finditer(r'id="(FAR_52_[0-9_]+)"[^>]*>(.*?)(?=id="FAR_52_[0-9_]+"|$)', part52_html, flags=re.S):
        number = m.group(1)[4:].replace("_", ".", 1).replace("_", "-")
        head = clean(m.group(2))[:300]
        # the anchor's block may hold several consecutive reserved sections; the first heading belongs to this anchor
        first = re.match(rf"{re.escape(number)}\s*(.*?)(?:\s+As prescribed|\s+\(Deviation Date\)|$)", head)
        title = first.group(1).strip() if first else ""
        title = re.split(r"(?<=\.)\s+(?=[A-Z(])", title, maxsplit=1)[0]  # a heading is one sentence; text may follow
        status = "reserved" if re.match(r"\[Reserved\]", title, re.I) else "text"
        kinds = {k.lower() for k in re.findall(r"(?:insert|use) the following (provision|clause)", head, flags=re.I)}
        rows.append(
            {
                "number": number,
                "rfo_title": title.rstrip("."),
                "rfo_status": status,
                "rfo_kind": next(iter(kinds)) if len(kinds) == 1 else "unknown",
            }
        )
    return rows


def agency_part52_pdfs(index_html: str, base: str = "https://www.acquisition.gov") -> list[dict[str, str]]:
    """Agency deviation PDFs whose file name lists Part 52 (e.g. `HHS_RFO_Deviation_Part-3-17-27-45and52.pdf`)."""
    out, seen = [], set()
    for href, label in re.findall(r'<a [^>]*href="([^"]+\.pdf)"[^>]*>(.*?)</a>', index_html, flags=re.S):
        name = unquote(href.rsplit("/", 1)[-1])
        if re.search(r"Parts?[-_ ]?[0-9\-and_ ]*?(?<!\d)52(?!\d)", name) and href not in seen:
            seen.add(href)
            out.append({"agency": clean(label), "filename": name, "url": urljoin(base, href)})
    return out


_DATE_DMY = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b"
)
_NUMBER_PATTERNS = [
    re.compile(r"FAR\s+CLASS\s+DEVIATION\s+(\d{4}-\d{2,3})", re.I),  # HHS: "FAR CLASS DEVIATION 2025-12"
    re.compile(r"AAPD\s+No\.?\s*(\d{2}-\d{2})", re.I),  # USAID: "AAPD No. 25-03"
    re.compile(r"(?:Class\s+Deviation|Deviation)\s*(?:No\.?|Number|#)\s*:?\s*([A-Z0-9][A-Z0-9\-–.]{3,})", re.I),
]
_DHS_ROW = re.compile(
    r"(FAR|HSAR)\s+Class\s+Dev(?:iation)?\s+(\d{2}-\d{2})\s+for\s+(?:FAR|HSAR)\s+Part\s+(\d+)[^.]{0,260}?"
    r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})"
)


def any_date(text: str) -> str | None:
    """First explicit calendar date (`Month D, YYYY` or `D Month YYYY`), else None; never a year-month guess."""
    m1, m2 = _FULL_DATE.search(text), _DATE_DMY.search(text)
    if m1 and (not m2 or m1.start() < m2.start()):
        return f"{m1.group(3)}-{_MONTH[m1.group(1)]:02d}-{int(m1.group(2)):02d}"
    return f"{m2.group(3)}-{_MONTH[m2.group(2)]:02d}-{int(m2.group(1)):02d}" if m2 else None


def pdf_header(text: str) -> dict[str, Any]:
    """Deviation number and date from the first page text of an agency deviation; the raw header is always kept."""
    head = _WS.sub(" ", text[:1500])
    number = next((m.group(1) for pat in _NUMBER_PATTERNS if (m := pat.search(head))), None)
    date = any_date(_WS.sub(" ", text[:6000]))
    return {"deviation_number": number, "date": date, "parsed": bool(number and date), "header": head[:300]}


_DHS_SPLIT = re.compile(r"(?=\b(?:FAR|HSAR)\s+Class\s+Dev\s+\d{2}-\d{2})")
_DHS_HEAD = re.compile(r"\b(FAR|HSAR)\s+Class\s+Dev\s+(\d{2}-\d{2})(?:,\s*Revision\s+(\d+))?")
_DHS_PART = re.compile(r"(?:FAR|HSAR)\s+Part\s+(\d+)")
_DATES_ALL = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b"
)


def dhs_rows(text: str) -> list[dict[str, str]]:
    """DHS "conformed" Part documents open with a table of class deviations: number, revision, part and dates.

    A row's issue date is the LAST date in it; a date inside "(changes effective ...)" is kept separately.
    """
    out = []
    for seg in _DHS_SPLIT.split(_WS.sub(" ", text[:60000])):
        h = _DHS_HEAD.match(seg)
        part = _DHS_PART.search(seg)
        if not h or not part:
            continue
        dates = [d for d in _DATES_ALL.findall(seg)]
        eff = re.search(r"changes effective\s+(" + _DATES_ALL.pattern[2:-2] + r")", seg)
        out.append(
            {
                "regulation": h.group(1),
                "deviation_number": h.group(2),
                "revision": h.group(3) or "",
                "part": part.group(1),
                "date": any_date(dates[-1]) or "" if dates else "",
                "effective": (any_date(eff.group(1)) or "") if eff else "",
            }
        )
    return out
