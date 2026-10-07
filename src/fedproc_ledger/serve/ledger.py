"""One document in, one clause ledger out (docs/INTEGRATION_CONTRACT.md): extract, candidates, rules v1.2, role model.

Scratch shards live under data/processed with an `adhoc-` prefix and are removed afterwards; nothing else is written.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from fedproc_ledger.extract.pdf import page_row
from fedproc_ledger.extract.run import extract_file
from fedproc_ledger.model import classifier as C
from fedproc_ledger.model.commands import MODEL, ledger_for, predict_doc
from fedproc_ledger.paths import PROCESSED
from fedproc_ledger.rules.commands import load_registry, run_document

CONTRACT_VERSION = "0.2"
RULES_VERSION = "1.2"
HI, LO = 0.7, 0.3  # tier thresholds: configuration, not constants (contract section 3)
_MODEL: C.RoleModel | None = None


def _model() -> C.RoleModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = C.RoleModel.load(MODEL)
    return _MODEL


def ledger_for_file(path: Path, hi: float = HI, lo: float = LO) -> dict[str, Any]:
    """The contract's response for one PDF, DOCX, DOC or TXT file."""
    raw = path.read_bytes()
    doc_id = "adhoc-" + hashlib.sha1(raw).hexdigest()[:12]
    with tempfile.TemporaryDirectory() as work:
        pages = extract_file(path, path.suffix.lower(), Path(work))
    shard = PROCESSED / "pages" / f"{doc_id}.parquet"
    rules = PROCESSED / "rules" / f"{doc_id}.parquet"
    try:
        shard.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([page_row(doc_id, p) for p in pages]).to_parquet(shard, index=False)
        stats = run_document(doc_id, load_registry())
        registry = load_registry() or {}
        pred = predict_doc(_model(), doc_id)
        cand = pd.read_parquet(rules) if rules.exists() else pd.DataFrame()
    finally:
        for f in (shard, rules):
            f.unlink(missing_ok=True)
    scanned = bool(pages) and all(p.scanned for p in pages)
    warnings = ["no text layer: scanned document, no ledger produced"] if scanned else []
    entries: list[dict[str, Any]] = []
    if len(pred) and not scanned:
        where = cand.set_index("cand_id")[["page", "line_no"]] if len(cand) else pd.DataFrame()
        probs = ledger_for(pred, "max")
        for (number, alt), q in sorted(probs.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
            rows = pred[(pred["number"] == number) & (pred["alternate"].fillna("") == (alt or ""))]
            tier = "BINDING" if q >= hi else "NOT_BINDING" if q <= lo else "UNDETERMINED"
            decided = "model" if (rows["source"] == "model").any() else str(rows["source"].iloc[0])
            entries.append(
                {
                    "number": number,
                    "alternate": alt,
                    "tier": tier,
                    "q": round(float(q), 4),
                    "decided_by": decided,
                    "registry": {"status": registry.get(number, "unknown")},
                    "evidence": [
                        {
                            "page": int(where.loc[r.cand_id, "page"]) if r.cand_id in where.index else None,
                            "line": int(where.loc[r.cand_id, "line_no"]) if r.cand_id in where.index else None,
                            "role": r.role,
                            "p": round(float(r.binding_prob), 4),
                            "source": r.source,
                            "text": str(r.line_text)[:200],
                        }
                        for r in rows.head(5).itertuples()
                    ],
                }
            )
    summary = {
        "binding": sum(e["tier"] == "BINDING" for e in entries),
        "not_binding": sum(e["tier"] == "NOT_BINDING" for e in entries),
        "undetermined": sum(e["tier"] == "UNDETERMINED" for e in entries),
        "rule_decided_share": (sum(e["decided_by"] != "model" for e in entries) / len(entries) if entries else 0.0),
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "model": {
            "name": "role_model",
            "sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
            "rules_version": RULES_VERSION,
            "aggregation": "max over mentions",
        },
        "document": {
            "pages": len(pages),
            "scanned": scanned,
            "extraction_warnings": warnings,
            "candidates": stats["candidates"],
        },
        "entries": entries,
        "summary": summary,
    }
