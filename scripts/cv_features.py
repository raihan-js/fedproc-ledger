"""Kaggle-style loop (D-019): grouped CV of a feature classifier on the agent-labelled audit sets plus slice A.

Experiments: B1 alone, features only, features + B1 (the LLM-vote stacking rows were dropped with Qwen, D-021).
Every experiment is logged to results/leaderboard.jsonl. Groups are documents (so no document is in train and test).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold

from fedproc_ledger.eval.leaderboard import log_run
from fedproc_ledger.label.commands import build_items, slice_a_ids
from fedproc_ledger.model.features import mention_features
from fedproc_ledger.paths import PROCESSED, RESULTS
from fedproc_ledger.rules.baseline import BINDING

OUT = Path("data/interim/labeled_mentions.parquet")


def build_dataset() -> pd.DataFrame:
    labels: dict[str, tuple[str, str]] = {}
    for src in ("audit_claude_pilot", "audit_claude_round2"):
        for k, v in json.loads(Path(f"results/{src}.json").read_text())["labels"].items():
            if v != "UNCLEAR":
                labels[k] = (v, src)
    docs = sorted({k.rsplit("-p", 1)[0] for k in labels} | set(Path("data/interim/pilot_docs.txt").read_text().split()))
    rows = []
    for d in docs:
        a = slice_a_ids(d)
        for k, v in a.items():
            labels.setdefault(
                k, (v.replace("SELECTED", "CHECKLIST_SELECTED") if not v.startswith("CHECKLIST") else v, "slice_a")
            )
        want = {k for k in labels if k.startswith(d + "-")}
        if not want:
            continue
        rules = pd.read_parquet(PROCESSED / "rules" / f"{d}.parquet").set_index("cand_id")
        pg = pd.read_parquet(PROCESSED / "pages" / f"{d}.parquet", columns=["page", "text_layout"])
        pages = {int(str(r.page)): str(r.text_layout).split("\n") for r in pg.itertuples()}
        items = [i for i in build_items(d) if i["id"] in want]
        for it in items:
            r = rules.loc[it["id"]]
            lines = pages[int(r["page"])]
            li = int(r["line_no"])
            f = mention_features(
                {**it, "registry_status": r["registry_status"]},
                lines[max(0, li - 4) : li],
                lines[li + 1 : li + 4],
                lines[li],
            )
            role, src = labels[it["id"]]
            rows.append(
                {
                    "id": it["id"],
                    "doc": d,
                    "source": src,
                    "label": role,
                    "b1": it["b1"],
                    "b1_conf": float(r["confidence"]),
                    "section": str(r["section"]),
                    "vote": "NA",
                    "feat": json.dumps(f),
                }
            )
    return pd.DataFrame(rows)


def design(df: pd.DataFrame, use_b1: bool, use_vote: bool) -> list[dict[str, float]]:
    out = []
    for r in df.itertuples():
        f = dict(json.loads(str(r.feat)))
        if use_b1:
            f["b1=" + str(r.b1)] = 1.0
            f["b1_conf"] = float(r.b1_conf)
            f["sec=" + str(r.section)] = 1.0
        if use_vote:
            f["vote=" + str(r.vote)] = 1.0
        out.append(f)
    return out


def agreement(pred: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    return {
        "n": float(len(truth)),
        "role_agreement": float((pred == truth).mean()),
        "binding_agreement": float(
            np.mean([(p in BINDING) == (t in BINDING) for p, t in zip(pred, truth, strict=True)])
        ),
        "macro_f1": float(f1_score(truth, pred, average="macro")),
    }


def cv(df: pd.DataFrame, use_b1: bool, use_vote: bool, model: str, seed: int = 0) -> np.ndarray:
    X = DictVectorizer(sparse=False).fit_transform(design(df, use_b1, use_vote))
    y = df["label"].to_numpy()
    groups = df["doc"].to_numpy()
    pred = np.empty(len(df), dtype=object)
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        if model == "hgb":
            m = HistGradientBoostingClassifier(
                max_depth=4, learning_rate=0.08, max_iter=150, l2_regularization=1.0, random_state=seed
            )
        else:
            m = LogisticRegression(max_iter=2000, C=0.5, class_weight="balanced")
        m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return pred


def main() -> None:
    df = build_dataset() if "--rebuild" in sys.argv or not OUT.exists() else pd.read_parquet(OUT)
    df.to_parquet(OUT, index=False)
    print(len(df), "labelled mentions;", df["doc"].nunique(), "documents;", df["source"].value_counts().to_dict())
    truth = df["label"].to_numpy()
    hard = (df["source"] != "slice_a").to_numpy()  # the non-box mentions: where the methods differ
    preds = {
        "B1 alone": df["b1"].to_numpy(),
    }
    for name, b1, vote, model in [
        ("features (lr)", False, False, "lr"),
        ("features (hgb)", False, False, "hgb"),
        ("features+B1 (lr)", True, False, "lr"),
        ("features+B1 (hgb)", True, False, "hgb"),
    ]:
        preds[name] = cv(df, b1, vote, model)
    print(
        f"{'(non-box audit mentions only, n=' + str(int(hard.sum())) + ')':44s} role   binding macroF1 | box items role"
    )
    for name, pr in preds.items():
        m = agreement(pr[hard], truth[hard])
        box = float((pr[~hard] == truth[~hard]).mean())
        log_run(
            RESULTS / "leaderboard.jsonl",
            f"cv-hard {name}",
            {"experiment": name, "n": int(hard.sum())},
            {**m, "box_role_agreement": box},
            split="cv-labelled-hard",
        )
        print(f"{name:44s} {m['role_agreement']:.3f}  {m['binding_agreement']:.3f}  {m['macro_f1']:.3f}  | {box:.3f}")


if __name__ == "__main__":
    main()
