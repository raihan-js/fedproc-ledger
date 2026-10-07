"""H6 (docs/preregistration_round2.md): 40 random rule-decided mentions from the round-2 documents (seed 7), printed for the agent to read."""

import json
import random
from pathlib import Path

import pandas as pd

from fedproc_ledger.paths import PROCESSED

docs = Path("data/interim/round2_docs.txt").read_text().split()
rows = []
for d in docs:
    p = pd.read_parquet(PROCESSED / "predictions" / f"{d}.parquet")
    b = p[p["source"] == "box_rule"]
    for i, r in b.iterrows():
        rows.append((d, int(i), r["number"], r["role"], " / ".join(str(r["context"]).split("\n"))[:260]))
rng = random.Random(7)
pick = rng.sample(rows, 40)
Path("data/audit/round2_h6_items.json").write_text(json.dumps(pick))
print(len(rows), "rule-decided mentions in the frame")
for k, (_d, _i, n, role, t) in enumerate(pick, 1):
    print(f"[{k}] {n} rule={role} | {t}")
