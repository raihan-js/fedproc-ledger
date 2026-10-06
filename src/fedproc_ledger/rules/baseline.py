"""Rules baseline B1 and status-quo baseline B0 (plan sections 8.3 and 8.4), and the document ledger.

B1 assigns one of the ten roles to every candidate from its section label (rules/sections.py), its box marker and
its It is meant to be as strong as reasonably possible; where it cannot tell (a box whose state was lost) it says so in
`reason` and gives a low `confidence`. B0 is what VETR does today: every number the status-quo regexes find that
exists in the registry binds the contract.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fedproc_ledger.candidates.generate import Candidate
from fedproc_ledger.rules import sections as S

IBR, FULL, SELECTED, NOT_SELECTED = (
    "INCORPORATED_BY_REFERENCE",
    "FULL_TEXT",
    "CHECKLIST_SELECTED",
    "CHECKLIST_NOT_SELECTED",
)
EXCLUDED, INTERNAL, NARRATIVE, INDEX, NOT_CLAUSE, UNCLEAR = (
    "EXPLICITLY_EXCLUDED", "INTERNAL_REFERENCE", "NARRATIVE_MENTION", "INDEX_ENTRY", "NOT_A_CLAUSE", "UNCLEAR",
)  # fmt: skip
ROLES = [IBR, FULL, SELECTED, NOT_SELECTED, EXCLUDED, INTERNAL, NARRATIVE, INDEX, NOT_CLAUSE, UNCLEAR]
BINDING = {IBR, FULL, SELECTED}

_EXCLUSION = re.compile(
    r"^[\s,:;.\-–—]*(?:\(?\s*(?:deleted|reserved)\s*\)?|\[\s*reserved\s*\]|is\s+(?:hereby\s+)?deleted|has\s+been\s+deleted)",
    re.I,
)
_LIST_LINE = re.compile(r"^\s*(?:⟦[X ?]⟧\s*)?(?:FAR\s+|DFARS\s+)?\d{2,4}\.\d{3}-\d{1,4}\b")


@dataclass
class Prediction:
    cand: Candidate
    role: str
    confidence: float
    reason: str
    section: str


def _starts_line(c: Candidate) -> bool:
    return bool(_LIST_LINE.match(c.line_text))


def classify(c: Candidate, ll: S.LabelledLine | None) -> Prediction:
    """One candidate in context -> a role, with the reason."""
    section = ll.label if ll else S.OTHER

    def P(role: str, conf: float, why: str) -> Prediction:
        return Prediction(c, role, conf, why, section)

    hints = set(c.nonclause_hints)
    if hints & {"money", "longer_number", "percent", "decimal_continuation"}:
        return P(NOT_CLAUSE, 0.9, f"context hint {sorted(hints)}")
    if c.in_registry is False and c.regulation not in ("AFARS", "NMCARS", "DAFFARS", "SOFARS", "DLAD"):
        return P(NOT_CLAUSE, 0.6, "number is not in the eCFR registry")
    if section == S.TOC:
        return P(INDEX, 0.95, "table of contents")
    after = c.line_text.split(c.raw.split("(")[0], 1)[-1] if c.raw else ""
    if _EXCLUSION.match(after[:60]):
        return P(EXCLUDED, 0.8, "deleted or reserved right after the number")
    if c.box_marker and (section == S.CHECKLIST or _starts_line(c) or c.line_text.startswith("⟦")):
        if c.box_marker == "⟦X⟧":
            return P(SELECTED, 0.95, "checked box")
        if c.box_marker == "⟦ ⟧":
            return P(NOT_SELECTED, 0.95, "unchecked box")
        return P(SELECTED, 0.5, "box state lost; counted as selected (benefit of the doubt)")
    if section == S.CHECKLIST:
        return P(SELECTED, 0.5, "checklist item with no box signal; counted as selected")
    if section == S.IBR:
        return (
            P(IBR, 0.85, "listed under an incorporation heading")
            if _starts_line(c)
            else P(INTERNAL, 0.6, "cited inside a list line")
        )
    if section == S.FULL_TEXT:
        if ll and ll.heading and ll.clause == c.number:
            return P(FULL, 0.9, "heading of a clause given in full text")
        return P(INTERNAL, 0.7, "cited inside another clause's text")
    if section in (S.INSTRUCTIONS, S.EVALUATION, S.SOW):
        return P(NARRATIVE, 0.8, f"cited in {section.lower()}")
    if _starts_line(c) and re.search(r"\(\s*[A-Za-z]{3,9}\.?\s+\d{4}\s*\)", c.line_text):
        return P(IBR, 0.5, "dated list line outside any recognised section")
    return P(NARRATIVE, 0.55, "cited in running text")


def classify_document(cands: list[Candidate], labelled: list[S.LabelledLine]) -> list[Prediction]:
    by_line = {(ll.page, ll.line_no): ll for ll in labelled}
    return [classify(c, by_line.get((c.page, c.line_no))) for c in cands]


def ledger(preds: list[Prediction]) -> dict[tuple[str, str | None], dict[str, Any]]:
    """The binding set: (number, alternate) of every IBR, FULL_TEXT or CHECKLIST_SELECTED mention, minus any number that
    has an EXPLICITLY_EXCLUDED mention. Each entry keeps its mentions' roles and the lowest confidence."""
    excluded = {p.cand.number for p in preds if p.role == EXCLUDED}
    entries: dict[tuple[str, str | None], dict[str, Any]] = defaultdict(
        lambda: {"roles": [], "confidence": 1.0, "pages": set()}
    )
    for p in preds:
        if p.role in BINDING and p.cand.number not in excluded and not p.cand.from_range:
            e = entries[(p.cand.number, p.cand.alternate)]
            e["roles"].append(p.role)
            e["confidence"] = min(e["confidence"], p.confidence)
            e["pages"].add(p.cand.page)
    return dict(entries)


def b0_ledger(numbers: list[str], registry: dict[str, str]) -> set[str]:
    """Status quo: every number found by VETR's regexes that is in the registry binds the contract."""
    return {n for n in numbers if n in registry}
