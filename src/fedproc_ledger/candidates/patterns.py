"""Port of VETR's clause-number patterns (app/Services/FarClauseDetectionService.php, 16 regexes).

Ordered longest-prefix first, each captures the number only. `extract_clause_numbers` reproduces VETR's
`extractClauseNumbers` (union of all patterns, unique, sorted); the parity test in tests/test_vetr_parity.py compares it
with VETR's own PHP on real and edge-case lines. Extensions (hyphen variants, spacing, ranges, ...) live elsewhere so
this module stays an exact port: it is also the status-quo baseline B0.
"""

from __future__ import annotations

import re

# (regulation, regex) in VETR's order. Flags: PHP /i, and PHP's \d is ASCII-only, hence re.ASCII.
_FLAGS = re.I | re.ASCII
_DIG = r"\d{3}(?:-\d{1,4})?"
CLAUSE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("NFS", re.compile(rf"(?:NFS\s+|(?<!\d))(1852\.{_DIG})", _FLAGS)),
    ("HSAR", re.compile(rf"(?:HSAR\s+|(?<!\d))(3052\.{_DIG})", _FLAGS)),
    ("HUDAR", re.compile(rf"(?:HUDAR\s+|(?<!\d))(2452\.{_DIG})", _FLAGS)),
    ("AFARS", re.compile(rf"(?:AFARS\s+|(?<!\d))(5152\.{_DIG})", _FLAGS)),
    ("DAFFARS", re.compile(rf"(?:DAFFARS\s+|(?<!\d))(5352\.{_DIG})", _FLAGS)),
    ("NMCARS", re.compile(rf"(?:NMCARS\s+|(?<!\d))(5252\.{_DIG})", _FLAGS)),
    ("SOFARS", re.compile(rf"(?:SOFARS\s+|(?<!\d))(7052\.{_DIG})", _FLAGS)),
    ("DFARS", re.compile(rf"(?:DFARS\s+|Section\s+|Clause\s+|(?<!\d))(252\.{_DIG})", _FLAGS)),
    ("GSAM", re.compile(rf"(?:GSAM\s+|(?<!\d))(552\.{_DIG})", _FLAGS)),
    ("DOSAR", re.compile(rf"(?:DOSAR\s+|(?<!\d))(652\.{_DIG})", _FLAGS)),
    ("AIDAR", re.compile(rf"(?:AIDAR\s+|(?<!\d))(752\.{_DIG})", _FLAGS)),
    ("DEAR", re.compile(rf"(?:DEAR\s+|(?<!\d))(952\.{_DIG})", _FLAGS)),
    ("VAAR", re.compile(rf"(?:VAAR\s+|(?<!\d))(852\.{_DIG})", _FLAGS)),
    ("HHSAR", re.compile(rf"(?:HHSAR\s+|(?<!\d))(352\.{_DIG})", _FLAGS)),
    ("AGAR", re.compile(rf"(?:AGAR\s+|(?<!\d))(452\.{_DIG})", _FLAGS)),
    ("FAR", re.compile(rf"(?:FAR\s+|Section\s+|Clause\s+|(?<!\d))(52\.{_DIG})", _FLAGS)),
]


def extract_clause_numbers(text: str) -> list[str]:
    """Unique clause numbers found by any VETR pattern. Order is not significant (VETR sorts with PHP's sort())."""
    found: set[str] = set()
    for _name, pat in CLAUSE_PATTERNS:
        found.update(pat.findall(text))
    return sorted(found)
