"""Temporal hold-out (D-042): fetch solicitations posted after the last acquisition day (2026-09-29) through the GovCon API
(the same client, config, quota reserve and download code as `fl acquire`), unique solicitation numbers not seen before.
Writes data/raw/search_new/*.json.gz, data/interim/notices_new.parquet and downloads into data/raw/files (own journal)."""

import sys
import time
from datetime import date, timedelta

import httpx
import pandas as pd

from fedproc_ledger.acquire.commands import _limit_after_first_call, make_client, reserve_for
from fedproc_ledger.acquire.download import Journal, run_download
from fedproc_ledger.acquire.pool import build_pool, load_search_days
from fedproc_ledger.acquire.ratelimit import TokenBucket
from fedproc_ledger.acquire.search import fetch_day, with_quota_wait
from fedproc_ledger.config import load_config
from fedproc_ledger.paths import DATA

cfg = load_config("acquisition")
first, last = date(2026, 9, 30), date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 10, 7)
days = [first + timedelta(days=i) for i in range((last - first).days + 1) if (first + timedelta(days=i)).weekday() < 5]
out_dir = DATA / "raw" / "search_new"
client = make_client(cfg)
client.budget.reserve = reserve_for(cfg, _limit_after_first_call(client))
for d in days:
    r = with_quota_wait(client, lambda d=d: fetch_day(client, d, cfg, out_dir), log=print)
    print(r, "| remaining", client.budget.remaining)
df = load_search_days(out_dir)
old = set(pd.read_parquet("data/interim/notices_ranked.parquet")["solicitation_number"].astype(str))
ranked, stats = build_pool(df, 400, 0.30, 20261021)
ranked = ranked[~ranked["solicitation_number"].astype(str).isin(old)].copy()
ranked["selected"] = True
ranked["rank"] = range(len(ranked))
ranked.to_parquet(DATA / "interim" / "notices_new.parquet", index=False)
print(len(ranked), "new unique solicitations;", stats["unique_solicitations"], "before the novelty filter")
d = cfg["download"]
journal = Journal(DATA / "interim" / "download_journal_new.jsonl")
todo = [
    {str(k): v for k, v in r.items()} for r in ranked.to_dict("records") if r["notice_id"] not in journal.done_notices
]
http = httpx.Client(
    follow_redirects=True,
    max_redirects=d["max_redirects"],
    timeout=d["timeout_s"],
    headers={"User-Agent": d["user_agent"]},
)
try:
    print(
        run_download(
            client,
            http,
            todo,
            cfg,
            journal,
            DATA / "raw" / "files",
            workers=d["workers"],
            bucket=TokenBucket(1.0 / d["min_seconds_between_downloads"]),
            log=print,
            sleep=time.sleep,
        )
    )
finally:
    http.close()
