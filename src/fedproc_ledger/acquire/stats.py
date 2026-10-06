"""documents.parquet and acquisition_stats.json, built from the download journal, the notices and the API call log."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_documents(journal: list[dict[str, Any]], notices: pd.DataFrame) -> pd.DataFrame:
    """One row per stored (notice, file). `doc_id` is the first 16 hex of the sha256; `duplicate` marks content already
    stored from an earlier row. `license_flag` stays `unknown` until the marking filter runs in Phase 3."""
    meta = notices.set_index("notice_id")
    rows = []
    seen: set[str] = set()
    done_pairs: set[tuple[str, str]] = set()
    for e in journal:
        if e.get("event") != "file" or e.get("status") != "ok":
            continue
        if (e["notice_id"], e["sha256"]) in done_pairs:  # an interrupted notice that was re-run repeats its files
            continue
        done_pairs.add((e["notice_id"], e["sha256"]))
        n = meta.loc[e["notice_id"]]
        sha = e["sha256"]
        rows.append(
            {
                "doc_id": sha[:16],
                "notice_id": e["notice_id"],
                "solicitation_number": n["solicitation_number"],
                "resource_id": e.get("resource_id"),
                "filename": e.get("name") or e.get("filename"),
                "file_type": e["ext"].lstrip("."),
                "size_bytes": e["bytes"],
                "posted_date": n["posted_date"],
                "agency": n["agency"],
                "department": n["department"],
                "set_aside_type": n.get("set_aside_type"),
                "naics": n.get("naics"),
                "notice_type": n["notice_type"],
                "source_url": e.get("source_url"),
                "download_ts": e["ts"],
                "sha256": sha,
                "duplicate": sha in seen,
                "license_flag": "unknown",
                "oversample": False,
            }
        )
        seen.add(sha)
    return pd.DataFrame(rows)


def acquisition_stats(
    journal: list[dict[str, Any]], docs: pd.DataFrame, notices: pd.DataFrame, api_log: list[dict[str, Any]]
) -> dict[str, Any]:
    files = [e for e in journal if e.get("event") == "file"]
    done = [e for e in journal if e.get("event") == "notice_done"]
    failed = [e for e in journal if e.get("event") == "notice_failed"]
    by_status = Counter(e["status"] for e in files)
    reasons = Counter((e["status"], e.get("reason")) for e in files if e["status"] != "ok")
    unique = docs[~docs["duplicate"]] if len(docs) else docs
    return {
        "notices_selected": int(len(notices)),
        "notices_done": len({e["notice_id"] for e in done}),
        "notices_failed_attachment_list": len({e["notice_id"] for e in failed}),
        "notices_with_no_stored_file": int(sum(1 for e in done if e.get("n_stored", 0) == 0)),
        "files_by_status": dict(by_status),
        "files_not_stored_by_reason": {f"{s}:{r}": c for (s, r), c in reasons.most_common()},
        "documents_rows": int(len(docs)),
        "documents_unique_sha256": int(len(unique)),
        "bytes_unique": int(unique["size_bytes"].sum()) if len(unique) else 0,
        "by_file_type": dict(Counter(unique["file_type"])) if len(unique) else {},
        "by_department": dict(Counter(docs["department"])) if len(docs) else {},
        "by_month": dict(sorted(Counter(docs["posted_date"].str[:7]).items())) if len(docs) else {},
        "documents_per_notice_median": float(docs.groupby("notice_id").size().median()) if len(docs) else None,
        "api_calls": {
            "total": len(api_log),
            "by_path": dict(
                Counter(r["path"].split("/")[1] if r["path"].count("/") > 1 else r["path"] for r in api_log)
            ),
            "by_status": {str(k): v for k, v in Counter(r.get("status") for r in api_log).items()},
        },
    }
