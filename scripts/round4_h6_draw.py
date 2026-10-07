"""H6 (docs/preregistration_round4.md): 60 mentions drawn at random (seed 13) from all rule-decided mentions of the round-3 documents."""

import json
import random
import re
from pathlib import Path

import pandas as pd

from fedproc_ledger.paths import PROCESSED

docs = Path("data/interim/round4_docs.txt").read_text().split()
rows = []
for d in docs:
    p = pd.read_parquet(PROCESSED / "predictions" / f"{d}.parquet")
    for i, r in p[p["source"] != "model"].iterrows():
        rows.append((d, int(i), r["number"], r["source"], r["role"]))
pick = random.Random(13).sample(rows, 60)
Path("data/audit/round4_h6_items.json").write_text(json.dumps(pick))
print(len(rows), "rule-decided mentions in the frame")
for k, (d, i, n, src, role) in enumerate(pick, 1):
    ctx = str(pd.read_parquet(PROCESSED / "predictions" / f"{d}.parquet").loc[i, "context"])
    rx = re.compile(re.escape(n).replace(r"\.", r"\s?[.]\s?").replace(r"\-", r"[-–]"))
    lines = [x.strip()[:100] for x in ctx.split("\n") if rx.search(x)]
    print(f"[{k}] {n} {src}:{role.replace('CHECKLIST_', '')} | " + " // ".join(lines[:2]))
