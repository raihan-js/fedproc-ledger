"""Fetched search days -> notice pool: flatten, dedupe on solicitation_number, map departments, select."""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from fedproc_ledger.acquire.sampling import department_of, select_candidates

PERSONAL_PREFIXES = ("contact_", "secondary_contact")


def load_search_days(search_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for f in sorted(search_dir.glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            day = json.load(fh)
        for r in day["data"]:
            rows.append({**r, "search_day": day["day"]})
    df = pd.DataFrame(rows)
    leaked = [c for c in df.columns if c.startswith(PERSONAL_PREFIXES)]
    if leaked:  # the fields list excludes them; this is a tripwire, not a filter
        raise ValueError(f"personal contact fields in the search data: {leaked}")
    return df


def build_pool(
    df: pd.DataFrame,
    target: int,
    max_share: float,
    seed: int,
    month_from: str | None = None,
    month_to: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Returns (ranked unique solicitations, stats). One row per solicitation_number; amendments that share it are
    recorded in `lineage_notice_ids` (the notices of the same solicitation seen in the sample), not as extra rows."""
    df = df.copy()
    sol = df["solicitation_number"].fillna("").astype(str).str.strip()
    df["solicitation_number"] = sol.where(sol != "", df["notice_id"])  # a missing number falls back to the notice id
    df = df.sort_values(["solicitation_number", "posted_date", "notice_id"])
    lineage = df.groupby("solicitation_number")["notice_id"].apply(list)
    latest = df.drop_duplicates("solicitation_number", keep="last").copy()
    latest["lineage_notice_ids"] = latest["solicitation_number"].map(lineage)
    latest["month"] = latest["posted_date"].str[:7]
    if month_from:
        latest = latest[latest["month"] >= month_from]
    if month_to:
        latest = latest[latest["month"] <= month_to]
    latest["department"] = latest["agency"].map(department_of)
    latest["n_links"] = latest["resource_links_array"].map(lambda x: len(x) if isinstance(x, list) else 0)
    latest = latest[latest["n_links"] > 0].reset_index(drop=True)
    ranked = select_candidates(latest, target=target, max_share=max_share, seed=seed)
    sel = ranked[ranked["selected"]]
    stats = {
        "search_days": int(df["search_day"].nunique()),
        "notices_fetched": int(len(df)),
        "unique_solicitations": int(len(latest)),
        "selected": int(len(sel)),
        "target": target,
        "selected_by_department": dict(Counter(sel["department"])),
        "selected_by_month": dict(sorted(Counter(sel["month"]).items())),
        "selected_by_notice_type": dict(Counter(sel["notice_type"])),
        "available_by_department": dict(Counter(latest["department"])),
        "available_by_month": dict(sorted(Counter(latest["month"]).items())),
        "links_per_selected_notice": {
            "median": float(sel["n_links"].median()),
            "max": int(sel["n_links"].max()),
            "total": int(sel["n_links"].sum()),
        },
        "max_department_share": float(sel["department"].value_counts(normalize=True).max()) if len(sel) else None,
    }
    return ranked, stats
