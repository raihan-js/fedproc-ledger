"""Number-level stacker on rounds 2-4 (development data), grouped CV by document; compares with max-q. Exploratory (D-038)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from fedproc_ledger.model.commands import ledger_for

DIRS = {"round2": "predictions_v12", "round3": "predictions_v12", "round4": "predictions"}
ROLES = ["INCORPORATED_BY_REFERENCE", "FULL_TEXT", "CHECKLIST_SELECTED", "CHECKLIST_NOT_SELECTED", "INTERNAL_REFERENCE",
         "NARRATIVE_MENTION", "INDEX_ENTRY", "NOT_A_CLAUSE"]  # fmt: skip
rows = []
for rnd, pd_dir in DIRS.items():
    agent = json.loads(Path(f"results/ledger_gold_{rnd}_agent.json").read_text())["gold"]
    maj = json.loads(
        Path(f"results/ledger_gold_{'round2v2' if rnd == 'round2' else rnd}_majority_binding.json").read_text()
    )["gold"]
    for d, labs in agent.items():
        pred = pd.read_parquet(Path("data/processed") / pd_dir / f"{d}.parquet")
        qm = {n: v for (n, _a), v in ledger_for(pred, "max").items()}
        qn: dict[str, float] = {}
        for (n, _a), v in ledger_for(pred, "noisy_or").items():
            qn[n] = max(qn.get(n, 0), v)
        for n, g in pred.groupby("number"):
            a = labs.get(n)
            if a not in ("B", "N", "R"):
                continue
            f = {"qmax": qm.get(n, 0), "qnor": qn.get(n, 0), "n": len(g), "n_model": int((g.source == "model").sum()),
                 "n_rule": int((g.source != "model").sum()), "bp_mean": g.binding_prob.mean(), "bp_min": g.binding_prob.min()}  # fmt: skip
            for r in ROLES:
                col = f"p_{r}"
                f["max_" + r] = float(g[col].max()) if col in g else 0.0
            rows.append({"round": rnd, "doc": d, "number": n, "y": a == "B", "maj": maj.get(d, {}).get(n), **f})
df = pd.DataFrame(rows)
feat = [c for c in df.columns if c not in ("round", "doc", "number", "y", "maj")]
print(len(df), "numbers;", df.y.mean().round(3), "binding share")
oof = {"lr": np.zeros(len(df)), "hgb": np.zeros(len(df))}
for tr, te in GroupKFold(n_splits=5).split(df, df.y, df.doc):
    X, y = df.loc[tr, feat].values, df.y.values[tr]
    lr = LogisticRegression(max_iter=2000, C=1.0).fit(X, y)
    oof["lr"][te] = lr.predict_proba(df.loc[te, feat].values)[:, 1]
    hg = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=120, l2_regularization=1.0).fit(X, y)
    oof["hgb"][te] = hg.predict_proba(df.loc[te, feat].values)[:, 1]
y = df.y.values
for name, q in [("max-q", df.qmax.values), ("lr", oof["lr"]), ("hgb", oof["hgb"])]:
    pred = q >= 0.5
    tp, fp, fn, tn = ((pred & y).sum(), (pred & ~y).sum(), (~pred & y).sum(), (~pred & ~y).sum())
    f1 = 2 * tp / (2 * tp + fp + fn)
    err = pred != y
    qu = (q > 0.1) & (q < 0.9)
    print(
        f"{name:6s} AUC {roc_auc_score(y, q):.3f} F1 {f1:.3f} rec {tp / (tp + fn):.3f} spec {tn / (tn + fp):.3f} | queue {qu.mean():.2f} holds {err[qu].sum() / err.sum():.2f} of errors, acc outside {1 - err[~qu].mean():.3f}"
    )
