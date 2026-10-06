"""`fl registry ...`: Phase 2 commands."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import typer

from fedproc_ledger.acquire.ratelimit import TokenBucket
from fedproc_ledger.manifest import write_manifest
from fedproc_ledger.paths import DATA, PROCESSED, RESULTS
from fedproc_ledger.registry.build import build_part, to_frame, x52_parts
from fedproc_ledger.registry.deviations import (
    GUIDE,
    PART52,
    agency_part52_pdfs,
    dhs_rows,
    model_dates,
    part52_sections,
    pdf_header,
)
from fedproc_ledger.registry.ecfr import UA, EcfrClient
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


X52 = "|".join(
    [
        "52",
        "252",
        "352",
        "452",
        "552",
        "652",
        "752",
        "852",
        "952",
        "1052",
        "1252",
        "1352",
        "1452",
        "1552",
        "1652",
        "1852",
        "1952",
        "2052",
        "2152",
        "2452",
        "2852",
        "2952",
        "3052",
        "3452",
        "5452",
    ]
)
STARTING_URLS = [
    "https://www.acq.osd.mil/dpap/dars/dfars_far_overhaul_class_deviations.html",
    "https://www.dhs.gov/publication/cpo-rfo-deviation-far-part-52",
    "https://www.acquisition.gov/far-overhaul",
]


def _fetch_text(http: httpx.Client, url: str, path: Path) -> tuple[str | None, str]:
    """Cached GET. Returns (text or None, status note); a refusal or timeout is recorded, never worked around."""
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace"), "cached"
    try:
        r = http.get(url)
    except httpx.HTTPError as e:
        return None, f"failed: {type(e).__name__}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.text, "fetched"


@registry_app.command()
def deviations() -> None:
    """RFO deviation facts for Part 52 (acquisition.gov guide): model dates, RFO section status, agency PDFs."""
    import fitz  # PyMuPDF

    raw = DATA / "raw" / "deviations"
    http = httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
    status: dict[str, str] = {}
    for u in STARTING_URLS:  # the plan's starting URLs: record what each one gives; do not work around a refusal
        if "acquisition.gov" in u:
            status[u] = "see the guide below"
            continue
        _, note = _fetch_text(http, u, raw / (u.split("//")[1].replace("/", "_") + ".html"))
        status[u] = note
    index, n1 = _fetch_text(http, GUIDE, raw / "acq_deviation_guide.html")
    part52, n2 = _fetch_text(http, PART52, raw / "acq_part52.html")
    status[GUIDE], status[PART52] = n1, n2
    if not index or not part52:
        typer.echo(f"cannot read the guide pages: {status}", err=True)
        raise typer.Exit(code=1)
    dates = model_dates(index)
    sections = pd.DataFrame(part52_sections(part52))
    sections["source_url"] = PART52
    rows: list[dict[str, Any]] = [
        {
            "kind": "model",
            "agency": "FAR Council (RFO model deviation, Part 52)",
            "deviation_number": None,
            "date": dates["issued"],
            "date_updated": dates["updated"],
            "clause_numbers_mentioned": sorted(sections["number"]),
            "url": PART52,
            "parsed": True,
            "header": "",
        }
    ]
    bucket = TokenBucket(1.0, capacity=1.0)
    pdfs = agency_part52_pdfs(index)
    dhs_path = raw / "www.dhs.gov_publication_cpo-rfo-deviation-far-part-52.html"
    if dhs_path.exists() and status.get(STARTING_URLS[1], "").startswith(("fetched", "cached")):
        for href in sorted(
            set(
                re.findall(
                    r'href="(https://www\.dhs\.gov/sites/default/files/[^"]+\.pdf)"',
                    dhs_path.read_text(errors="replace"),
                )
            )
        ):
            pdfs.append(
                {"agency": "Department of Homeland Security (DHS)", "filename": href.rsplit("/", 1)[-1], "url": href}
            )
    for pdf in pdfs:
        path = raw / "pdf" / pdf["filename"]
        if not path.exists():
            bucket.acquire()
            r = http.get(pdf["url"])
            if r.status_code != 200:
                rows.append(
                    {
                        "kind": "agency",
                        "agency": pdf["agency"],
                        "url": pdf["url"],
                        "parsed": False,
                        "header": f"HTTP {r.status_code}",
                    }
                )
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
        with fitz.open(path) as doc:
            first = doc[0].get_text() if len(doc) else ""
            second = doc[1].get_text() if len(doc) > 1 else ""
            alltext = "".join(pg.get_text() for pg in doc)
        h = pdf_header(first)
        nums = sorted(set(re.findall(rf"\b(?:{X52})\.\d{{3}}(?:-\d{{1,4}})?\b", alltext)))
        table = dhs_rows(first + second) if "dhs.gov" in pdf["url"] else []
        for t in table:  # DHS conformed documents: one row per class deviation listed in their opening table
            rows.append(
                {
                    "kind": "agency",
                    "agency": f"{pdf['agency']} ({t['regulation']} Part {t['part']})",
                    "deviation_number": f"{t['regulation']} Class Dev {t['deviation_number']}"
                    + (f", Revision {t['revision']}" if t["revision"] else ""),
                    "date": t["date"] or None,
                    "date_updated": t["effective"] or None,
                    "clause_numbers_mentioned": [],
                    "url": pdf["url"],
                    "parsed": bool(t["date"]),
                    "header": "from the document's opening table",
                }
            )
        if table:
            continue
        rows.append(
            {
                "kind": "agency",
                "agency": pdf["agency"],
                "deviation_number": h["deviation_number"],
                "date": h["date"],
                "date_updated": None,
                "clause_numbers_mentioned": nums,
                "url": pdf["url"],
                "parsed": h["parsed"],
                "header": h["header"],
            }
        )
    PROCESSED.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(PROCESSED / "deviations.parquet", index=False)
    sections.to_parquet(PROCESSED / "rfo_part52_sections.parquet", index=False)
    summary = {
        "model_deviation": dates,
        "rfo_sections": int(len(sections)),
        "rfo_status": sections["rfo_status"].value_counts().to_dict(),
        "agency_pdfs": sum(1 for r in rows if r["kind"] == "agency"),
        "agency_pdfs_parsed": sum(1 for r in rows if r["kind"] == "agency" and r["parsed"]),
        "agencies_with_a_part_52_pdf": sorted({r["agency"] for r in rows if r["kind"] == "agency"}),
        "source_status": status,
        "not_located": (
            "No Part 52 deviation file is listed on the guide for DoD, DHS, DOE, GSA, VA, NASA, USDA, DOI and others; "
            "the DoD (DPAP) and DHS pages named in the plan are not retrievable from this machine. Needs the owner."
        ),
    }
    (RESULTS / "deviations_stats.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    typer.echo(json.dumps(summary, indent=1, ensure_ascii=False))
