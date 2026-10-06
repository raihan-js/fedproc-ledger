"""`fl acquire ...`: Phase 1 commands (probe, search, pool, download, stats)."""

from __future__ import annotations

import json
import math
import time
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import typer

from fedproc_ledger.acquire.budget import CallBudget
from fedproc_ledger.acquire.download import Journal, run_download
from fedproc_ledger.acquire.govcon import BudgetStop, GovConClient, GovConError
from fedproc_ledger.acquire.pool import build_pool, load_search_days
from fedproc_ledger.acquire.ratelimit import TokenBucket
from fedproc_ledger.acquire.sampling import month_list, sample_days
from fedproc_ledger.acquire.search import day_path, fetch_day, with_quota_wait
from fedproc_ledger.acquire.stats import acquisition_stats, build_documents, read_jsonl
from fedproc_ledger.config import load_config
from fedproc_ledger.envfile import load_env, require
from fedproc_ledger.manifest import write_manifest
from fedproc_ledger.paths import DATA, RESULTS

acquire_app = typer.Typer(help="Phase 1: GovCon search, notice pool, attachment download.", no_args_is_help=True)
LOG = DATA / "logs" / "api_calls.jsonl"
_SAFE = ("plan", "tier", "limit", "remaining", "reset", "quota", "usage", "window", "period", "status")


def make_client(cfg: dict[str, Any], reserve: int | None = None) -> GovConClient:
    load_env()
    api = cfg["api"]
    budget = CallBudget(reserve=api["min_reserve"] if reserve is None else reserve, max_calls=api["max_calls_per_run"])
    return GovConClient(
        require("GOVCON_API_KEY"),
        api["base_url"],
        budget=budget,
        bucket=TokenBucket(api["calls_per_second"]),
        log_path=LOG,
    )


def safe_view(d: dict[str, Any]) -> dict[str, Any]:
    """Only plan/limit-like fields of a /me style payload (never names or emails)."""
    return {k: v for k, v in d.items() if any(s in k.lower() for s in _SAFE) and not isinstance(v, dict | list)}


def reserve_for(cfg: dict[str, Any], limit: int | None) -> int:
    api = cfg["api"]
    frac = math.ceil(api["reserve_fraction"] * limit) if limit else 0
    return int(max(api["min_reserve"], frac))


