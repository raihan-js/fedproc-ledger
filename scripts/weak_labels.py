"""Weak role labels for model v2: two OpenAI voters (variant D) label a stratified sample of mentions that no rule decides, in pool
documents that are not in development, round 1 or round 2 (and share no solicitation with them). Labels where both voters agree
(and neither says UNCLEAR) are kept. Resumable through the panel cache; spend is capped in label/openai_chat.py."""

import json
import random
import sys
from pathlib import Path

import pandas as pd

from fedproc_ledger.label import panel as P
from fedproc_ledger.label.commands import build_items, chat_for, inherited_ids, para_a_ids, slice_a_ids
from fedproc_ledger.paths import PROCESSED

N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 400
PER_DOC = int(sys.argv[2]) if len(sys.argv) > 2 else 15
OUT = Path("data/interim/weak_labels.jsonl")
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
used = set(pd.read_parquet("data/interim/labeled_mentions.parquet")["doc"])
for f in ("ledger_gold_docs.txt", "ledger_test_docs.txt", "round2_docs.txt"):
    used |= set(Path("data/interim", f).read_text().split())
used_sol = {docs.loc[d, "solicitation_number"] for d in used if d in docs.index}
pool = [
    p.stem
    for p in sorted((PROCESSED / "predictions").glob("*.parquet"))
    if p.stem in docs.index and p.stem not in used and docs.loc[p.stem, "solicitation_number"] not in used_sol
]
seen, uniq = set(), []
for d in pool:
    s = docs.loc[d, "solicitation_number"]
    if s not in seen:
        seen.add(s)
        uniq.append(d)
rng = random.Random(20261012)
rng.shuffle(uniq)
chosen = uniq[:N_DOCS]
voters = [P.Voter("g41", "gpt-4.1-mini", "D"), P.Voter("g4o", "gpt-4o-mini", "D")]
chat, cache = chat_for("openai", ""), P.Cache(Path("data/interim/panel_cache.jsonl"))
done = set()
if OUT.exists():
    done = {json.loads(line)["doc"] for line in OUT.read_text().splitlines() if line.strip()}
print(len(pool), "pool docs;", len(uniq), "distinct solicitations;", len(chosen), "chosen;", len(done), "done")
for d in chosen:
    if d in done:
        continue
    skip = set(slice_a_ids(d)) | para_a_ids(d) | set(inherited_ids(d))
    items = [i for i in build_items(d) if i["id"] not in skip]
    rng.shuffle(items)
    # at most one mention per (number) per document first, so the sample spreads over clauses
    seen_n, pick = set(), []
    for it in items:
        if it["number"] not in seen_n:
            seen_n.add(it["number"])
            pick.append(it)
    pick = pick[:PER_DOC]
    if not pick:
        continue
    votes = [P.vote(pick, v, chat, cache) for v in voters]
    rows = [
        {
            "doc": d,
            "id": it["id"],
            "number": it["number"],
            "g41": votes[0].get(it["id"]),
            "g4o": votes[1].get(it["id"]),
            "b1": it["b1"],
        }
        for it in pick
    ]
    with OUT.open("a") as f:
        f.write(json.dumps({"doc": d, "rows": rows}) + "\n")
print("finished")
