"""Round 7 (docs/preregistration_round7.md): labelled universe, sample (<= 20 numbers per M/L document, seed 20261022) and evidence sheets
with the original [doc.k] ids. Run after `fl model predict --docs data/interim/round7_docs.txt` with the frozen weights and rules v1.4."""

import collections
import hashlib
import json
import random
import subprocess
from pathlib import Path

import pandas as pd

from fedproc_ledger.label.commands import build_items
from fedproc_ledger.paths import PROCESSED

frozen = json.loads(Path("results/round7_docs_FROZEN.json").read_text())
stratum = {d: k for k, v in frozen["strata"].items() for d in v}
docs = Path("data/interim/round7_docs.txt").read_text().split()
rng = random.Random(20261022)
keys, sample, out = {}, {}, []
for di, d in enumerate(docs, 1):
    pred = pd.read_parquet(PROCESSED / "predictions" / f"{d}.parquet")
    undecided = sorted(set(pred.loc[pred["source"] == "model", "number"]))  # at least one mention no rule decided
    keys[d] = undecided
    pick = list(range(len(undecided)))
    if stratum[d] in ("M", "L") and len(undecided) > 20:
        pick = sorted(rng.sample(pick, 20))
    sample[d] = [undecided[i] for i in pick]
    by = collections.OrderedDict()
    for it in build_items(d):
        by.setdefault(it["number"], []).append(it)
    out.append(f"=== DOC {di} [{stratum[d]}] ({len(pick)} of {len(undecided)} numbers)")
    for i in pick:
        n = undecided[i]
        ms = by[n]
        out.append(f"[{di}.{i + 1}] {n} ({len(ms)}x)")
        for it in ms[:3]:
            ctx = it["context"].split("\n")
            idx = next((j for j, line in enumerate(ctx) if ">>>" in line), len(ctx) - 1)
            seg = " / ".join(x[:90] for x in ctx[max(0, idx - 1) : idx + 2])
            h = " > ".join(x[:30] for x in it["breadcrumb"][-2:])
            out.append(f" - [{h}] {seg}")
Path("data/audit/round7_sheet_keys.json").write_text(json.dumps(keys))
Path("data/audit/round7_sample_keys.json").write_text(json.dumps(sample))
Path("data/audit/round7_sample_sheets.txt").write_text("\n".join(out) + "\n")
sha = hashlib.sha256(Path("data/models/role_model.pkl").read_bytes()).hexdigest()
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
Path("results/round7_manifest.json").write_text(
    json.dumps(
        {
            "model_sha256": sha,
            "stacker_sha256": hashlib.sha256(Path("data/models/stacker_v3.pkl").read_bytes()).hexdigest(),
            "code_commit": head,
            "docs": len(docs),
            "labelled_universe": sum(len(v) for v in keys.values()),
            "sampled": sum(len(v) for v in sample.values()),
            "sample_keys_sha256": hashlib.sha256(json.dumps(sample, sort_keys=True).encode()).hexdigest(),
        },
        indent=1,
    )
)
print(
    sum(len(v) for v in sample.values()),
    "numbers sampled of",
    sum(len(v) for v in keys.values()),
    "; model",
    sha[:8],
    "; commit",
    head[:8],
)
