"""Does the feature model survive stricter grouping? Compare document, solicitation and department folds, with and
without TF-IDF of the context text. Hard (non-box) mentions are scored; box items stay in the training folds."""

import json

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.multiclass import OneVsRestClassifier

from fedproc_ledger.eval.leaderboard import log_run
from fedproc_ledger.label.commands import build_items
from fedproc_ledger.paths import RESULTS
from fedproc_ledger.rules.baseline import BINDING

df = pd.read_parquet("data/interim/labeled_mentions.parquet")
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
df["solicitation"] = df["doc"].map(docs["solicitation_number"]).fillna(df["doc"])
df["department"] = df["doc"].map(docs["department"]).fillna("unknown")
ctx = {}
for d in df["doc"].unique():
    ctx.update({i["id"]: i["context"] for i in build_items(d)})
df["context"] = df["id"].map(ctx)
hard = (df["source"] != "slice_a").to_numpy()
y = df["label"].to_numpy()
Xf = DictVectorizer(sparse=True).fit_transform([json.loads(s) for s in df["feat"]])
print(
    len(df),
    "mentions;",
    df["doc"].nunique(),
    "docs;",
    df["solicitation"].nunique(),
    "solicitations;",
    df["department"].nunique(),
    "departments",
)


def run(group_col: str, text: bool, C: float = 0.5) -> dict[str, float]:
    groups = df[group_col].to_numpy()
    pred = np.empty(len(df), dtype=object)
    n = min(5, len(set(groups)))
    for tr, te in GroupKFold(n_splits=n).split(Xf, y, groups):
        if text:
            tv = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, max_features=8000, sublinear_tf=True)
            Xt = tv.fit_transform(df["context"].iloc[tr])
            X_tr = hstack([Xf[tr], Xt]).tocsr()
            X_te = hstack([Xf[te], tv.transform(df["context"].iloc[te])]).tocsr()
        else:
            X_tr, X_te = Xf[tr], Xf[te]
        m = OneVsRestClassifier(LogisticRegression(solver="liblinear", C=C, class_weight="balanced")).fit(X_tr, y[tr])
        pred[te] = m.predict(X_te)
    p, t = pred[hard], y[hard]
    return {
        "role_agreement": float((p == t).mean()),
        "binding_agreement": float(np.mean([(a in BINDING) == (b in BINDING) for a, b in zip(p, t, strict=True)])),
    }


for g, text in [("solicitation", True), ("department", False), ("department", True)]:
    if True:
        r = run(g, text)
        name = f"lr {'features+tfidf' if text else 'features'} | groups={g}"
        log_run(RESULTS / "leaderboard.jsonl", name, {"groups": g, "tfidf": text}, r, split="cv-labelled-hard")
        print(f"{name:46s} role {r['role_agreement']:.3f}  binding {r['binding_agreement']:.3f}")
