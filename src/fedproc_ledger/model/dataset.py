"""Turn a document's rules-stage candidates into model inputs: structural features plus the context text."""

from __future__ import annotations

from typing import Any

import pandas as pd

from fedproc_ledger.model.features import mention_features
from fedproc_ledger.paths import PROCESSED


def featurize_doc(doc_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per item: id, number, features (dict), context, and the rules-stage fields B1 produced.

    `items` come from `label.commands.build_items` (id, number, breadcrumb, context, alternate, cited_date, b1).
    """
    rules = pd.read_parquet(PROCESSED / "rules" / f"{doc_id}.parquet").set_index("cand_id")
    pg = pd.read_parquet(PROCESSED / "pages" / f"{doc_id}.parquet", columns=["page", "text_layout"])
    pages = {int(str(r.page)): str(r.text_layout).split("\n") for r in pg.itertuples()}
    out = []
    for it in items:
        r = rules.loc[it["id"]]
        lines = pages[int(r["page"])]
        li = int(r["line_no"])
        feats = mention_features(
            {**it, "registry_status": r["registry_status"]},
            lines[max(0, li - 4) : li],
            lines[li + 1 : li + 4],
            lines[li],
        )
        out.append(
            {
                "id": it["id"],
                "doc": doc_id,
                "number": it["number"],
                "alternate": it.get("alternate"),
                "feat": feats,
                "context": it["context"],
                "b1": it["b1"],
                "box_marker": r["box_marker"] if isinstance(r["box_marker"], str) else None,
                "line_text": str(r["line_text"]),
                "page": int(r["page"]),
                "from_range": bool(r["from_range"]),
            }
        )
    return out
