"""`fl extract ...`: Phase 3 commands."""

from __future__ import annotations

import json
import re
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


@extract_app.command()
def report(n: int = typer.Option(5, help="Number of pages to show.")) -> None:
    """HTML report (data/reports/extract_report.html): page images beside text_layout, markers highlighted."""
    from fedproc_ledger.extract.report import build_report, choose_pages, page_image_b64

    docs = pd.read_parquet(DATA / "interim" / "documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
    cands: list[dict[str, Any]] = []
    for f in sorted(SHARDS.glob("*.parquet")):
        df = pd.read_parquet(f)
        if docs.loc[df["doc_id"].iloc[0], "file_type"] != "pdf":
            continue
        for r in df.itertuples():
            counts = json.loads(str(r.box_signals))["counts"]
            by_source: dict[str, int] = {}
            for k, v in counts.items():
                by_source[k.split(":")[0]] = by_source.get(k.split(":")[0], 0) + v
            total = sum(counts.values())
            if total >= 3:
                checklist = int(bool(re.search(r"52\.212-5|52\.213-4|252\.212-7001", str(r.text_plain))))
                cands.append(
                    {
                        "doc_id": r.doc_id,
                        "page": r.page,
                        "layout": r.text_layout,
                        "counts": counts,
                        "by_source": by_source,
                        "total": total,
                        "checklist": checklist,
                    }
                )
    chosen = choose_pages(cands, n)
    rows = []
    for c in chosen:
        d = docs.loc[c["doc_id"]]
        rows.append(
            {
                "title": str(d["filename"]),
                "page": c["page"],
                "layout": c["layout"],
                "counts": c["counts"],
                "image_b64": page_image_b64(DATA / "raw" / "files" / f"{d['sha256']}.pdf", c["page"]),
            }
        )
    stats = (
        json.loads((RESULTS / "extract_stats.json").read_text()) if (RESULTS / "extract_stats.json").exists() else {}
    )
    out = DATA / "reports" / "extract_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_report(rows, stats), encoding="utf-8")
    typer.echo(f"wrote {out} ({len(rows)} pages from {len(cands)} candidate pages)")
