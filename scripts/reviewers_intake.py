"""Intake for reviewer labels: python scripts/reviewers_intake.py REVIEWER < labels.txt.

Input lines `DOC.ITEM: LETTER` (LETTER in BNRU, DOC.ITEM are the [doc.k] sheet ids).
Validates full coverage of the frozen sample, then writes
data/audit/reviewer_labels_<REVIEWER>.json. Combine reviewers with
scripts/reviewers_gold.py (majority) once two or more reviewers finish.
"""

import json
import sys
from pathlib import Path

name = sys.argv[1]
frozen = json.loads(Path("results/reviewer_docs_FROZEN.json").read_text())
keys = json.loads(Path("data/audit/reviewer_sheet_keys.json").read_text())
sample = json.loads(Path("data/audit/reviewer_sample_keys.json").read_text())
need = set()
for di, d in enumerate(frozen["docs"], 1):
    uni, smp = keys[d], set(sample[d])
    for k, n in enumerate(uni, 1):
        if n in smp:
            need.add(f"{di}.{k}")
got: dict[str, str] = {}
for line in sys.stdin:
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    key, _, val = line.partition(":")
    key, val = key.strip(), val.strip().upper()
    assert val in "BNRU", line
    got[key] = val
missing = sorted(need - set(got))
extra = sorted(set(got) - need)
print(f"{len(got)} labels, {len(need)} needed; missing {len(missing)}, extra {len(extra)}")
if missing[:5]:
    print("missing:", missing[:10])
if extra[:5]:
    print("extra:", extra[:10])
if missing or extra:
    raise SystemExit("coverage mismatch: fix the input and re-run")
Path(f"data/audit/reviewer_labels_{name}.json").write_text(json.dumps(got))
print("saved")
