"""Temporal hold-out (D-042): extract + rules + predict the newer solicitations.

Reads data/interim/download_journal_new.jsonl (stored files), extracts only
doc_ids not already in data/processed/pages/, runs rules + frozen-model
prediction for the new doc_ids, and writes:
  data/interim/documents_new.parquet  (doc rows for the new files)
  data/processed/rules/<doc>.parquet   (same shared dir, keyed by doc_id)
  data/processed/predictions/<doc>.parquet
  results/newer_stats.json             (counts)

Idempotent: skips doc_ids already done. Run: uv run python scripts/process_newer.py
Log: data/logs/process_newer.log
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from fedproc_ledger.extract.run import process_document
from fedproc_ledger.model.classifier import RoleModel
from fedproc_ledger.model.commands import MODEL, predict_doc
from fedproc_ledger.paths import DATA, PROCESSED, RESULTS
from fedproc_ledger.rules.commands import load_registry, run_document

JOURNAL = DATA / "interim" / "download_journal_new.jsonl"
NOTICES = DATA / "interim" / "notices_new.parquet"
DOCS_NEW = DATA / "interim" / "documents_new.parquet"
PAGES = PROCESSED / "pages"
WORK = DATA / "tmp"


def main() -> None:
    journal = [json.loads(line) for line in JOURNAL.open(encoding="utf-8")]
    ok = [r for r in journal if r.get("status") == "ok" and r.get("sha256")]
    print(f"{len(ok)} stored files in the new journal", flush=True)

    notices = pd.read_parquet(NOTICES).set_index("notice_id")
    seen: dict[str, dict[str, str]] = {}
    for r in ok:
        sha = str(r["sha256"])
        if sha in seen:
            continue
        ext = str(r.get("ext", ".pdf"))
        path = DATA / "raw" / "files" / f"{sha}{ext}"
        if not path.exists():
            # try without dot confusion
            alt = DATA / "raw" / "files" / f"{sha}.{ext.lstrip('.')}"
            path = alt if alt.exists() else path
        if not path.exists():
            print(f"  MISSING file for sha {sha[:12]}", flush=True)
            continue
        n = notices.loc[r["notice_id"]] if r["notice_id"] in notices.index else None
        seen[sha] = {
            "doc_id": sha[:16],
            "sha256": sha,
            "file_type": ext.lstrip("."),
            "notice_id": str(r["notice_id"]),
            "solicitation_number": str(n["solicitation_number"]) if n is not None else "",
            "posted_date": str(n["posted_date"]) if n is not None else "",
            "department": str(n["department"]) if n is not None else "",
        }
    docs = pd.DataFrame(list(seen.values()))
    docs.to_parquet(DOCS_NEW, index=False)
    print(f"{len(docs)} unique new documents -> {DOCS_NEW}", flush=True)

    todo = [r for r in docs.to_dict("records") if not (PAGES / f"{r['doc_id']}.parquet").exists()]
    print(f"{len(todo)} need extraction ({len(docs) - len(todo)} already extracted)", flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "pages").mkdir(parents=True, exist_ok=True)
    summaries_path = PROCESSED / "extract_docs.jsonl"
    n = 0
    if todo:
        with ProcessPoolExecutor(4) as ex, summaries_path.open("a", encoding="utf-8") as out:
            futs = {
                ex.submit(
                    process_document,
                    r["doc_id"],
                    str(DATA / "raw" / "files" / f"{r['sha256']}.{r['file_type']}"),
                    "." + r["file_type"],
                    str(PAGES),
                    str(WORK),
                ): r["doc_id"]
                for r in todo
            }
            for f in as_completed(futs):
                out.write(json.dumps(f.result(), ensure_ascii=False) + "\n")
                out.flush()
                n += 1
                if n % 100 == 0:
                    print(f"  extracted {n}/{len(todo)}", flush=True)
    print(f"extracted {n} new documents", flush=True)

    registry = load_registry()
    print("registry: " + ("loaded" if registry else "NOT available"), flush=True)
    ids = [r["doc_id"] for r in docs.to_dict("records")]
    n_rules = n_cands = n_b0 = n_b1 = 0
    n_pred = 0
    model = RoleModel.load(Path(MODEL))
    pred_dir = PROCESSED / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(ids):
        if not (PAGES / f"{d}.parquet").exists():
            continue
        s = run_document(d, registry)
        n_rules += 1
        n_cands += s["candidates"]
        n_b0 += s["b0_ledger"]
        n_b1 += s["b1_ledger"]
        df = predict_doc(model, d)
        if len(df):
            df.to_parquet(pred_dir / f"{d}.parquet", index=False)
            n_pred += len(df)
        if (i + 1) % 100 == 0:
            print(f"  rules+predict {i + 1}/{len(ids)}", flush=True)
    stats = {
        "new_documents": len(docs),
        "extracted_now": n,
        "rules_run": n_rules,
        "candidates": n_cands,
        "b0_ledger_total": n_b0,
        "b1_ledger_total": n_b1,
        "predicted_mentions": n_pred,
    }
    (RESULTS / "newer_stats.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=1), flush=True)


if __name__ == "__main__":
    sys.exit(main())
