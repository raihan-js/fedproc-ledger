"""The legal and privacy filter (plan section 5.4): marking detection and PII redaction for released text."""

from __future__ import annotations

import re

# Markings that exclude a document from the public release (counted for internal statistics only).
MARKINGS: dict[str, re.Pattern[str]] = {
    "CUI": re.compile(r"\bCUI\b|Controlled Unclassified Information", re.I),
    "FOUO": re.compile(r"\bFOUO\b|For Official Use Only", re.I),
    "proprietary": re.compile(r"\bProprietary\b", re.I),
    "source_selection": re.compile(r"Source Selection Information", re.I),
    "distribution_statement": re.compile(r"Distribution\s+Statement\s+[B-F]\b", re.I),
    "export_control": re.compile(r"Export[- ]Controlled|\bITAR\b|\bEAR\s*99\b|International Traffic in Arms", re.I),
}
# "CUI" is also the name of a FAR/DFARS topic (e.g. "CUI" in 252.204-7012 text); a hit is a flag for the release step,
# not proof of a marking, so every hit is returned with its name and the release step decides.

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?<![\w.\-/$])(?:\+?1[\s.\-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.\-])\d{3}[\s.\-]\d{4}(?:\s?(?:x|ext\.?)\s?\d{1,5})?(?![\w\-/])"
)


def find_markings(text: str) -> list[str]:
    return sorted(name for name, pat in MARKINGS.items() if pat.search(text))


_CLAUSE_SHAPE = re.compile(r"\d{3,4}\.\d{3}-\d{4}")  # 252.204-7012 has a phone number's digit groups but mixes . and -


def _phone(m: re.Match[str]) -> str:
    return m.group(0) if _CLAUSE_SHAPE.fullmatch(m.group(0)) else "[PHONE]"


def redact(text: str) -> str:
    """Replace e-mail addresses and US-style phone numbers with [EMAIL] and [PHONE]; DFARS clause numbers are kept."""
    return _PHONE.sub(_phone, _EMAIL.sub("[EMAIL]", text))
