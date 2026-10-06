"""Section detector (plan section 8.2): tag every line of a document with where it sits.

Labels: TOC, CLAUSE_LIST_IBR (a list of clauses incorporated by reference), CHECKLIST (a clause list whose items
are selected: 52.212-5, 252.212-7001, agency checklists), FULL_TEXT_CLAUSE (a clause heading and its body),
INSTRUCTIONS (Section L / 52.212-1), EVALUATION (Section M / 52.212-2), SOW (Section C / statement of work), OTHER.

Heading regexes plus a small state machine over the whole document (state carries across pages). A heading changes
the state; box-marker lines inside a run switch a line to CHECKLIST whatever the state. This is a rules component: it
is used by the rules baseline B1 and is an optional auxiliary label for the model; it is evaluated on gold later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOC = "TOC"
IBR = "CLAUSE_LIST_IBR"
CHECKLIST = "CHECKLIST"
FULL_TEXT = "FULL_TEXT_CLAUSE"
INSTRUCTIONS = "INSTRUCTIONS"
EVALUATION = "EVALUATION"
SOW = "SOW"
OTHER = "OTHER"

_MARKER_START = re.compile(r"^\s*⟦[X ?]⟧")
_LEADER = re.compile(r"\.{4,}\s*[\divxlc]*\s*$|(?:\.\s){5,}")
_TOC_HEAD = re.compile(r"^\s*(?:TABLE\s+OF\s+CONTENTS|CONTENTS)\s*$", re.I)
_SECTION = re.compile(r"^\s*(?:PART\s+[IV]+\s*[-–—:]?\s*)?SECTION\s+([A-M])\b(?P<rest>.*)$", re.I)
_IBR_HEAD = re.compile(
    r"^\s*(?:\d{2,4}\.\d{3}-\d+\s+)?(?:CLAUSES?|PROVISIONS?|SOLICITATION PROVISIONS?)"
    r"\s+INCORPORATED\s+BY\s+REFERENCE\b",
    re.I,
)
_FULLTEXT_HEAD = re.compile(r"^\s*(?:CLAUSES?|PROVISIONS?|ADDENDUM)\b.{0,60}\b(?:IN|BY)\s+FULL\s+TEXT\b", re.I)
_CLAUSE_HEAD = re.compile(
    r"^\s*(?:⟦[X ?]⟧\s*)?(?:FAR\s+|DFARS\s+)?(?P<n>\d{2,4}\.\d{3}-\d{1,4})\s+(?P<title>[A-Z][^()\n]{3,110}?)"
    r"(?:\s*\((?:[A-Za-z]{3,9}\.?\s+\d{4}|DEVIATION[^)]*)\))*\s*$"
)
_END_OF = re.compile(r"\(\s*End of (?:clause|provision)\s*\)", re.I)
_LIST_ITEM = re.compile(
    r"^\s*(?:⟦[X ?]⟧\s*)?\((?:\d{1,3}|[a-z])\)\s*(?:\([ivxIVX]+\)\s*)?(?:FAR\s+|DFARS\s+)?\d{2,4}\.\d{3}-\d{1,4}"
)
_INSTR = re.compile(
    r"^\s*(?:INSTRUCTIONS,?\s+CONDITIONS,?\s+AND\s+NOTICES\s+TO\s+OFFERORS|INSTRUCTIONS\s+TO\s+OFFERORS)\b", re.I
)
_EVAL = re.compile(r"^\s*EVALUATION\s+(?:FACTORS|CRITERIA)\b", re.I)
_SOW_HEAD = re.compile(
    r"^\s*(?:STATEMENT\s+OF\s+WORK|PERFORMANCE\s+WORK\s+STATEMENT|SCOPE\s+OF\s+WORK)\s*(?:\(\w+\))?\s*$", re.I
)
# Clauses whose body is a list of clauses the contracting officer selects.
CHECKLIST_CLAUSES = {"52.212-5", "52.213-4", "252.212-7001", "52.244-6"}
_SECTION_LABEL = {"C": SOW, "L": INSTRUCTIONS, "M": EVALUATION}


@dataclass
class LabelledLine:
    page: int
    line_no: int
    text: str
    label: str
    heading: bool = False
    clause: str | None = None  # the clause whose full text this line belongs to, if any


def _is_section_heading(line: str) -> re.Match[str] | None:
    m = _SECTION.match(line)
    if not m:
        return None
    rest = m.group("rest").strip()
    # "SECTION I - CONTRACT CLAUSES" and "Section A - Solicitation/Contract Form" are headings;
    # "Section G of the contract." is a sentence.
    if not rest or rest[0] in "-–—:." or (rest.upper() == rest and len(rest) <= 90):
        return m if len(line.strip()) <= 120 else None
    return None


_TRAILING_PAGE = re.compile(r"\S\s{1,}\d{1,3}\s*$")


def _toc_like(line: str) -> bool:
    """A table-of-contents entry: leader dots, or a heading with a trailing page number."""
    return bool(
        _LEADER.search(line)
        or (_TRAILING_PAGE.search(line) and (_is_section_heading(line) or _CLAUSE_HEAD.match(line)))
    )


def label_document(pages: list[tuple[int, str]]) -> list[LabelledLine]:
    """pages: [(page_number, text_layout)] in order -> one LabelledLine per non-empty line."""
    out: list[LabelledLine] = []
    state = OTHER
    section_state = OTHER
    clause: str | None = None
    in_toc = False  # inside a table of contents: ends at the first line that is not an entry
    for page, text in pages:
        for li, raw in enumerate(text.split("\n")):
            line = raw.strip()
            if not line:
                continue
            heading = False
            if _TOC_HEAD.match(line):
                in_toc, heading = True, True
                label = TOC
            elif _toc_like(line) or in_toc and len(line) < 3:
                label = TOC
            else:
                in_toc = False
                sec = _is_section_heading(line)
                if sec:
                    letter = sec.group(1).upper()
                    section_state = _SECTION_LABEL.get(letter, IBR if letter in ("I", "K") else OTHER)
                    state, clause, heading = section_state, None, True
                elif _IBR_HEAD.match(line):
                    state, clause, heading = IBR, None, True
                elif _FULLTEXT_HEAD.match(line):
                    state, clause, heading = FULL_TEXT, None, True
                elif _INSTR.match(line):
                    state, clause, heading = INSTRUCTIONS, None, True
                elif _EVAL.match(line):
                    state, clause, heading = EVALUATION, None, True
                elif _SOW_HEAD.match(line):
                    state, clause, heading = SOW, None, True
                label = state
                if not heading:
                    ch = _CLAUSE_HEAD.match(line)
                    if ch and not _LIST_ITEM.match(line) and state in (FULL_TEXT, CHECKLIST, OTHER):
                        state, clause, heading = FULL_TEXT, ch.group("n"), True
                        label = FULL_TEXT
                    elif _END_OF.search(line):
                        label = FULL_TEXT if clause else state
                        clause = None
                    elif (
                        clause in CHECKLIST_CLAUSES
                        and _LIST_ITEM.match(line)
                        or _MARKER_START.match(line)
                        and re.search(r"\d{2,4}\.\d{3}-\d", line)
                    ):
                        label = CHECKLIST
                    elif clause and state == FULL_TEXT:
                        label = FULL_TEXT
            out.append(
                LabelledLine(page, li, line, label, heading, clause if label in (FULL_TEXT, CHECKLIST) else None)
            )
    return out
