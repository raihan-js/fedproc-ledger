"""The Python port of VETR's clause patterns must give exactly the numbers VETR's own PHP gives.

`tests/fixtures/vetr_parity_expected.json` was produced by `scripts/php/vetr_clauses.php` running VETR's
FarClauseDetectionService::extractClauseNumbers on `vetr_parity_cases.json` (real lines from solicitations, lines without
clause numbers, and edge cases). A second test re-runs the PHP when php and a VETR checkout are available.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fedproc_ledger.candidates.patterns import CLAUSE_PATTERNS, extract_clause_numbers

FIX = Path(__file__).parent / "fixtures"
CASES = json.loads((FIX / "vetr_parity_cases.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIX / "vetr_parity_expected.json").read_text(encoding="utf-8"))


def test_there_are_sixteen_patterns_in_vetrs_order():
    assert [n for n, _ in CLAUSE_PATTERNS] == [
        "NFS", "HSAR", "HUDAR", "AFARS", "DAFFARS", "NMCARS", "SOFARS", "DFARS", "GSAM", "DOSAR", "AIDAR", "DEAR", "VAAR", "HHSAR", "AGAR", "FAR",
    ]  # fmt: skip


def test_every_case_matches_the_recorded_vetr_output():
    assert len(CASES) == len(EXPECTED) >= 400
    bad = [
        (c, sorted(extract_clause_numbers(c)), sorted(e))
        for c, e in zip(CASES, EXPECTED, strict=True)
        if set(extract_clause_numbers(c)) != set(e)
    ]
    assert not bad, bad[:3]


def test_the_known_quirks_of_the_status_quo_are_preserved():
    # these are VETR's behaviours, kept on purpose: this module is baseline B0 and must not "fix" them
    assert extract_clause_numbers("$52.212 is not a clause") == ["52.212"]  # money is matched
    assert extract_clause_numbers("52.212‑4") == ["52.212"]  # a non-breaking hyphen cuts the number
    assert extract_clause_numbers("52. 212-4") == []  # a stray space hides it
    assert extract_clause_numbers("1852.219-73") == ["1852.219-73"]  # not also 52.219-73 (digit lookbehind)


@pytest.mark.skipif(not (shutil.which("php") and os.environ.get("VETR_PATH")), reason="needs php and VETR_PATH")
def test_the_php_oracle_still_agrees_with_the_recorded_output():
    out = subprocess.run(
        ["php", str(Path(__file__).parent.parent / "scripts/php/vetr_clauses.php"), str(FIX / "vetr_parity_cases.json")],
        capture_output=True, text=True, check=True, env={**os.environ},
    )  # fmt: skip
    assert json.loads(out.stdout) == EXPECTED
