"""Version currency of the model ledger: does the date a solicitation cites for a clause match the version of that clause in
force (eCFR history, registry) on the day the notice was posted? Objective given the cited date and the registry; the ledger
membership (q >= 0.5) comes from the model. Pre-RFO notices (posted before 2025-10-28) are the clean case: eCFR is then the
authority. After that date agencies adopt the RFO deviation at different times, so those are reported separately."""

import collections
import json

import pandas as pd

from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED, RESULTS

RFO = "2025-10-28"
reg = pd.read_parquet(PROCESSED / "registry.parquet").set_index("number")
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")


def version_in_force(number: str, day: str) -> str | None:
    if number not in reg.index:
        return None
    for v in reg.loc[number, "versions"]:
        lo, hi = v["effective_from"], v["effective_to"]
        if lo <= day and (hi is None or day <= hi) and v["present"] and not v["reserved"]:
            return v["clause_date"]
    return None


rows = []
for p in sorted((PROCESSED / "predictions").glob("*.parquet")):
    d = p.stem
    if d not in docs.index:
        continue
    day = str(docs.loc[d, "posted_date"])[:10]
    if len(day) < 10:
        continue
    pred = pd.read_parquet(p)
    rules = pd.read_parquet(PROCESSED / "rules" / f"{d}.parquet", columns=["cand_id", "cited_date", "number"])
    q: dict[str, float] = {}
    for (n, _a), v in ledger_for(pred).items():
        q[n] = max(q.get(n, 0.0), v)
    dates = rules.dropna(subset=["cited_date"]).groupby("number")["cited_date"].agg(lambda s: s.value_counts().index[0])
    for n, v in q.items():
        if v < 0.5:
            continue
        cited = dates.get(n)
        force = version_in_force(n, day)
        if n not in reg.index:
            cat = "not_in_registry"
        elif cited is None:
            cat = "no_date_cited"
        elif force is None:
            cat = "no_version_data"
        elif cited == force:
            cat = "matches_in_force"
        elif cited < force:
            cat = "older_than_in_force"
        else:
            cat = "newer_than_in_force"
        rows.append(
            {
                "doc": d,
                "number": n,
                "posted": day,
                "era": "rfo" if day >= RFO else "pre_rfo",
                "cited": cited,
                "in_force": force,
                "cat": cat,
                "rfo_status": reg.loc[n, "rfo_status"] if n in reg.index else None,
            }
        )
df = pd.DataFrame(rows)
out = {"entries": len(df)}
for era, g in df.groupby("era"):
    c = g["cat"].value_counts().to_dict()
    dated = g[g.cat.isin(["matches_in_force", "older_than_in_force", "newer_than_in_force"])]
    out[era] = {
        "entries": len(g),
        "by_category": c,
        "dated_entries": len(dated),
        "older_share_of_dated": float((dated.cat == "older_than_in_force").mean()) if len(dated) else None,
        "docs": int(g["doc"].nunique()),
    }
pre = df[(df.era == "pre_rfo") & (df.cat == "older_than_in_force")]
out["pre_rfo_most_often_stale"] = collections.Counter(pre["number"]).most_common(10)
out["rfo_era_entries_citing_clauses_the_rfo_reserves"] = int(((df.era == "rfo") & (df.rfo_status == "reserved")).sum())
print(json.dumps(out, indent=1, default=float))
(RESULTS / "version_currency.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
df.to_parquet("data/processed/version_currency_entries.parquet", index=False)
