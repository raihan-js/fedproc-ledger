"""Clause dates: `(OCT 2022)`, `Oct 2022`, `OCT. 2022`, `10/2022`, `October 2022`, `2022-10` all become `YYYY-MM`."""

from __future__ import annotations

import re

_MONTHS = {
    "JAN": 1, "JANUARY": 1, "FEB": 2, "FEBRUARY": 2, "MAR": 3, "MARCH": 3, "APR": 4, "APRIL": 4, "MAY": 5,
    "JUN": 6, "JUNE": 6, "JUL": 7, "JULY": 7, "AUG": 8, "AUGUST": 8, "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10, "NOV": 11, "NOVEMBER": 11, "DEC": 12, "DECEMBER": 12,
}  # fmt: skip
_NAME = re.compile(r"\b([A-Za-z]{3,9})\.?,?\s+((?:19|20)\d{2})\b")
_SLASH = re.compile(r"\b(\d{1,2})/((?:19|20)\d{2})\b")
_ISO = re.compile(r"\b((?:19|20)\d{2})-(\d{2})\b")


def normalize_clause_date(s: str | None) -> str | None:
    """The first month-year in `s` as `YYYY-MM`, or None. Never guesses a month from a bare year."""
    if not s:
        return None
    for m in _NAME.finditer(s):
        month = _MONTHS.get(m.group(1).upper())
        if month:
            return f"{m.group(2)}-{month:02d}"
    m2 = _SLASH.search(s)
    if m2 and 1 <= int(m2.group(1)) <= 12:
        return f"{m2.group(2)}-{int(m2.group(1)):02d}"
    m3 = _ISO.search(s)
    if m3 and 1 <= int(m3.group(2)) <= 12:
        return f"{m3.group(1)}-{m3.group(2)}"
    return None


def trailing_paren_date(s: str) -> str | None:
    """The date in a trailing parenthesis, e.g. 'Limitations on Subcontracting (OCT 2022)'."""
    m = re.search(r"\(([^()]*)\)\s*$", s.strip())
    return normalize_clause_date(m.group(1)) if m else None
