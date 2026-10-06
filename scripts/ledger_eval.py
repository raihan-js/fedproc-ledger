"""Document-level ledger evaluation on the agent-adjudicated gold (results/ledger_gold_agent_v0.json).

Unit: (document, clause number) among numbers labelled B (binds) or N (does not); U is excluded. Systems are restricted to
that universe, so a system is never charged for numbers nobody labelled. Metrics: precision, recall and F1 of the binding
class, specificity (share of N numbers correctly left out), accuracy; cluster bootstrap over documents.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fedproc_ledger.candidates.patterns import extract_clause_numbers
from fedproc_ledger.eval import metrics as M
from fedproc_ledger.eval.leaderboard import log_run
from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED, RESULTS
from fedproc_ledger.rules import baseline as B
from fedproc_ledger.rules.commands import load_registry

GOLD = sys.argv[1] if len(sys.argv) > 1 else "results/ledger_gold_agent_v0.json"
MODE = (
    sys.argv[2] if len(sys.argv) > 2 else "binding"
)  # binding: B positive, N and R negative; applicable: B and R positive
TAG = Path(GOLD).stem.replace("ledger_gold_", "") + ("" if MODE == "binding" else "_" + MODE)
gold = json.loads(Path(GOLD).read_text())["gold"]
_MAP = {"binding": {"B": "B", "N": "N", "R": "N", "U": "U"}, "applicable": {"B": "B", "R": "B", "N": "N", "U": "U"}}[
    MODE
]
gold = {d: {n: _MAP[v] for n, v in labels.items()} for d, labels in gold.items()}
registry = load_registry()
systems: dict[str, dict[str, set[str]]] = {
    k: {} for k in ["all-candidates", "B0 (VETR)", "B0 minus empty-box clauses", "B1 rules"]
}
probs: dict[str, dict[str, dict[str, float]]] = {"noisy_or": {}, "max": {}}
for d in gold:
    rules = pd.read_parquet(PROCESSED / "rules" / f"{d}.parquet")
    pred = pd.read_parquet(PROCESSED / "predictions" / f"{d}.parquet")
    systems["all-candidates"][d] = set(pred["number"])
    b1 = {str(r.number) for r in rules.itertuples() if r.role in B.BINDING and not bool(r.from_range)}
    excl = {str(r.number) for r in rules.itertuples() if r.role == B.EXCLUDED}
    systems["B1 rules"][d] = b1 - excl
    plain = "\n".join(
        str(t) for t in pd.read_parquet(PROCESSED / "pages" / f"{d}.parquet", columns=["text_plain"])["text_plain"]
    )
    systems["B0 (VETR)"][d] = set(
        B.b0_ledger(extract_clause_numbers(plain), registry) if registry else extract_clause_numbers(plain)
    )
    unchecked = {
        n
        for n, g in pred.groupby("number")
        if (g["source"] == "box_rule").all() and (g["role"] == "CHECKLIST_NOT_SELECTED").all()
    }
    systems["B0 minus empty-box clauses"][d] = systems["B0 (VETR)"][d] - unchecked
    for mode in probs:
        q = ledger_for(pred, mode)
        agg: dict[str, float] = {}
        for (n, _a), v in q.items():
            agg[n] = max(agg.get(n, 0.0), v)
        probs[mode][d] = agg


def counts(pred_by_doc: dict[str, set[str]]) -> np.ndarray:
    rows = []
    for d, labels in gold.items():
        lab = {n: v for n, v in labels.items() if v in ("B", "N")}
        p = {n for n in lab if n in pred_by_doc.get(d, set())}
        g = {n for n, v in lab.items() if v == "B"}
        tn = sum(1 for n, v in lab.items() if v == "N" and n not in p)
        rows.append((len(p & g), len(p - g), len(g - p), tn, sum(1 for v in lab.values() if v == "N")))
    return np.asarray(rows, dtype=float)


def summarize(name: str, c: np.ndarray) -> dict[str, float]:
    tp, fp, fn, tn, nneg = c.sum(axis=0)
    r = M.prf(tp, fp, fn)
    ci = M.cluster_bootstrap(c[:, :3], n_boot=4000)
    f2 = M.prf(tp, fp, fn, beta=2.0)["f"]
    out = {
        **r,
        "f2": f2,
        "specificity": float(tn / nneg),
        "accuracy": float((tp + tn) / (tp + fp + fn + tn)),
        "f1_lo": ci["lo"],
        "f1_hi": ci["hi"],
    }
    print(
        f"{name:28s} P {r['precision']:.3f} R {r['recall']:.3f} F1 {r['f']:.3f} [{ci['lo']:.3f},{ci['hi']:.3f}] F2 {f2:.3f}  specificity {out['specificity']:.3f}  acc {out['accuracy']:.3f}"
    )
    return out


n_lab = int(sum(1 for g in gold.values() for v in g.values() if v in ("B", "N")))
print(
    f"{len(gold)} documents, {n_lab} labelled numbers ({sum(1 for g in gold.values() for v in g.values() if v == 'B')} binding)"
)
res = {}
all_counts = {}
for name, s in systems.items():
    all_counts[name] = counts(s)
    res[name] = summarize(name, all_counts[name])
for mode in ("noisy_or", "max"):
    for t in (0.5, 0.7, 0.9):
        s = {d: {n for n, v in q.items() if v >= t} for d, q in probs[mode].items()}
        name = f"model {mode} q>={t}"
        all_counts[name] = counts(s)
        res[name] = summarize(name, all_counts[name])
best = max((k for k in all_counts if k.startswith("model")), key=lambda k: res[k]["f"])
print("best model config by F1:", best)
for base in ("B1 rules", "B0 (VETR)", "all-candidates"):
    d = M.paired_bootstrap(all_counts[base][:, :3], all_counts[best][:, :3], n_boot=4000)
    print(f"  {best} - {base}: dF1 {d['diff']:+.3f} [{d['lo']:+.3f},{d['hi']:+.3f}]")
    res[f"paired {best} vs {base}"] = d
RESULTS.mkdir(exist_ok=True)
(RESULTS / f"ledger_eval_{TAG}.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
log_run(
    RESULTS / "leaderboard.jsonl",
    "ledger " + best,
    {"gold": "agent_v0", "docs": len(gold)},
    {k: v for k, v in res[best].items()},
    split="ledger-gold-v0",
)
