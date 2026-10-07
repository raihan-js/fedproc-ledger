"""Model v2 (D-034): v1 training table plus weak labels (two OpenAI voters agreeing, scripts/weak_labels.py); grouped CV for T.
Writes data/models/role_model_v2.pkl; never touches the frozen v1 file. Usage: train_v2.py [--no-weak]"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.label.commands import build_items
from fedproc_ledger.model import classifier as C
from fedproc_ledger.model.dataset import featurize_doc
from fedproc_ledger.rules.baseline import BINDING

OUT = Path(next((a.split("=")[1] for a in sys.argv if a.startswith("--out=")), "data/models/role_model_v2.pkl"))
base = pd.read_parquet("data/interim/labeled_mentions.parquet")
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
ctx: dict[str, str] = {}
feats: list[dict] = []
y: list[str] = []
grp: list[str] = []
src: list[str] = []
for d in base["doc"].unique():
    ctx.update({i["id"]: i["context"] for i in build_items(d)})
for r in base.itertuples():
    feats.append(json.loads(str(r.feat)))
    y.append(str(r.label))
    grp.append(str(docs.loc[r.doc, "department"]) if r.doc in docs.index else "unknown")
    src.append("v1")
contexts = [ctx[i] for i in base["id"]]
n_weak = 0


def ok(r: dict) -> bool:
    if "--no-checklist" in sys.argv and r["g41"].startswith("CHECKLIST"):
        return False
    return not ("--b1-agree" in sys.argv and (r["g41"] in BINDING) != (r["b1"] in BINDING))


if "--no-weak" not in sys.argv:
    for line in Path("data/interim/weak_labels.jsonl").read_text().splitlines():
        rec = json.loads(line)
        keep = {
            r["id"]: r["g41"]
            for r in rec["rows"]
            if r["g41"] and r["g41"] == r["g4o"] and r["g41"] != "UNCLEAR" and ok(r)
        }
        if not keep:
            continue
        items = [i for i in build_items(rec["doc"]) if i["id"] in keep]
        for row in featurize_doc(rec["doc"], items):
            feats.append(row["feat"])
            contexts.append(row["context"])
            y.append(keep[row["id"]])
            grp.append(str(docs.loc[rec["doc"], "department"]))
            src.append("weak")
            n_weak += 1
print("v1 rows", len(base), "weak rows", n_weak)
print(pd.Series(y).value_counts().to_dict())
classes = sorted(set(y))
oof = np.zeros((len(y), len(classes)))
for tr, te in GroupKFold(n_splits=5).split(feats, y, grp):
    m = C.fit([feats[i] for i in tr], [contexts[i] for i in tr], [y[i] for i in tr])
    pf = m.proba([feats[i] for i in te], [contexts[i] for i in te])
    for j, c in enumerate(m.classes):
        oof[te, classes.index(c)] = pf[:, j]
lab = np.array([classes.index(v) for v in y])
t = M.fit_temperature(np.log(np.clip(oof, 1e-9, 1)), lab)
model = C.fit(feats, contexts, y, temperature=t)
model.save(OUT)
weak = np.array([s == "weak" for s in src])
print(
    f"temperature {t:.3f}; OOF role accuracy weak {float((oof.argmax(1) == lab)[weak].mean()) if weak.any() else 0:.3f}; saved {OUT}"
)
