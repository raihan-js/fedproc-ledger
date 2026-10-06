"""Corpus-level view: how many clause numbers does each method put in the ledger, and which numbers does the status quo
over-count. Model ledger = noisy-OR q >= 0.5 (the pre-registered default). Predictions are not gold: this is a description
of method differences, not an accuracy claim."""

import collections
import json

import pandas as pd

from fedproc_ledger.candidates.patterns import extract_clause_numbers
from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED, RESULTS
from fedproc_ledger.rules import baseline as B
from fedproc_ledger.rules.commands import load_registry

registry = load_registry()
docs = pd.read_parquet("data/interim/documents.parquet").drop_duplicates("doc_id").set_index("doc_id")
rows = []
dropped = collections.Counter()
kept = collections.Counter()
for p in sorted((PROCESSED / "predictions").glob("*.parquet")):
    d = p.stem
    pred = pd.read_parquet(p)
    rules = pd.read_parquet(PROCESSED / "rules" / f"{d}.parquet")
    plain = "\n".join(
        str(t) for t in pd.read_parquet(PROCESSED / "pages" / f"{d}.parquet", columns=["text_plain"])["text_plain"]
    )
    b0 = set(B.b0_ledger(extract_clause_numbers(plain), registry) if registry else extract_clause_numbers(plain))
    excl = {str(r.number) for r in rules.itertuples() if r.role == B.EXCLUDED}
    b1 = {str(r.number) for r in rules.itertuples() if r.role in B.BINDING and not bool(r.from_range)} - excl
    q: dict[str, float] = {}
    for (n, _a), v in ledger_for(pred).items():
        q[n] = max(q.get(n, 0.0), v)
    model = {n for n, v in q.items() if v >= 0.5}
    uncertain = {n for n, v in q.items() if 0.3 <= v < 0.7}
    for n in b0 & set(q):
        (dropped if n not in model else kept)[n] += 1
    dep = str(docs.loc[d, "department"]) if d in docs.index else "unknown"
    posted = str(docs.loc[d, "posted_date"]) if d in docs.index else ""
    rows.append(
        {
            "doc": d,
            "department": dep,
            "rfo_era": posted >= "2025-10-28",
            "b0": len(b0),
            "b1": len(b1),
            "model": len(model),
            "uncertain": len(uncertain),
            "b0_dropped": len(b0 & set(q) - model),
            "b0_only_not_candidate": len(b0 - set(q)),
        }
    )
df = pd.DataFrame(rows)
df = df[df.b0 > 0]
tot = df[["b0", "b1", "model", "uncertain", "b0_dropped"]].sum()
out = {
    "documents": len(df),
    "ledger_entries": {k: int(v) for k, v in tot.items()},
    "model_vs_b0_ratio": float(tot["model"] / tot["b0"]),
    "docs_where_b0_overcounts_by_20pct": float(((df.b0 - df.model) / df.b0 >= 0.2).mean()),
    "median_b0_minus_model_per_doc": float((df.b0 - df.model).median()),
    "by_rfo_era": df.groupby("rfo_era")[["b0", "model"]].sum().to_dict("index"),
    "most_dropped_by_model": [(n, dropped[n], dropped[n] + kept[n]) for n, _ in dropped.most_common(15)],
}
print(json.dumps(out, indent=1, default=float))
(RESULTS / "corpus_stats.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
df.to_parquet("data/processed/corpus_ledger_sizes.parquet", index=False)

# Objective part (no model, no LLM): numbers the status quo counts although every mention of them is a checklist item whose box is empty.
only_unchecked = 0
checked_anywhere = 0
docs_with_checklist = 0
docs_affected = 0
b0_total = 0
per_doc_unchecked = []
for p in sorted((PROCESSED / "predictions").glob("*.parquet")):
    d = p.stem
    pred = pd.read_parquet(p)
    plain = "\n".join(
        str(t) for t in pd.read_parquet(PROCESSED / "pages" / f"{d}.parquet", columns=["text_plain"])["text_plain"]
    )
    b0 = set(B.b0_ledger(extract_clause_numbers(plain), registry) if registry else extract_clause_numbers(plain))
    if not b0:
        continue
    b0_total += len(b0)
    box = pred[pred["source"] == "box_rule"]
    if len(box):
        docs_with_checklist += 1
    by_num = pred.groupby("number")
    n_un = 0
    for n in b0:
        if n not in by_num.groups:
            continue
        g = by_num.get_group(n)
        if (g["source"] == "box_rule").all() and (g["role"] == "CHECKLIST_NOT_SELECTED").all():
            n_un += 1
    only_unchecked += n_un
    per_doc_unchecked.append(n_un)
    docs_affected += n_un > 0
obj = {
    "b0_entries": b0_total,
    "b0_entries_only_in_empty_checklist_boxes": only_unchecked,
    "share_of_b0": only_unchecked / b0_total,
    "documents_with_a_decided_checklist": docs_with_checklist,
    "documents_where_b0_counts_unchecked_items": docs_affected,
    "median_unchecked_per_affected_document": float(pd.Series([x for x in per_doc_unchecked if x > 0]).median()),
}
print(json.dumps(obj, indent=1))
(RESULTS / "corpus_objective_overcount.json").write_text(json.dumps(obj, indent=1) + "\n")
