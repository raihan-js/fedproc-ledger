"""`fl extract ...`: Phase 3 commands."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

import pandas as pd
import typer

from fedproc_ledger.extract.run import process_document, read_summaries
from fedproc_ledger.manifest import write_manifest
from fedproc_ledger.paths import DATA, PROCESSED, RESULTS

extract_app = typer.Typer(help="Phase 3: layout-aware text extraction with checkbox markers.", no_args_is_help=True)
SUMMARIES = PROCESSED / "extract_docs.jsonl"
SHARDS = PROCESSED / "pages"


@extract_app.command()
def run(
    limit: int = typer.Option(0, help="Extract at most this many documents (0 = all); for trials."),
    workers: int = typer.Option(4, help="Parallel processes."),
) -> None:
    """Extract every unique downloaded document not yet done (resumable)."""
    docs = pd.read_parquet(DATA / "interim" / "documents.parquet").drop_duplicates("doc_id")
    done = {s["doc_id"] for s in read_summaries(SUMMARIES) if not s.get("error")}
    todo = [r for r in docs.to_dict("records") if r["doc_id"] not in done]
    if limit:
        todo = todo[:limit]
    typer.echo(f"{len(docs)} unique documents, {len(done)} done, {len(todo)} to do now")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    work = DATA / "tmp"
    n = 0
    with ProcessPoolExecutor(workers) as ex, open(SUMMARIES, "a", encoding="utf-8") as out:
        futs = {
            ex.submit(
                process_document,
                r["doc_id"],
                str(DATA / "raw" / "files" / f"{r['sha256']}.{r['file_type']}"),
                "." + r["file_type"],
                str(SHARDS),
                str(work),
            ): r["doc_id"]
            for r in todo
        }
        for f in as_completed(futs):
            out.write(json.dumps(f.result(), ensure_ascii=False) + "\n")
            out.flush()
            n += 1
            if n % 100 == 0:
                typer.echo(f"  {n}/{len(todo)} documents")
    typer.echo(f"extracted {n} documents into {SHARDS}")


@extract_app.command()
def stats() -> None:
    """Aggregate box-source counts, scanned share, markings and errors into results/extract_stats.json."""
    summaries = {s["doc_id"]: s for s in read_summaries(SUMMARIES)}  # the last line per document wins
    ok = [s for s in summaries.values() if not s.get("error")]
    boxes: dict[str, int] = {}
    pua: dict[str, int] = {}
    for s in ok:
        for k, v in s["box_counts"].items():
            boxes[k] = boxes.get(k, 0) + v
        for k, v in s["pua"].items():
            pua[k] = pua.get(k, 0) + v
    markings: dict[str, int] = {}
    mentions: dict[str, int] = {}
    for s in ok:
        for m in s["markings"]:
            markings[m] = markings.get(m, 0) + 1
        for m in s.get("marking_mentions", []):
            mentions[m] = mentions.get(m, 0) + 1
    errors: dict[str, int] = {}
    for s in summaries.values():
        if s.get("error"):
            key = s["error"].split(":")[0] + (":" + s["ext"])
            errors[key] = errors.get(key, 0) + 1
    out: dict[str, Any] = {
        "documents": len(summaries),
        "extracted": len(ok),
        "errors": errors,
        "pages": sum(s["n_pages"] for s in ok),
        "scanned_documents": sum(1 for s in ok if s["scanned"]),
        "documents_with_any_box": sum(1 for s in ok if s["box_counts"]),
        "documents_with_widgets": sum(1 for s in ok if any(k.startswith("widget") for k in s["box_counts"])),
        "box_counts_by_source_and_state": dict(sorted(boxes.items())),
        "unverified_private_use_codepoints": dict(sorted(pua.items(), key=lambda kv: -kv[1])),
        "documents_with_a_banner_marking": {k: v for k, v in sorted(markings.items())},
        "documents_with_any_banner_marking": sum(1 for s in ok if s["markings"]),
        "documents_mentioning_a_marking_keyword": {k: v for k, v in sorted(mentions.items())},
        "seconds_total": round(sum(s["seconds"] for s in summaries.values()), 1),
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "extract_stats.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_manifest(
        "extract.stats", [SUMMARIES], [RESULTS / "extract_stats.json"], {}, PROCESSED / "manifest_extract.json"
    )
    typer.echo(json.dumps(out, indent=1, ensure_ascii=False))
