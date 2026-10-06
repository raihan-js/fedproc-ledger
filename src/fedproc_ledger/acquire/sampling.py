"""Which days to search, how to name a department, and how to pick the candidate notices (seeded, deterministic)."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

import pandas as pd


def month_list(first: str, last: str) -> list[tuple[int, int]]:
    """['2024-01', '2024-03'] -> [(2024, 1), (2024, 2), (2024, 3)]."""
    y, m = (int(x) for x in first.split("-"))
    y2, m2 = (int(x) for x in last.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def weekdays(year: int, month: int) -> list[date]:
    d, out = date(year, month, 1), []
    while d.month == month:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def sample_days(year: int, month: int, k: int, seed: int) -> list[date]:
    """k random weekdays, one from each of k consecutive slices of the month's weekdays (so they are spread out)."""
    days = weekdays(year, month)
    rng = random.Random(f"{seed}-{year}-{month}")
    slices = [days[i * len(days) // k : (i + 1) * len(days) // k] for i in range(k)]
    return sorted(rng.choice(s) for s in slices if s)


_DOD_COMPONENTS = {
    "DEPT OF THE ARMY": "DOD_ARMY",
    "DEPT OF THE NAVY": "DOD_NAVY",
    "DEPT OF THE AIR FORCE": "DOD_AIR_FORCE",
    "DEFENSE LOGISTICS AGENCY (DLA)": "DOD_DLA",
    "DEFENSE LOGISTICS AGENCY": "DOD_DLA",
}
_TOP = {
    "DEPT OF DEFENSE": "DOD_OTHER",
    "VETERANS AFFAIRS, DEPARTMENT OF": "VA",
    "GENERAL SERVICES ADMINISTRATION": "GSA",
    "HOMELAND SECURITY, DEPARTMENT OF": "DHS",
    "HEALTH AND HUMAN SERVICES, DEPARTMENT OF": "HHS",
    "ENERGY, DEPARTMENT OF": "DOE",
    "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION": "NASA",
    "AGRICULTURE, DEPARTMENT OF": "USDA",
    "INTERIOR, DEPARTMENT OF THE": "DOI",
    "JUSTICE, DEPARTMENT OF": "DOJ",
    "TRANSPORTATION, DEPARTMENT OF": "DOT",
}


def department_of(agency: str | None) -> str:
    """Top-level department from SAM's dotted agency path; DoD split into its components; anything else is OTHER."""
    if not isinstance(agency, str) or not agency.strip():  # missing values arrive as None or NaN
        return "OTHER"
    parts = [p.strip().upper() for p in agency.split(".")]
    top = parts[0]
    if top in ("DEPT OF DEFENSE", "DEPARTMENT OF DEFENSE") and len(parts) > 1:
        return _DOD_COMPONENTS.get(parts[1], "DOD_OTHER")
    return _TOP.get(top, "OTHER")


def select_candidates(notices: pd.DataFrame, target: int, max_share: float, seed: int) -> pd.DataFrame:
    """Rank notices for download: balanced across months, no department above `max_share` of the target.

    `notices` needs the columns solicitation_number, month (YYYY-MM) and department. Returns every row with a `rank`
    (0 = first to download); `selected` marks the first `target` ranks that respect the cap, and the rest is the
    reserve list for later top-up rounds. If the cap cannot be met, fewer rows are selected. Deterministic per seed.
    """
    rng = random.Random(seed)
    df = notices.copy()
    df["_r"] = [rng.random() for _ in range(len(df))]
    cap = int(max_share * target)
    months = sorted(df["month"].unique())
    per_month = max(1, target // max(1, len(months)))
    chosen: list[Any] = []
    taken: dict[str, int] = {}
    groups = {m: df[df["month"] == m].sort_values("_r") for m in months}
    # round-robin over months: one notice at a time, skipping a department that has reached its cap
    cursors = dict.fromkeys(months, 0)
    quota = dict.fromkeys(months, per_month)
    progress = True
    while len(chosen) < target and progress:
        progress = False
        for m in months:
            if quota[m] <= 0 or len(chosen) >= target:
                continue
            g = groups[m]
            while cursors[m] < len(g):
                row = g.iloc[cursors[m]]
                cursors[m] += 1
                dep = row["department"]
                if taken.get(dep, 0) >= cap:
                    continue
                chosen.append(g.index[cursors[m] - 1])
                taken[dep] = taken.get(dep, 0) + 1
                quota[m] -= 1
                progress = True
                break
    # if some months ran short, top up from whatever is left (still respecting the department cap)
    rest = df.drop(index=chosen).sort_values("_r")
    for idx, row in rest.iterrows():
        if len(chosen) >= target:
            break
        dep = row["department"]
        if taken.get(dep, 0) < cap:
            chosen.append(idx)
            taken[dep] = taken.get(dep, 0) + 1
    leftover = df.drop(index=chosen).sort_values("_r").index.tolist()
    order = chosen + list(leftover)
    out = df.loc[order].copy()
    out["rank"] = range(len(out))
    out["selected"] = out["rank"] < len(chosen)
    return out.drop(columns="_r")
