"""Version history of a part from the versioner API, and the per-section effective intervals built from it."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fedproc_ledger.registry.ecfr import EcfrClient

CAP = 1000  # the versions endpoint returns at most this many records per request (probed 2026-10-06)


def fetch_part_versions(
    client: EcfrClient, part: str, start: date, end: date, warnings: list[str] | None = None
) -> list[dict[str, Any]]:
    """All version records of one part issued in [start, end]: the window is halved until no response hits the cap."""

    def window(a: date, b: date) -> list[dict[str, Any]]:
        got = client.versions(part=str(part), **{"issue_date[gte]": a.isoformat(), "issue_date[lte]": b.isoformat()})
        if len(got) < CAP:
            return got
        if a >= b:
            if warnings is not None:
                warnings.append(f"part {part}: {len(got)} records on {a} (cap {CAP}); some may be missing")
            return got
        mid = a + (b - a) // 2
        return window(a, mid) + window(mid + timedelta(days=1), b)

    seen: set[tuple[Any, ...]] = set()
    out = []
    for r in window(start, end):
        key = (r["identifier"], r["date"], r.get("amendment_date"), r.get("issue_date"), r.get("removed"))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def section_intervals(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """identifier -> [{effective_from, effective_to, removed}], one entry per distinct effective date, in date order.

    `effective_to` is the day before the next version starts, None for the latest. A version with `removed` true ends
    the section's life at its date (its interval is recorded, flagged removed).
    """
    by: dict[str, dict[str, bool]] = {}
    for r in records:
        by.setdefault(r["identifier"], {})
        by[r["identifier"]][r["date"]] = by[r["identifier"]].get(r["date"], False) or bool(r.get("removed"))
    out: dict[str, list[dict[str, Any]]] = {}
    for ident, dates in by.items():
        ordered = sorted(dates)
        rows = []
        for i, d in enumerate(ordered):
            nxt = ordered[i + 1] if i + 1 < len(ordered) else None
            to = (date.fromisoformat(nxt) - timedelta(days=1)).isoformat() if nxt else None
            rows.append({"effective_from": d, "effective_to": to, "removed": dates[d]})
        out[ident] = rows
    return out
