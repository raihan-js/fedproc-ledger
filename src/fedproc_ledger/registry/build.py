"""The clause registry: every section of the x52 parts of eCFR Title 48 with kind, dates, alternates and versions."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from fedproc_ledger.registry.ecfr import EcfrClient
from fedproc_ledger.registry.parse import ParsedSection, parse_part_xml
from fedproc_ledger.registry.versions import fetch_part_versions, section_intervals

# Acronyms only where the plan or VETR's detection patterns name the regulation; anything else is CH<chapter> and
# carries the chapter's own title from eCFR, so no name is supplied from memory.
REG_CODE = {
    "1": "FAR", "2": "DFARS", "3": "HHSAR", "4": "AGAR", "5": "GSAM", "6": "DOSAR", "7": "AIDAR", "8": "VAAR",
    "9": "DEAR", "18": "NFS", "24": "HUDAR", "30": "HSAR", "54": "DLAD",
}  # fmt: skip


def x52_parts(structure: dict[str, Any]) -> list[dict[str, str]]:
    """Parts whose number ends in 52 (the provisions-and-clauses parts), with their chapter, from the structure tree."""
    out: list[dict[str, str]] = []

    def walk(n: dict[str, Any], chapter: tuple[str, str] | None) -> None:
        if n.get("type") == "chapter":
            chapter = (str(n["identifier"]), str(n.get("label", "")))
        if n.get("type") == "part" and str(n["identifier"]).endswith("52") and chapter:
            code = REG_CODE.get(chapter[0], f"CH{chapter[0]}")
            out.append(
                {"part": str(n["identifier"]), "chapter": chapter[0], "regulation": code, "regulation_name": chapter[1]}
            )
        for c in n.get("children") or []:
            walk(c, chapter)

    walk(structure, None)
    return out


def _row(
    part: dict[str, str], number: str, sec: ParsedSection, versions: list[dict[str, Any]], in_latest: bool
) -> dict[str, Any]:
    status = "removed" if not in_latest else ("reserved" if sec.reserved else "active")
    return {
        "number": number,
        "regulation": part["regulation"],
        "regulation_name": part["regulation_name"],
        "chapter": part["chapter"],
        "part": part["part"],
        "title": sec.title,
        "kind": sec.kind,
        "kind_source": sec.kind_source,
        "prescribed_in": sec.prescribed_in,
        "current_date": sec.clause_date if status == "active" else None,
        "alternates": sec.alternates,
        "versions": versions,
        "status": status,
        "removed": status != "active",
    }


def build_part(
    client: EcfrClient,
    part: dict[str, str],
    latest_date: str,
    start: date,
    end: date,
    log: Callable[[str], None] = print,
    warnings: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = fetch_part_versions(client, part["part"], start, end, warnings)
    intervals = section_intervals(records)
    dates = sorted({r["date"] for r in records})
    latest = parse_part_xml(client.full_xml(latest_date, part=part["part"]))
    last_seen: dict[str, ParsedSection] = {}
    for i, d in enumerate(dates):
        snap = parse_part_xml(client.full_xml(d, part=part["part"]))
        for ident, ivs in intervals.items():
            for iv in ivs:
                if iv["effective_from"] != d:
                    continue
                s = snap.get(ident)
                iv["clause_date"] = s.clause_date if s and not s.reserved else None
                iv["alternates"] = s.alternates if s else []
                iv["reserved"] = bool(s and s.reserved)
                iv["present"] = s is not None
                if s is not None:
                    last_seen[ident] = s
        if (i + 1) % 20 == 0:
            log(f"  part {part['part']}: {i + 1}/{len(dates)} snapshots")
    rows = []
    for number in sorted(set(intervals) | set(latest), key=_sort_key):
        sec = latest.get(number) or last_seen.get(number)
        if sec is None:
            continue
        rows.append(_row(part, number, sec, intervals.get(number, []), number in latest))
    stats = {
        "part": part["part"],
        "regulation": part["regulation"],
        "version_records": len(records),
        "snapshot_dates": len(dates),
        "sections_now": len(latest),
        "rows": len(rows),
    }
    return rows, stats


def _sort_key(number: str) -> tuple[tuple[int, int, str], ...]:
    """Natural order of section numbers: 52.219-9 before 52.219-14; numeric and text pieces never compared directly."""
    return tuple((0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.\-]", number))


def to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows)
