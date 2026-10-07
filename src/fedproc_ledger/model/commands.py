"""`fl model ...`: train the mention-role classifier and predict roles and ledger probabilities for documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import typer
from sklearn.model_selection import GroupKFold

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.label.commands import (
    bare_list_ids,
    build_items,
    inherited_ids,
    para_a_ids,
    slice_a_ids,
    text_rule_ids,
)
from fedproc_ledger.model import classifier as C
from fedproc_ledger.model.dataset import featurize_doc
from fedproc_ledger.paths import PROCESSED, RESULTS

model_app = typer.Typer(help="Mention-role classifier: train and predict.", no_args_is_help=True)
MODEL = Path("data/models/role_model.pkl")
PRED = PROCESSED / "predictions"
LABELLED = Path("data/interim/labeled_mentions.parquet")


@model_app.command()
def train(folds: int = typer.Option(5)) -> None:
    """Fit on every labelled mention (scripts/cv_features.py writes the table); T from grouped out-of-fold scores."""
    df = pd.read_parquet(LABELLED)
    docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
    df["department"] = df["doc"].map(docs["department"]).fillna("unknown")
    ctx: dict[str, str] = {}
    for d in df["doc"].unique():
        ctx.update({i["id"]: i["context"] for i in build_items(d)})
    feats = [json.loads(s) for s in df["feat"]]
    contexts = [ctx[i] for i in df["id"]]
    y = df["label"].tolist()
    classes = sorted(set(y))
    oof = np.zeros((len(df), len(classes)))
    for tr, te in GroupKFold(n_splits=folds).split(feats, y, df["department"]):
        m = C.fit([feats[i] for i in tr], [contexts[i] for i in tr], [y[i] for i in tr])
        pf = m.proba([feats[i] for i in te], [contexts[i] for i in te])
        for j, c in enumerate(m.classes):  # a fold may lack a rare class
            oof[te, classes.index(c)] = pf[:, j]
    lab = np.array([classes.index(v) for v in y])
    t = M.fit_temperature(np.log(np.clip(oof, 1e-9, 1)), lab)
    model = C.fit(feats, contexts, y, temperature=t)
    model.save(MODEL)
    typer.echo(f"trained on {len(df)} mentions, {df['doc'].nunique()} documents; temperature {t:.3f}; saved {MODEL}")


def predict_doc(model: C.RoleModel, doc_id: str) -> pd.DataFrame:
    items = build_items(doc_id)
    if not items:
        return pd.DataFrame()
    rows = featurize_doc(doc_id, items)
    truth = slice_a_ids(doc_id)
    para_a = para_a_ids(doc_id)
    text_rules = text_rule_ids(doc_id)
    bare = bare_list_ids(doc_id)
    for k, v in inherited_ids(doc_id).items():
        truth.setdefault(k, v)
    p = model.proba([r["feat"] for r in rows], [r["context"] for r in rows])
    b, e = model.binding_prob(p), model.exclusion_prob(p)
    out = []
    for r, pr, bi, ei in zip(rows, p, b, e, strict=True):
        role = model.classes[int(pr.argmax())]
        src = "model"
        if r["id"] in truth:  # checklist item line with a known box glyph: decided by rule
            role, src = truth[r["id"]], "box_rule"
            bi, ei = float(role == "CHECKLIST_SELECTED"), 0.0
        elif r["id"] in para_a:  # unconditional paragraph (a) of 52.212-5: binding (amendment A2)
            role, src = "INCORPORATED_BY_REFERENCE", "para_a_rule"
            bi, ei = 1.0, 0.0
        elif r["id"] in bare and r["id"] not in text_rules:  # bare list of clause numbers and titles (D-040)
            role, src = "INCORPORATED_BY_REFERENCE", "list_rule"
            bi, ei = 1.0, 0.0
        elif r["id"] in text_rules:  # conditional certificate, definition reference, "is applicable" statement
            binds = text_rules[r["id"]] == "BINDING"
            role, src = ("INCORPORATED_BY_REFERENCE" if binds else "INTERNAL_REFERENCE"), "text_rule"
            bi, ei = float(binds), 0.0
        out.append(
            {
                "cand_id": r["id"],
                "doc_id": doc_id,
                "number": r["number"],
                "alternate": r["alternate"],
                "role": role,
                "binding_prob": float(bi),
                "exclusion_prob": float(ei),
                "source": src,
                "confidence": float(max(bi, 1 - bi)),
                **{f"p_{c}": float(x) for c, x in zip(model.classes, pr, strict=True)},
                "line_text": r["line_text"],
                "box_marker": r["box_marker"],
                "b1": r["b1"],
                "context": r["context"],
            }
        )
    return pd.DataFrame(out)


@model_app.command()
def predict(
    docs: str = typer.Option("", help="file with doc ids (default: every document with candidates)"),
    limit: int = typer.Option(0),
    model_path: str = typer.Option(str(MODEL), "--model"),
    out_dir: str = typer.Option(str(PRED), "--out"),
) -> None:
    """Role and binding probability per candidate -> data/processed/predictions/<doc>.parquet."""
    model = C.RoleModel.load(Path(model_path))
    ids = (
        [x for x in Path(docs).read_text().split() if x]
        if docs
        else sorted(p.stem for p in (PROCESSED / "rules").glob("*.parquet") if not p.stem.startswith("_"))
    )
    if limit:
        ids = ids[:limit]
    pred_dir = Path(out_dir)
    pred_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, d in enumerate(ids):
        df = predict_doc(model, d)
        if len(df):
            df.to_parquet(pred_dir / f"{d}.parquet", index=False)
            n += len(df)
        if (i + 1) % 100 == 0:
            typer.echo(f"{i + 1}/{len(ids)} documents, {n} mentions")
    RESULTS.mkdir(exist_ok=True)
    typer.echo(f"predicted {n} mentions in {len(ids)} documents")


def ledger_for(df: pd.DataFrame, mode: str = "noisy_or") -> dict[tuple[str, str | None], float]:
    ms: list[dict[str, Any]] = [
        {
            "number": r.number,
            "alternate": r.alternate if isinstance(r.alternate, str) else None,
            "b": r.binding_prob,
            "e": r.exclusion_prob,
        }
        for r in df.itertuples()
    ]
    return M.ledger_probabilities(ms, mode=mode)
