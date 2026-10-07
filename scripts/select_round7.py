"""Frame for round 7 (docs/preregistration_round7.md): the temporal hold-out.

All documents come from the newer acquisition (posted 2026-09-30 to 2026-10-07,
after the last acquisition day 2026-09-29), disjoint from every training,
development and round 2-6 document and solicitation. Strata S / M / L,
10 / 4-6 / 10 documents. Frozen with a hash before labelling."""

import hashlib
import json
import random
from pathlib import Path

import pandas as pd

from fedproc_ledger.paths import PROCESSED

SEED = 20261021
new_docs = pd.read_parquet("data/interim/documents_new.parquet").set_index("doc_id")
old_docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
used_sol = set(old_docs["solicitation_number"].astype(str))
used_sol |= {
    s
    for f in ("data/interim/round2_docs.txt", "data/interim/round3_docs.txt", "data/interim/round4_docs.txt",
              "data/interim/round5_docs.txt", "data/interim/round6_docs.txt")
    if Path(f).exists()
    for s in []  # round docs are all in old_docs; kept for explicitness
}
rows = []
for p in sorted((PROCESSED / "predictions").glob("*.parquet")):
    d = p.stem
    if d not in new_docs.index:
        continue
    if str(new_docs.loc[d, "solicitation_number"]) in used_sol:
        continue
    pred = pd.read_parquet(p, columns=["number", "source"])
    n = pred["number"].nunique()
    if n < 8 or n > 150:
        continue
    box = int((pred["source"] == "box_rule").sum())
    rows.append({"doc": d, "n": n, "box": box, "dep": str(new_docs.loc[d, "department"]),
                 "posted": str(new_docs.loc[d, "posted_date"])[:10],
                 "sol": str(new_docs.loc[d, "solicitation_number"])})
df = pd.DataFrame(rows).drop_duplicates("sol")
rng = random.Random(SEED)
strata = {
    "S": df[(df.n <= 40)],
    "M": df[(df.n >= 41) & (df.n <= 80) & (df.box >= 10)],
    "L": df[(df.n >= 81) & (df.box >= 10)],
}
print({k: len(v) for k, v in strata.items()}, "eligible documents per stratum")
picked: dict[str, list[str]] = {}
dep_count: dict[str, int] = {}
for k, v in strata.items():
    ids = list(v["doc"])
    rng.shuffle(ids)
    picked[k] = []
    for d in ids:
        if len(picked[k]) >= 10:
            break
        dep = df.set_index("doc").loc[d, "dep"]
        if dep_count.get(dep, 0) >= 4:
            continue
        dep_count[dep] = dep_count.get(dep, 0) + 1
        picked[k].append(d)
chosen = sorted(d for v in picked.values() for d in v)
print(len(chosen), "documents;", {k: len(v) for k, v in picked.items()})
h = hashlib.sha256("\n".join(chosen).encode()).hexdigest()
Path("results/round7_docs_FROZEN.json").write_text(
    json.dumps({"seed": SEED, "strata": picked, "docs": chosen, "sha256": h}, indent=1)
)
Path("data/interim/round7_docs.txt").write_text("\n".join(chosen) + "\n")
print("sha256", h[:16])
