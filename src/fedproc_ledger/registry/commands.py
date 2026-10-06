"""`fl registry ...`: Phase 2 commands."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import typer

from fedproc_ledger.manifest import write_manifest
from fedproc_ledger.paths import DATA, PROCESSED, RESULTS
from fedproc_ledger.registry.build import build_part, to_frame, x52_parts
from fedproc_ledger.registry.ecfr import EcfrClient
from fedproc_ledger.registry.versions import fetch_part_versions

registry_app = typer.Typer(help="Phase 2: the eCFR clause registry with version history.", no_args_is_help=True)
CACHE = DATA / "raw" / "ecfr" / "cache"
HISTORY_START = date(
    2016, 1, 1
)  # eCFR point-in-time history starts 2017-01-01; the first window starts earlier on purpose


def _latest(client: EcfrClient) -> str:
    return str(next(t for t in client.titles()["titles"] if t["number"] == 48)["up_to_date_as_of"])


@registry_app.command()
def plan(parts: str = typer.Option("", help="Comma-separated part numbers (default: every x52 part).")) -> None:
    """How many requests the build needs: version records and distinct change dates per part (cheap, cached)."""
    client = EcfrClient(CACHE)
    latest = _latest(client)
    chosen = [p for p in x52_parts(client.structure(latest)) if not parts or p["part"] in parts.split(",")]
    total = 0
    for p in chosen:
        recs = fetch_part_versions(client, p["part"], HISTORY_START, date.fromisoformat(latest))
        n = len({r["date"] for r in recs})
        total += n + 1
        typer.echo(f"part {p['part']:>5} {p['regulation']:<7} records {len(recs):>5}  snapshot dates {n:>4}")
    typer.echo(
        f"{len(chosen)} parts, about {total} full-part requests (about 3 s each, cached afterwards); "
        f"latest eCFR date {latest}"
    )


@registry_app.command()
def build(parts: str = typer.Option("", help="Comma-separated part numbers (default: every x52 part).")) -> None:
    """Fetch snapshots and write data/processed/registry.parquet and results/registry_stats.json."""
    client = EcfrClient(CACHE)
    latest = _latest(client)
    chosen = [p for p in x52_parts(client.structure(latest)) if not parts or p["part"] in parts.split(",")]
    rows: list[dict[str, Any]] = []
    stats: list[dict[str, Any]] = []
    warnings: list[str] = []
    for p in chosen:
        typer.echo(f"part {p['part']} ({p['regulation']})")
        r, s = build_part(
            client, p, latest, HISTORY_START, date.fromisoformat(latest), log=typer.echo, warnings=warnings
        )
        rows += r
        stats.append(s)
    df = to_frame(rows)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out = PROCESSED / "registry.parquet"
    df.to_parquet(out, index=False)
    summary = {
        "ecfr_as_of": latest,
        "earliest_version_date": min((v["effective_from"] for vs in df["versions"] for v in vs), default=None),
        "sections": int(len(df)),
        "by_status": df["status"].value_counts().to_dict(),
        "by_regulation": df["regulation"].value_counts().to_dict(),
        "kind_active": df[df["status"] == "active"]["kind"].value_counts().to_dict(),
        "parts": stats,
        "warnings": warnings,
        "requests": client.requests,
        "cache_hits": client.cache_hits,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "registry_stats.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    write_manifest(
        "registry.build",
        [],
        [out, RESULTS / "registry_stats.json"],
        {"parts": [p["part"] for p in chosen], "ecfr_as_of": latest},
        PROCESSED / "manifest_registry.json",
    )
    typer.echo(json.dumps({k: v for k, v in summary.items() if k != "parts"}, indent=1, default=str))
