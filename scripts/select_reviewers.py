"""Reviewer-gold frame (docs/preregistration_reviewers.md): 200 documents for VETR
reviewers, disjoint from every training, development and round 2-7 document and
solicitation. Strata S (80) / M (50) / L (70); department cap 25; seed frozen
with a hash before any reviewer sees it."""

import hashlib
import json
import random
from pathlib import Path

import pandas as pd

from fedproc_ledger.paths import PROCESSED

SEED = 20261023
main = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
new = pd.read_parquet("data/interim/documents_new.parquet").set_index("doc_id")
docs = pd.concat([main, new])
used: set[str] = set(pd.read_parquet("data/interim/labeled_mentions.parquet")["doc"])
for f in (
    "ledger_gold_docs.txt",
    "ledger_test_docs.txt",
    "pilot_docs.txt",
    "dev23_docs.txt",
    "dev2345_docs.txt",
    "round2_docs.txt",
    "round3_docs.txt",
    "round4_docs.txt",
    "round5_docs.txt",
    "round6_docs.txt",
    "round7_docs.txt",
    "one_doc.txt",
):
    p = Path("data/interim") / f
    if p.exists():
        used.update(p.read_text().split())
wl = Path("data/interim/weak_labels.jsonl")
if wl.exists():
    used.update(json.loads(line)["doc"] for line in wl.read_text().splitlines() if line.strip())
used_sol = {str(docs.loc[d, "solicitation_number"]) for d in used if d in docs.index}
rows = []
for p in sorted((PROCESSED / "predictions").glob("*.parquet")):
    d = p.stem
    if d in used or d not in docs.index or str(docs.loc[d, "solicitation_number"]) in used_sol:
        continue
    pred = pd.read_parquet(p, columns=["number", "source"])
    n = pred["number"].nunique()
    if n < 8 or n > 150:
        continue
    box = int((pred["source"] == "box_rule").sum())
    rows.append(
        {
            "doc": d,
            "n": n,
            "box": box,
            "dep": str(docs.loc[d, "department"]),
            "posted": str(docs.loc[d, "posted_date"])[:10],
            "sol": str(docs.loc[d, "solicitation_number"]),
        }
    )
df = pd.DataFrame(rows).drop_duplicates("sol")
rng = random.Random(SEED)
strata = {
    "S": df[df.n <= 40],
    # M has almost no box-heavy documents corpus-wide (5 with box>=10); no box filter here.
    # The objective empty-box analysis runs on the L stratum, which is naturally checklist-heavy.
    "M": df[(df.n >= 41) & (df.n <= 80)],
    "L": df[(df.n >= 81) & (df.box >= 10)],
}
print({k: len(v) for k, v in strata.items()}, "eligible documents per stratum")
quota = {"S": 80, "M": 50, "L": 70}
picked: dict[str, list[str]] = {}
dep_count: dict[str, int] = {}
for k, v in strata.items():
    ids = list(v["doc"])
    rng.shuffle(ids)
    picked[k] = []
    for d in ids:
        if len(picked[k]) >= quota[k]:
            break
        dep = df.set_index("doc").loc[d, "dep"]
        if dep_count.get(dep, 0) >= 25:
            continue
        dep_count[dep] = dep_count.get(dep, 0) + 1
        picked[k].append(d)
chosen = sorted(d for v in picked.values() for d in v)
rfo = sum(df.set_index("doc").loc[d, "posted"] >= "2025-10-28" for d in chosen)
print(len(chosen), "documents;", rfo, "RFO-era;", {k: len(v) for k, v in picked.items()})
h = hashlib.sha256("\n".join(chosen).encode()).hexdigest()
Path("results/reviewer_docs_FROZEN.json").write_text(
    json.dumps({"seed": SEED, "strata": picked, "docs": chosen, "rfo_era": int(rfo), "sha256": h}, indent=1)
)
Path("data/interim/reviewer_docs.txt").write_text("\n".join(chosen) + "\n")
print("sha256", h[:16])
