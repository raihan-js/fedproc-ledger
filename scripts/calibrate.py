"""Calibration and abstention on out-of-fold predictions of the feature classifier (EVALUATION_DESIGN.md 2, 3).

OOF probabilities come from grouped folds (departments left out). One temperature is fitted on half of the
departments and evaluated on the other half. The abstention threshold is chosen on the same dev half and applied
unchanged to the held-out half.
"""

import json

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.multiclass import OneVsRestClassifier

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.eval.leaderboard import log_run
from fedproc_ledger.label.commands import build_items
from fedproc_ledger.paths import RESULTS
from fedproc_ledger.rules.baseline import BINDING

df = pd.read_parquet("data/interim/labeled_mentions.parquet")
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
df["department"] = df["doc"].map(docs["department"]).fillna("unknown")
ctx = {}
for d in df["doc"].unique():
    ctx.update({i["id"]: i["context"] for i in build_items(d)})
df["context"] = df["id"].map(ctx)
y = df["label"].to_numpy()
hard = (df["source"] != "slice_a").to_numpy()
Xf = DictVectorizer(sparse=True).fit_transform([json.loads(s) for s in df["feat"]])
classes = sorted(set(y))
P = np.zeros((len(df), len(classes)))
for tr, te in GroupKFold(n_splits=5).split(Xf, y, df["department"].to_numpy()):
    tv = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, max_features=8000, sublinear_tf=True)
    Xtr = hstack([Xf[tr], tv.fit_transform(df["context"].iloc[tr])]).tocsr()
    Xte = hstack([Xf[te], tv.transform(df["context"].iloc[te])]).tocsr()
    m = OneVsRestClassifier(LogisticRegression(solver="liblinear", C=0.5, class_weight="balanced")).fit(Xtr, y[tr])
    p = m.predict_proba(Xte)
    P[te][:, : p.shape[1]] = 0
    for j, c in enumerate(m.classes_):
        P[te, classes.index(c)] = p[:, j]
P = P / P.sum(axis=1, keepdims=True)
lab = np.array([classes.index(v) for v in y])
logits = np.log(np.clip(P, 1e-9, 1))
bind_cols = [i for i, c in enumerate(classes) if c in BINDING]


def report(probs: np.ndarray, mask: np.ndarray, tag: str) -> dict[str, float]:
    b = probs[:, bind_cols].sum(axis=1)
    truth_b = np.array([classes[i] in BINDING for i in lab])
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == lab
    r = {
        "n": int(mask.sum()),
        "role_accuracy": float(correct[mask].mean()),
        "ece": M.ece(conf[mask], correct[mask]),
        "nll": M.nll(probs[mask], lab[mask]),
        "binding_brier": M.brier(b[mask], truth_b[mask]),
        "binding_aurc": M.risk_coverage(b[mask], truth_b[mask])["aurc"],
    }
    for tgt in (0.95, 0.98):
        c = M.choose_threshold(b[mask], truth_b[mask], target=tgt)
        r[f"cov@{int(tgt * 100)}"] = c["coverage"] if c else 0.0
        r[f"t@{int(tgt * 100)}"] = c["t"] if c else float("nan")
    print(tag, {k: round(v, 3) for k, v in r.items()})
    return r


raw = report(P, hard, "raw    ")
depts = sorted(df["department"].unique())
fit_mask = df["department"].isin(depts[::2]).to_numpy()  # temperature fitted on half the departments ...
T = M.fit_temperature(logits[fit_mask], lab[fit_mask])
Pt = M.softmax(logits, T)
test_mask = hard & ~fit_mask  # ... and evaluated on the other half
before = report(P, test_mask, "held-out raw ")
after = report(Pt, test_mask, f"held-out T={T:.2f}")
res = {"temperature": T, "all_hard_raw": raw, "heldout_raw": before, "heldout_scaled": after}
log_run(
    RESULTS / "leaderboard.jsonl",
    "calibration feature-model",
    {"T": T},
    {k: v for k, v in after.items() if isinstance(v, float)},
    split="cv-labelled-hard",
)
(RESULTS / "calibration.json").write_text(json.dumps(res, indent=1) + "\n")

# threshold chosen on the dev half (departments used to fit T), applied unchanged to the held-out half
b_all = Pt[:, bind_cols].sum(axis=1)
truth_all = np.array([classes[i] in BINDING for i in lab])
dev = hard & fit_mask
out = {}
for tgt in (0.95, 0.98):
    c = M.choose_threshold(b_all[dev], truth_all[dev], target=tgt)
    if not c:
        print("no threshold reaches", tgt)
        continue
    t = c["t"]
    conf = np.maximum(b_all, 1 - b_all)
    keep = test_mask & (conf >= t)
    acc = float(((b_all[keep] >= 0.5) == truth_all[keep]).mean()) if keep.any() else float("nan")
    out[str(tgt)] = {
        "t_from_dev": t,
        "dev_coverage": c["coverage"],
        "dev_accuracy": c["accuracy"],
        "test_coverage": float(keep.sum() / test_mask.sum()),
        "test_accuracy": acc,
        "test_n": int(test_mask.sum()),
    }
    print(
        f"target {tgt}: t={t:.3f} dev cov {c['coverage']:.3f} acc {c['accuracy']:.3f} | "
        f"held-out cov {out[str(tgt)]['test_coverage']:.3f} acc {acc:.3f} (n={int(test_mask.sum())})"
    )
res["threshold_dev_to_test"] = out
(RESULTS / "calibration.json").write_text(json.dumps(res, indent=1) + "\n")
