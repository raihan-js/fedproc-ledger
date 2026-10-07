"""One document in, one clause ledger out (docs/INTEGRATION_CONTRACT.md): extract, candidates, rules v1.4, role model.

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
from fedproc_ledger.model.stacker import STACKER, Stacker, number_features
from fedproc_ledger.paths import PROCESSED
from fedproc_ledger.rules.commands import load_registry, run_document

CONTRACT_VERSION = "0.3"
RULES_VERSION = "1.4"
HI, LO = 0.7, 0.3  # tier thresholds: configuration, not constants (contract section 3)
RFO = "2025-10-28"
_MODEL: C.RoleModel | None = None


def _versions() -> Any:
    path = PROCESSED / "registry.parquet"
    return pd.read_parquet(path).set_index("number") if path.exists() else None


def _in_force(reg: Any, number: str, day: str) -> str | None:
    if number not in reg.index:
        return None
    for v in reg.loc[number, "versions"]:
        live = v["effective_from"] <= day and (v["effective_to"] is None or day <= v["effective_to"])
        if live and v["present"] and not v["reserved"]:
            return str(v["clause_date"])
    return None


def _currency(reg: Any, number: str, cited: str | None, day: str | None) -> dict[str, Any]:
    """Cited date against the version in force on the posting day (eCFR history); RFO-era notices are not judged."""
    out: dict[str, Any] = {"cited_date": cited, "version_in_force": None, "currency": "unknown_posted_date"}
    if not day or reg is None:
        return out
    if day >= RFO:
        return {**out, "currency": "rfo_era_not_judged"}
    force = _in_force(reg, number, day)
    out["version_in_force"] = force
    if cited is None:
        out["currency"] = "no_date_cited"
    elif force is None:
        out["currency"] = "no_version_data"
    else:
        out["currency"] = "matches" if cited == force else "older" if cited < force else "newer"
    return out


def _model() -> C.RoleModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = C.RoleModel.load(MODEL)
    return _MODEL


def ledger_for_file(path: Path, hi: float = HI, lo: float = LO, posted_date: str | None = None) -> dict[str, Any]:
    """The contract's response for one PDF, DOCX, DOC or TXT file; `posted_date` (YYYY-MM-DD) enables currency."""
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
        pred: Any = predict_doc(_model(), doc_id)
        cand: Any = pd.read_parquet(rules) if rules.exists() else pd.DataFrame()
    finally:
        for f in (shard, rules):
            f.unlink(missing_ok=True)
    scanned = bool(pages) and all(p.scanned for p in pages)
    warnings = ["no text layer: scanned document, no ledger produced"] if scanned else []
    entries: list[dict[str, Any]] = []
    if len(pred) and not scanned:
        where: Any = cand.set_index("cand_id")[["page", "line_no"]] if len(cand) else pd.DataFrame()
        probs = ledger_for(pred, "max")
        if (
            STACKER.exists()
        ):  # number-level stacker over the mention probabilities (D-038); rule-only numbers keep their rule value
            nf: Any = number_features(pred)
            sq = dict(zip(nf.index, Stacker.load().proba(nf), strict=True))
            probs = {(n, a): (float(sq[n]) if nf.loc[n, "n_model"] > 0 else q) for (n, a), q in probs.items()}
        reg_versions = _versions() if posted_date else None
        dates = (
            cand.dropna(subset=["cited_date"]).groupby("number")["cited_date"].agg(lambda x: x.value_counts().index[0])
            if len(cand) and "cited_date" in cand
            else pd.Series(dtype=object)
        )
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
                    "registry": {
                        "status": registry.get(number, "unknown"),
                        **_currency(reg_versions, number, dates.get(number), posted_date),
                    },
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