@acquire_app.command()
def probe() -> None:
    """Two real calls: /me (plan, quota) and a one-record search. Prints plan facts; never the key or personal data."""
    cfg = load_config("acquisition")
    client = make_client(cfg, reserve=0)
    try:
        me = client.me()
        typer.echo(f"/me (plan and limit fields only): {json.dumps(safe_view(me), indent=1)}")
        typer.echo(f"/me keys: {sorted(me)}")
        typer.echo(f"rate-limit headers: {client.last_rate_headers}")
        fields = ",".join(cfg["search"]["fields"]["list"])
        res = client.search(
            notice_type=",".join(cfg["search"]["notice_types"]),
            posted_from="2026-09-01",
            posted_to="2026-09-30",
            has_attachments=True,
            limit=1,
            fields=fields,
        )
    except (GovConError, BudgetStop) as e:
        typer.echo(f"probe failed: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"search window/pagination: window={res.get('window')} pagination={res.get('pagination')}")
    rec = (res.get("data") or [{}])[0]
    typer.echo(f"record fields returned: {sorted(rec)}")
    links = rec.get("resource_links_array")
    typer.echo(
        f"resource_links_array: type={type(links).__name__} len={len(links) if hasattr(links, '__len__') else None} "
        f"first={_shape(links[0]) if links else None}"
    )
    typer.echo(
        f"agency example: {rec.get('agency')!r}; agency_path_code={rec.get('agency_path_code')!r}; "
        f"notice_type={rec.get('notice_type')!r}; set_aside_type={rec.get('set_aside_type')!r}"
    )
    typer.echo(f"calls spent: {client.budget.spent_total}; remaining (header): {client.budget.remaining}")


@acquire_app.command()
def search(
    months_from: str = typer.Option(None, "--from", help="First month, YYYY-MM (default: configs/acquisition.toml)."),
    months_to: str = typer.Option(None, "--to", help="Last month, YYYY-MM."),
    days_per_month: int = typer.Option(None, help="Random weekdays per month (default from config)."),
    max_days: int = typer.Option(0, help="Stop after this many fetched days (0 = all); for trials."),
    dry_run: bool = typer.Option(False, help="Only print the days that would be fetched."),
) -> None:
    """Fetch the sampled search days (resumable: days already on disk are skipped)."""
    cfg = load_config("acquisition")
    s = cfg["sampling"]
    months = month_list(months_from or s["months_from"], months_to or s["months_to"])
    k = days_per_month or s["days_per_month"]
    days = [d for y, m in months for d in sample_days(y, m, k, s["seed"])]
    out_dir = DATA / "raw" / "search"
    todo = [d for d in days if not day_path(out_dir, d).exists()]
    typer.echo(
        f"{len(months)} months, {len(days)} sampled days, {len(todo)} not on disk yet (at least that many calls)"
    )
    if dry_run:
        typer.echo(", ".join(d.isoformat() for d in todo[:12]) + (" ..." if len(todo) > 12 else ""))
        return
    client = make_client(cfg)
    client.budget.reserve = reserve_for(cfg, _limit_after_first_call(client))
    typer.echo(
        f"reserve {client.budget.reserve} calls kept for other users of the key; remaining {client.budget.remaining}"
    )
    done = 0
    try:
        for d in todo:
            res = with_quota_wait(client, partial(fetch_day, client, d, cfg, out_dir), log=typer.echo)
            done += 1
            typer.echo(f"{res} | calls {client.budget.spent_total}, remaining {client.budget.remaining}")
            if max_days and done >= max_days:
                break
    except (GovConError, BudgetStop) as e:
        typer.echo(f"stopped: {e}", err=True)
        raise typer.Exit(code=1) from e


@acquire_app.command()
def pool() -> None:
    """Build the notice pool from the fetched days (data/interim/notices.parquet, results/pool_stats.json)."""
    cfg = load_config("acquisition")
    s = cfg["sampling"]
    df = load_search_days(DATA / "raw" / "search")
    ranked, stats = build_pool(
        df, s["candidate_target"], s["max_department_share"], s["seed"], s["months_from"], s["months_to"]
    )
    (DATA / "interim").mkdir(parents=True, exist_ok=True)
    light = ranked.drop(columns=["description_text"])
    light.to_parquet(
        DATA / "interim" / "notices_ranked.parquet", index=False
    )  # every unique solicitation with its rank
    ranked[ranked["selected"]].to_parquet(
        DATA / "interim" / "notices.parquet", index=False
    )  # selected, with description_text
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "pool_stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    inputs = sorted((DATA / "raw" / "search").glob("*.json.gz"))
    outputs = [
        DATA / "interim" / "notices.parquet",
        DATA / "interim" / "notices_ranked.parquet",
        RESULTS / "pool_stats.json",
    ]
    write_manifest("acquire.pool", inputs, outputs, {"sampling": s}, DATA / "interim" / "manifest_pool.json")
    typer.echo(
        json.dumps({k: v for k, v in stats.items() if not k.startswith(("selected_by_", "available_by_"))}, indent=1)
    )
    typer.echo(f"selected by department: {stats['selected_by_department']}")


@acquire_app.command()
def download(
    limit: int = typer.Option(0, help="Process at most this many notices (0 = all selected); for trials."),
    workers: int = typer.Option(
        0, help="Parallel downloads (default: configs/acquisition.toml; 1 request/s limit is shared)."
    ),
) -> None:
    """Attachment lists and downloads for the selected notices, in rank order. Resumable; stops at the disk cap."""
    cfg = load_config("acquisition")
    notices = pd.read_parquet(DATA / "interim" / "notices.parquet").sort_values("rank")
    journal = Journal(DATA / "interim" / "download_journal.jsonl")
    todo = [
        {str(k): v for k, v in r.items()}
        for r in notices.to_dict("records")
        if r["notice_id"] not in journal.done_notices
    ]
    if limit:
        todo = todo[:limit]
    typer.echo(f"{len(notices)} selected notices, {len(journal.done_notices)} done, {len(todo)} to do now")
    client = make_client(cfg)
    client.budget.reserve = reserve_for(cfg, _limit_after_first_call(client))
    d = cfg["download"]
    http = httpx.Client(
        follow_redirects=True,
        max_redirects=d["max_redirects"],
        timeout=d["timeout_s"],
        headers={"User-Agent": d["user_agent"]},
    )
    bucket = TokenBucket(1.0 / d["min_seconds_between_downloads"])
    try:
        out = run_download(
            client,
            http,
            todo,
            cfg,
            journal,
            DATA / "raw" / "files",
            workers=workers or d["workers"],
            bucket=bucket,
            log=typer.echo,
            sleep=time.sleep,
        )
    finally:
        http.close()
    typer.echo(f"finished: {out}")
    if out["stopped"]:
        raise typer.Exit(code=1)


@acquire_app.command()
def stats() -> None:
    """Write data/interim/documents.parquet and results/acquisition_stats.json from the journal and the call log."""
    notices = pd.read_parquet(DATA / "interim" / "notices.parquet")
    journal = read_jsonl(DATA / "interim" / "download_journal.jsonl")
    docs = build_documents(journal, notices)
    docs.to_parquet(DATA / "interim" / "documents.parquet", index=False)
    st = acquisition_stats(journal, docs, notices, read_jsonl(LOG))
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "acquisition_stats.json").write_text(
        json.dumps(st, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    outs = [DATA / "interim" / "documents.parquet", RESULTS / "acquisition_stats.json"]
    write_manifest(
        "acquire.stats",
        [DATA / "interim" / "notices.parquet", DATA / "interim" / "download_journal.jsonl"],
        outs,
        {},
        DATA / "interim" / "manifest_stats.json",
    )
    typer.echo(json.dumps(st, indent=1))


def _limit_after_first_call(client: GovConClient) -> int | None:
    client.refresh_quota()
    hdr = client.last_rate_headers.get("x-ratelimit-limit", "")
    return int(hdr) if hdr.isdigit() else None


def _shape(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: type(v).__name__ for k, v in x.items()}
    return type(x).__name__ if not isinstance(x, str) else f"str(len={len(x)}, starts={x[:30]!r}...)"


def data_path(*parts: str) -> Path:
    return DATA.joinpath(*parts)
