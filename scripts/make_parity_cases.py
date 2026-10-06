#!/usr/bin/env python3
"""Build tests/fixtures/vetr_parity_cases.json: real lines (redacted) from extracted documents, lines without clause
numbers, and hand-written edge cases. The expected outputs come from VETR's own PHP (scripts/php/vetr_clauses.php).

  make_parity_cases.py
  VETR_PATH=/path/to/VETR-Framework php scripts/php/vetr_clauses.php tests/fixtures/vetr_parity_cases.json \
      > tests/fixtures/vetr_parity_expected.json
"""

import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from fedproc_ledger.extract.privacy import redact  # noqa: E402

EDGE = [
    "FAR 52.212-4 and DFARS 252.204-7012",
    "see 52.212-5(b)(16) and 52.219-14.",
    "52.219-1 through 52.219-9",
    "Clause 52.204-21, Basic Safeguarding",
    "Section 252.225-7001 applies",
    "dfars 252.204-7012 lower case",
    "NFS 1852.219-73 and NFS1852.219-74",
    "HSAR 3052.204-71",
    "$52.212 is not a clause",
    "Total: $1,252.204 per unit",
    "52.212‑4 non-breaking hyphen",
    "52.212–4 en dash",
    "52.212—4 em dash",
    "52. 212-4 stray space",
    "52.212 -4 stray space before hyphen",
    "(52.212-4)",
    "[52.212-4]",
    "52.212-4,52.212-5",
    "1852.219-73 contains 52.219-73",
    "2452.219-70 HUDAR",
    "5152.201 AFARS",
    "5352.201 DAFFARS",
    "5252.201 NMCARS",
    "7052.201 SOFARS",
    "352.211-70 HHSAR and 552.212-71 GSAM",
    "652.242-70 DOSAR 752.202-1 AIDAR 952.223-71 DEAR 852.211-70 VAAR 452.211-70 AGAR",
    "CAGE 1AB52.123",
    "phone 252.204-7012",
    "version 52.1.3",
    "1252.204-7012 twelve fifty-two",
    "52.2123-4",
    "52.212-12345",
    "x52.212-4y",
    "52.212-4a",
    "",
    "no clause numbers here at all",
    "52.212 only",
    "252.204 only",
    "FAR52.212-4",
    "far 52.212-4",
    "FAR 52.212-4 nbsp",
    "FAR\n52.212-4 newline",
    "52.212-4\n52.212-5\n252.204-7012",
]


def main() -> None:
    rng = random.Random(20261006)
    has_num = re.compile(r"\d{2,4}\.\d{3}")
    with_num, without = [], []
    for f in sorted((ROOT / "data/processed/pages").glob("*.parquet")):
        df = pd.read_parquet(f, columns=["text_plain"])
        for t in df["text_plain"]:
            for line in str(t).splitlines():
                line = line.strip()
                if 12 <= len(line) <= 220:
                    (with_num if has_num.search(line) else without).append(redact(line))
    rng.shuffle(with_num)
    rng.shuffle(without)
    cases = EDGE + with_num[:260] + without[:100]
    out = ROOT / "tests/fixtures/vetr_parity_cases.json"
    out.write_text(json.dumps(cases, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(
        len(cases),
        "cases:",
        len(EDGE),
        "edge,",
        min(260, len(with_num)),
        "real with digits,",
        min(100, len(without)),
        "real without",
    )


if __name__ == "__main__":
    main()
