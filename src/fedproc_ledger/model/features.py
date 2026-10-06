"""Hand-built features for the mention-role classifier (rules as features, plus layout and wording cues)."""

from __future__ import annotations

import re
from typing import Any

ROLES = [
    "INCORPORATED_BY_REFERENCE", "FULL_TEXT", "CHECKLIST_SELECTED", "CHECKLIST_NOT_SELECTED", "EXPLICITLY_EXCLUDED",
    "INTERNAL_REFERENCE", "NARRATIVE_MENTION", "INDEX_ENTRY", "NOT_A_CLAUSE",
]  # fmt: skip

_ROMAN_ITEM = re.compile(r"^\s*\((?:[ivx]{1,5}|[A-Z]|\d{1,3})\)\s*(?:\([A-Za-z0-9]\)\s*)?(?:FAR\s+)?\d{2,4}\.\d{3}")
_BLANK_ITEM = re.compile(r"^\s*(?:_{2,}|\[\s*\])\s*(?:\(\w{1,3}\)|\()?")
_XMARK = re.compile(r"^\s*(?:_*X_*|\[X\]|X)\s*(?:\(\w{1,4}\))")
_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b|\b20\d{2}-\d{2}\b|\b19\d{2}-\d{2}\b",
    re.I,
)
_TOC = re.compile(r"\.{4,}\s*\d+\s*$|\s\d{1,3}\s*$")
_CUES = {
    "defined": r"\b(?:as defined in|meaning(?:s)? (?:given|provided) in|has the meaning)\b",
    "clause_at": r"\b(?:the )?(?:clause|provision) (?:at|in)\b|\bof (?:this|the) (?:clause|provision)\b",
    "flowdown": r"\bflow ?down\b",
    "paragraph_of": r"\bparagraph\s+\([a-z0-9]+\)",
    "applies_if": r"\bapplies (?:if|to|only)\b",
    "end_of": r"\(end of (?:clause|provision|addendum)",
    "incorporated": r"incorporated (?:herein )?by reference",
    "full_text": r"\bfull text\b",
    "checked": r"\bchecked\b|\bcheck as appropriate\b|\bapplicable if checked\b",
    "prescribed": r"as prescribed in",
    "not_apply": r"\bnot applicable\b|\bdoes not apply\b|\bdeleted\b|\bin lieu of\b",
    "e_g": r"\be\.g\.|\bsee\b|\bin accordance with\b|\bpursuant to\b",
    "definitions": r"\(a\)\s*definitions|\bdefinitions\.",
    "deviation": r"deviation",
    "found_herein": r"found herein|set forth herein|attached hereto|included herein",
    "incorporated_herein": r"incorporated (?:herein|into this)|hereby incorporated",
    "apply_stmt": (
        r"\b(?:clauses?|provisions?)\b[^.;]{0,50}\b(?:apply|applies|applicable)\b"
        r"|are as follows|the following (?:FAR |DFARS )?(?:clauses|provisions)"
    ),
    "requirement": r"\b(?:shall|must|is required|are required|required to)\b",
    "in_accordance": r"in accordance with|pursuant to|\bIAW\b|\bper (?:FAR|DFARS)\b",
    "includes_clause": r"\b(?:includes?|included|including) (?:the )?(?:FAR |DFARS )?(?:clause|provision)",
}
_CUE_RE = {k: re.compile(v, re.I) for k, v in _CUES.items()}
_HEAD_KEYS = {
    "h_ibr": r"incorporated by reference",
    "h_full": r"full text",
    "h_toc": r"table of contents",
    "h_instr": r"instructions to offerors|evaluation",
    "h_sow": r"statement of work|performance work statement|scope of work",
    "h_sec_i": r"section i\b|contract clauses",
    "h_sec_k": r"section k|representations",
    "h_212_5": r"52\.212-5",
}
_HEAD_RE = {k: re.compile(v, re.I) for k, v in _HEAD_KEYS.items()}


