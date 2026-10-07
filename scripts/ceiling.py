"""Annotator ceiling (D-042): how well do the annotators agree with each other, and how does the model compare with them on the same items?
For rounds 3 to 6 (agent, gpt-4o-mini, gpt-4.1-mini labels; binding set: BINDS vs NOT/REFERENCED, undecided excluded), pooled over the rounds.
Reported: pairwise accuracy and kappa between annotators, and the model's (max-q >= 0.5) accuracy against each annotator."""

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED

R = Path("results")
PRED = {"round3": "predictions_v13", "round4": "predictions_v13", "round5": "predictions_v13", "round6": "predictions"}
ROUNDS = ["round3", "round4", "round5", "round6"]
MAP = {"B": 1, "N": 0, "R": 0}


def kappa(a: np.ndarray, b: np.ndarray) -> float:
    po = float((a == b).mean())
    pe = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


rows = []
for rnd in ROUNDS:
    ag = json.loads((R / f"ledger_gold_{rnd}_agent.json").read_text())["gold"]
    j1 = json.loads((R / f"ledger_gold_{rnd}_judge_gpt-4o-mini.json").read_text())["gold"]
    j2 = json.loads((R / f"ledger_gold_{rnd}_judge_gpt-4.1-mini.json").read_text())["gold"]
    for d, labs in ag.items():
        pred = pd.read_parquet(PROCESSED / PRED[rnd] / f"{d}.parquet")
        q: dict[str, float] = {}
        for (n, _a), v in ledger_for(pred, "max").items():
            q[n] = max(q.get(n, 0.0), v)
        for n, a in labs.items():
            rows.append(
                {"round": rnd, "doc": d, "n": n, "agent": MAP.get(a), "g4o": MAP.get(j1[d].get(n)), "g41": MAP.get(j2[d].get(n)),
                 "model": float(q.get(n, 0.0) >= 0.5)}
            )  # fmt: skip
df = pd.DataFrame(rows)
out: dict = {"numbers": int(len(df)), "pairs": {}, "model_vs": {}}
for a, b in itertools.combinations(["agent", "g4o", "g41"], 2):
    s = df.dropna(subset=[a, b])
    out["pairs"][f"{a}~{b}"] = {
        "n": len(s),
        "accuracy": float((s[a] == s[b]).mean()),
        "kappa": kappa(s[a].values, s[b].values),
    }
for a in ["agent", "g4o", "g41"]:
    s = df.dropna(subset=[a])
    out["model_vs"][a] = {
        "n": len(s),
        "accuracy": float((s[a] == s["model"]).mean()),
        "kappa": kappa(s[a].values, s["model"].values),
    }
# majority of the other two annotators as a reference for each annotator, and for the model
mv = {}
for a, (b, c) in {"agent": ("g4o", "g41"), "g4o": ("agent", "g41"), "g41": ("agent", "g4o")}.items():
    s = df.dropna(subset=[a, b, c])
    agree = s[b] == s[c]
    ref = s.loc[agree, b]
    mv[a] = {
        "n_items_where_other_two_agree": int(agree.sum()),
        "annotator_accuracy": float((s.loc[agree, a] == ref).mean()),
        "model_accuracy": float((s.loc[agree, "model"] == ref).mean()),
    }
out["against_agreeing_pair"] = mv
(R / "annotator_ceiling.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
