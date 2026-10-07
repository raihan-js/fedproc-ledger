"""Train the number-level stacker (D-038) on the agent's number labels of rounds 2 to 4 and save data/models/stacker_v3.pkl."""

import hashlib
import json
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression

from fedproc_ledger.model.stacker import FEATURES, STACKER, Stacker, number_features

DIRS = {"round2": "predictions_v12", "round3": "predictions_v12", "round4": "predictions"}
X, y = [], []
for rnd, pdir in DIRS.items():
    gold = json.loads(Path(f"results/ledger_gold_{rnd}_agent.json").read_text())["gold"]
    for d, labs in gold.items():
        nf = number_features(pd.read_parquet(Path("data/processed") / pdir / f"{d}.parquet"))
        for n, a in labs.items():
            if a in ("B", "N", "R") and n in nf.index:
                X.append(nf.loc[n, FEATURES].values.astype(float))
                y.append(a == "B")
clf = LogisticRegression(max_iter=2000, C=1.0).fit(X, y)
Stacker(clf).save()
print(len(y), "numbers; sha256", hashlib.sha256(STACKER.read_bytes()).hexdigest()[:16])
