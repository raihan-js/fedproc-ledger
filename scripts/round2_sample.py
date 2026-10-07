"""Amendment A3: sample at most 24 numbers per M/L document (seed 20261011); S documents in full; write sampled compact sheets
that keep the original [doc.k] ids so earlier labels stay aligned."""

import collections
import json
import random
from pathlib import Path

from fedproc_ledger.label.commands import build_items

frozen = json.loads(Path("results/round2_docs_FROZEN.json").read_text())
stratum = {d: k for k, v in frozen["strata"].items() for d in v}
docs = Path("data/interim/round2_docs.txt").read_text().split()
keys = json.loads(Path("data/audit/round2_sheet_keys.json").read_text())
rng = random.Random(20261011)
sample = {}
out = []
for di, d in enumerate(docs, 1):
    nums = keys[d]
    pick = list(range(len(nums)))
    if stratum[d] in ("M", "L") and len(nums) > 24:
        pick = sorted(rng.sample(pick, 24))
    sample[d] = [nums[i] for i in pick]
    by = collections.OrderedDict()
    for it in build_items(d):
        by.setdefault(it["number"], []).append(it)
    out.append(f"=== DOC {di} [{stratum[d]}] ({len(pick)} of {len(nums)} numbers)")
    for i in pick:
        n = nums[i]
        ms = by[n]
        out.append(f"[{di}.{i + 1}] {n} ({len(ms)}x)")
        for it in ms[:3]:
            ctx = it["context"].split("\n")
            idx = next((j for j, line in enumerate(ctx) if ">>>" in line), len(ctx) - 1)
            seg = " / ".join(x[:90] for x in ctx[max(0, idx - 1) : idx + 2])
            h = " > ".join(x[:30] for x in it["breadcrumb"][-2:])
            out.append(f" - [{h}] {seg}")
Path("data/audit/round2_sample_keys.json").write_text(json.dumps(sample))
Path("data/audit/round2_sample_sheets.txt").write_text("\n".join(out) + "\n")
print(sum(len(v) for v in sample.values()), "numbers sampled of", sum(len(v) for v in keys.values()))
