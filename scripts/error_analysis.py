"""List clean errors (agent and majority gold agree, model disagrees) for a gold file; used for development only.
usage: error_analysis.py <majority_gold> <agent_gold>"""

import collections
import json
import os
import sys
from pathlib import Path

import pandas as pd

from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED

PRED_DIR = Path(os.environ.get("PRED_DIR", str(PROCESSED / "predictions")))  # v2 predictions live elsewhere

g = json.loads(Path(sys.argv[1]).read_text())["gold"]
ag = json.loads(Path(sys.argv[2]).read_text())["gold"]
rows = []
for d, labs in g.items():
    pred = pd.read_parquet(PRED_DIR / f"{d}.parquet")
    agg: dict[str, float] = {}
    for (n, _a), v in ledger_for(pred).items():
        agg[n] = max(agg.get(n, 0), v)
    for n, label in labs.items():
        if n not in agg or label == "U" or ag[d].get(n) in (None, "U"):
            continue
        a = "B" if ag[d][n] == "B" else "N"
        if a != label:
            continue
        q = agg[n]
        if (label == "B") != (q >= 0.5):
            sub = pred[pred.number == n]
            r = sub.iloc[0]
            rows.append(
                (
                    label,
                    d[:6],
                    n,
                    round(q, 2),
                    collections.Counter(sub.role).most_common(2),
                    " // ".join(str(r.context).split("\n"))[:230],
                )
            )
print(len(rows), "clean errors;", collections.Counter(r[0] for r in rows))
for r in sorted(rows):
    print(r)