def mention_features(item: dict[str, Any], prev_lines: list[str], next_lines: list[str], line: str) -> dict[str, float]:
    f: dict[str, float] = {}
    num = str(item["number"])
    pos = line.find(num)
    before, after = (line[:pos], line[pos + len(num) :]) if pos >= 0 else ("", line)
    f["line_len"] = float(len(line))
    f["num_at_start"] = float(len(before.strip()) <= 6)
    f["num_only_line"] = float(
        line.strip() == num or re.fullmatch(rf"\W*{re.escape(num)}\W*", line.strip()) is not None
    )
    f["after_len"] = float(len(after.strip()))
    f["after_has_title"] = float(bool(re.match(r"\s*[,\-–—.]?\s*[A-Z][A-Za-z]", after)))
    f["after_has_date"] = float(bool(_DATE.search(after)))
    f["next_title"] = float(bool(next_lines) and bool(re.match(r"\s*[A-Z][a-z]", next_lines[0])))
    f["next_date"] = float(any(_DATE.search(x) for x in next_lines[:2]))
    f["prev_end_of"] = float(bool(prev_lines) and bool(_CUE_RE["end_of"].search(prev_lines[-1])))
    f["prev_num_line"] = float(bool(prev_lines) and bool(re.fullmatch(r"\s*\d{2,4}\.\d{3}-\d{1,4}\s*", prev_lines[-1])))
    f["prev_date_line"] = float(
        bool(prev_lines)
        and bool(
            _DATE.fullmatch(prev_lines[-1].strip())
            or re.fullmatch(r"\s*(?:\d{4}-\d{2}|[A-Z][a-z]{2} \d{4})\s*", prev_lines[-1])
        )
    )
    f["next_next_num"] = float(any(re.fullmatch(r"\s*\d{2,4}\.\d{3}-\d{1,4}\s*", x) for x in next_lines[:3]))
    f["roman_item"] = float(bool(_ROMAN_ITEM.match(line)))
    f["blank_item"] = float(bool(_BLANK_ITEM.match(line)))
    f["x_item"] = float(bool(_XMARK.match(line)))
    f["box_x"] = float(line.lstrip().startswith("⟦X⟧"))
    f["box_empty"] = float(line.lstrip().startswith("⟦ ⟧"))
    f["box_unknown"] = float(line.lstrip().startswith("⟦?⟧"))
    f["typed_box"] = float(bool(re.match(r"^\s*\[\s?[X ]?\s?\]", line)))
    f["toc_like"] = float(bool(_TOC.search(line)) and ("..." in line or len(line) > 20))
    f["bullet"] = float(line.lstrip().startswith(("▪", "•", "-", "*")))
    f["has_far_prefix"] = float(bool(re.search(r"\b(?:FAR|DFARS)\s+" + re.escape(num), line)))
    f["leading_marker_prefix"] = float(
        bool(re.match(r"^\s*(?:[A-Z]\.\d+|[IVX]+-\d+|\d+\.\d*)\s+" + re.escape(num), line))
    )
    f["alt"] = float(bool(item.get("alternate")))
    f["cited_date"] = float(bool(item.get("cited_date")))
    f["n_prev_nums"] = float(sum(len(re.findall(r"\d{2,4}\.\d{3}-\d", x)) for x in prev_lines))
    f["n_line_nums"] = float(len(re.findall(r"\d{2,4}\.\d{3}-\d", line)))
    f["semi_list"] = float(line.count(";") >= 2 and len(re.findall(r"\d{2,4}\.\d{3}-\d", line)) >= 2)
    f["after_semicolon"] = float(after.lstrip().startswith(";"))
    f["upper_ratio"] = float(sum(c.isupper() for c in line) / max(1, sum(c.isalpha() for c in line)))
    window = " ".join(prev_lines[-3:] + [line] + next_lines[:2])
    for k, rx in _CUE_RE.items():
        f["cue_" + k] = float(bool(rx.search(window)))
        f["cueL_" + k] = float(bool(rx.search(line)))
    heads = " > ".join(item.get("breadcrumb") or [])
    for k, rx in _HEAD_RE.items():
        f[k] = float(bool(rx.search(heads)))
    f["reg_" + str(item.get("registry_status") or "none")] = 1.0
    return f
