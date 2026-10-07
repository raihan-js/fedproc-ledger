"""Rebuild data/release/mentions.parquet from current (v1.4) predictions.

For every document with a rules parquet: run predict_doc (current code),
collect mention rows, re-redact contexts, write the release table.
Long job: run detached, log to data/logs/rebuild_mentions.log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from fedproc_ledger.extract.privacy import redact
from fedproc_ledger.model.classifier import RoleModel
from fedproc_ledger.model.commands import MODEL, predict_doc
from fedproc_ledger.paths import PROCESSED

COLS = ["doc_id", "number", "alternate", "role", "binding_prob", "exclusion_prob",
        "source", "confidence", "context"]


def main() -> None:
    model = RoleModel.load(Path(MODEL))
    rules = sorted((PROCESSED / "rules").glob("*.parquet"))
    rules = [p for p in rules if not p.stem.startswith("_")]
    print(f"{len(rules)} rule files", flush=True)
    out = Path("data/release/mentions.parquet")
    frames = []
    for i, p in enumerate(rules):
        d = p.stem
        try:
            df = predict_doc(model, d)
        except Exception as e:  # noqa: BLE001 — one bad doc never stops the corpus
            print(f"  SKIP {d}: {type(e).__name__}", flush=True)
            continue
        if len(df):
            sub = df[["doc_id", "number", "alternate", "role", "binding_prob",
                      "exclusion_prob", "source", "confidence", "context"]].copy()
            sub["context"] = [redact(str(t))[:300] for t in sub["context"]]
            frames.append(sub)
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(rules)} docs", flush=True)
    m = pd.concat(frames, ignore_index=True)
    m.to_parquet(out, index=False)
    print(json.dumps({"documents": len(rules), "mentions": len(m)}), flush=True)


if __name__ == "__main__":
    sys.exit(main())
