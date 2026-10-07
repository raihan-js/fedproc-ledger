"""Frame for round 6 (docs/preregistration_round6.md): strata S / M / L, 12 documents each, frozen with a hash before labelling."""

import hashlib
import json
import random
from pathlib import Path

import pandas as pd

from fedproc_ledger.paths import PROCESSED

SEED = 20261019
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
used = set(pd.read_parquet("data/interim/labeled_mentions.parquet")["doc"])
used |= set(Path("data/interim/ledger_gold_docs.txt").read_text().split()) | set(
    Path("data/interim/ledger_test_docs.txt").read_text().split()
)
used |= (
    set(Path("data/interim/round2_docs.txt").read_text().split())
    | set(Path("data/interim/round3_docs.txt").read_text().split())
    | set(Path("data/interim/round4_docs.txt").read_text().split())
    | set(Path("data/interim/round5_docs.txt").read_text().split())
)
used |= {
    json.loads(line)["doc"] for line in Path("data/interim/weak_labels.jsonl").read_text().splitlines() if line.strip()
}
used_sol = {docs.loc[d, "solicitation_number"] for d in used if d in docs.index}
rows = []
for p in sorted((PROCESSED / "predictions").glob("*.parquet")):
    d = p.stem
    if d in used or d not in docs.index or docs.loc[d, "solicitation_number"] in used_sol:
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
            "sol": docs.loc[d, "solicitation_number"],
        }
    )
df = pd.DataFrame(rows).drop_duplicates("sol")
rng = random.Random(SEED)
strata = {
    "S": df[(df.n <= 40)],
    "M": df[(df.n >= 41) & (df.n <= 80) & (df.box >= 10)],
    "L": df[(df.n >= 81) & (df.box >= 10)],
}
print({k: len(v) for k, v in strata.items()}, "eligible documents per stratum")
chosen, dep_count, picked = [], {}, {}
post = df.set_index("doc")["posted"]
for k, v in strata.items():
    ids = list(v["doc"])
    rng.shuffle(ids)
    picked[k] = []
    # the pre-registration requires at least 12 RFO-era documents overall: take 4 per stratum first, then fill
    for rfo_pass in (True, False):
        for d in ids:
            if d in picked[k] or len(picked[k]) == 10 or (rfo_pass and (post[d] < "2025-10-28" or len(picked[k]) >= 4)):
                continue
            dep = df.set_index("doc").loc[d, "dep"]
            if dep_count.get(dep, 0) >= 4:
                continue
            dep_count[dep] = dep_count.get(dep, 0) + 1
            picked[k].append(d)
chosen = sorted(d for v in picked.values() for d in v)
rfo = sum(df.set_index("doc").loc[d, "posted"] >= "2025-10-28" for d in chosen)
print(len(chosen), "documents;", rfo, "posted on or after 2025-10-28;", {k: len(v) for k, v in picked.items()})
h = hashlib.sha256("\n".join(chosen).encode()).hexdigest()
Path("results/round6_docs_FROZEN.json").write_text(
    json.dumps({"seed": SEED, "strata": picked, "docs": chosen, "rfo_era": int(rfo), "sha256": h}, indent=1)
)
Path("data/interim/round6_docs.txt").write_text("\n".join(chosen) + "\n")
print("sha256", h[:16])
