"""Fetch the sampled search days: one resumable gzip file per day under data/raw/search/."""

from __future__ import annotations

import gzip
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeVar

from fedproc_ledger.acquire.govcon import BudgetStop, GovConClient

T = TypeVar("T")


def with_quota_wait(
    client: GovConClient,
    fn: Callable[[], T],
    *,
    wait_s: float = 600.0,
    max_wait_s: float = 26 * 3600.0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> T:
    """Run fn; when the budget stops it at the reserve, wait, re-read the quota and try again.

    A local ceiling or an unknown quota is not waited out: those stops are re-raised.
    """
    waited = 0.0
    while True:
        try:
            return fn()
        except BudgetStop as e:
            if "reserve" not in str(e) or waited >= max_wait_s:
                raise
            log(f"[quota] {e}; waiting {int(wait_s)} s ({int(waited)} s so far), then re-reading the quota")
            sleep(wait_s)
            waited += wait_s
            client.refresh_quota()


def day_path(out_dir: Path, day: date) -> Path:
    return out_dir / f"{day.isoformat()}.json.gz"


def fetch_day(client: GovConClient, day: date, cfg: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Fetch every page for one posted-date day and write it atomically. Skips a day that is already on disk."""
    path = day_path(out_dir, day)
    if path.exists():
        return {"day": day.isoformat(), "skipped": True}
    s = cfg["sampling"]
    base = {
        "notice_type": ",".join(cfg["search"]["notice_types"]),
        "posted_from": day.isoformat(),
        "posted_to": day.isoformat(),
        "has_attachments": True,
        "sort_by": "posted_date",
        "fields": ",".join(cfg["search"]["fields"]["list"]),
    }
    records: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for offset, payload in client.iter_search_pages(s["per_day_limit"], **base):
        data = payload.get("data", [])
        records.extend(data)
        pages.append(
            {"offset": offset, "n": len(data), "pagination": payload.get("pagination"), "window": payload.get("window")}
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(
            {
                "day": day.isoformat(),
                "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "params": base,
                "pages": pages,
                "data": records,
            },
            f,
            ensure_ascii=False,
        )
    os.replace(tmp, path)
    last = pages[-1]["pagination"] or {}
    return {
        "day": day.isoformat(),
        "n": len(records),
        "pages": len(pages),
        "total": last.get("total"),
        "estimate": last.get("total_is_estimate"),
        "bytes": path.stat().st_size,
    }
