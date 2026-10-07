"""Number-level stacker: learn 'does this number bind' directly from the ledger gold, using features aggregated over the
mentions of the number, and compare with the noisy-OR of mention probabilities under document-grouped cross-validation.
Gold: development majority (25 docs) + first test majority, binding set (57 documents, B vs N/R, U excluded). Threshold-free
comparison: ROC-AUC, and specificity at 95% recall; plus P/R/F1/specificity at 0.5."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.model import classifier as C
from fedproc_ledger.model.commands import ledger_for, predict_doc
from fedproc_ledger.paths import PROCESSED

reg = pd.read_parquet(PROCESSED / "registry.parquet").set_index("number")
model = C.RoleModel.load(Path("data/models/role_model.pkl"))
gold: dict[str, dict[str, bool]] = {}
for f in ("ledger_gold_majority3.json", "ledger_gold_test_majority_binding.json"):
    for d, labels in json.loads((Path("results") / f).read_text())["gold"].items():
        gold[d] = {n: (v == "B") for n, v in labels.items() if v in ("B", "N", "R")}
ROLES = model.classes
rows = []
for d, labels in gold.items():
    pred = predict_doc(model, d)
    q = {}
    for (n, _a), v in ledger_for(pred).items():
        q[n] = max(q.get(n, 0.0), v)
    n_nums = pred["number"].nunique()
    doc_bind_share = float(np.mean([v >= 0.5 for v in q.values()])) if q else 0.0
    has_box = float((pred["source"] == "box_rule").any())
    for n, g in pred.groupby("number"):
        if n not in labels:
            continue
        f = {
            "n_mentions": len(g),
            "n_pages": g["doc_id"].map(lambda _: 0).size and g.get("page", pd.Series([0])).nunique(),
            "q_noisy": q[n],
            "b_max": g["binding_prob"].max(),
            "b_mean": g["binding_prob"].mean(),
            "b_min": g["binding_prob"].min(),
            "box_sel": float(((g["source"] == "box_rule") & (g["role"] == "CHECKLIST_SELECTED")).sum()),
            "box_not": float(((g["source"] == "box_rule") & (g["role"] == "CHECKLIST_NOT_SELECTED")).sum()),
            "row_start": float(np.mean([bool(re.search(re.escape(n), str(t)[:14])) for t in g["line_text"]])),
            "log_doc_numbers": float(np.log1p(n_nums)),
            "doc_bind_share": doc_bind_share,
            "doc_has_box": has_box,
            "in_registry": float(n in reg.index),
            "is_provision": float(n in reg.index and reg.loc[n, "kind"] == "provision"),
            "reserved": float(n in reg.index and reg.loc[n, "status"] != "active"),
            "fragment": float(not re.fullmatch(r"\d{2,4}\.\d{3}-\d{1,4}", n)),
        }
        for r in ROLES:
            f["pmax_" + r] = g["p_" + r].max()
            f["pmean_" + r] = g["p_" + r].mean()
        rows.append({"doc": d, "number": n, "y": labels[n], **f})
df = pd.DataFrame(rows)
feat = [c for c in df.columns if c not in ("doc", "number", "y")]
X, y, grp = df[feat].to_numpy(float), df["y"].to_numpy(bool), df["doc"].to_numpy()
print(len(df), "numbers,", df["doc"].nunique(), "documents,", int(y.sum()), "binding")


def curves(score: np.ndarray, tag: str) -> dict[str, float]:
    auc = roc_auc_score(y, score)
    order = np.sort(score[y])
    thr = order[int(0.05 * len(order))]  # threshold that keeps 95% of binding numbers
    spec95 = float((score[~y] < thr).mean())
    pred = score >= 0.5
    tp, fp, fn = float((pred & y).sum()), float((pred & ~y).sum()), float((~pred & y).sum())
    prf = M.prf(tp, fp, fn)
    out = {
        "auc": auc,
        "spec@recall95": spec95,
        "P@0.5": prf["precision"],
        "R@0.5": prf["recall"],
        "F1@0.5": prf["f"],
        "spec@0.5": float((~pred[~y]).mean()),
    }
    print(f"{tag:26s} " + "  ".join(f"{k} {v:.3f}" for k, v in out.items()))
    return out


res = {"noisy_or (frozen)": curves(df["q_noisy"].to_numpy(), "noisy-OR of mentions")}
for name, mk in [
    ("stacker LR", lambda: LogisticRegression(max_iter=3000, C=0.3, class_weight="balanced")),
    (
        "stacker HGB",
        lambda: HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.06, max_iter=120, l2_regularization=2.0, random_state=0
        ),
    ),
]:
    oof = np.zeros(len(df))
    for tr, te in GroupKFold(n_splits=6).split(X, y, grp):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        m = mk().fit((X[tr] - mu) / sd, y[tr])
        oof[te] = m.predict_proba((X[te] - mu) / sd)[:, 1]
    res[name] = curves(oof, name)
Path("results/number_stacker.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
