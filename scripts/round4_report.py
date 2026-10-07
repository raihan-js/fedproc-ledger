"""Round-2 verdicts H1 to H6 (round 4) (docs/preregistration_round4.md), computed mechanically from results/*.json and the frozen predictions."""

import collections
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from fedproc_ledger.candidates.patterns import extract_clause_numbers
from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED
from fedproc_ledger.rules import baseline as B
from fedproc_ledger.rules.commands import load_registry

PRED_DIR = Path(os.environ.get("PRED_DIR", str(PROCESSED / "predictions")))  # v2 predictions live elsewhere

R = Path("results")


def ev(tag: str) -> dict:
    return json.loads((R / f"ledger_eval_{tag}.json").read_text())


MAJ = "round4_majority_binding"
maj = ev(MAJ)
PRI = "model max q>=0.5"
P0 = f"paired {PRI} vs B0 (VETR)"
P1 = f"paired {PRI} vs B1 rules"
mod, b0 = maj[PRI], maj["B0 (VETR)"]
h: dict = {}
h["H1"] = {
    "diff": maj[P1]["diff"],
    "ci": [maj[P1]["lo"], maj[P1]["hi"]],
    "holds": bool(maj[P1]["diff"] >= 0.10 and maj[P1]["lo"] > 0),
}
h["H2"] = {
    "model_specificity": mod["specificity"],
    "model_recall": mod["recall"],
    "b0_specificity": b0["specificity"],
    "holds": bool(mod["specificity"] >= 0.70 and mod["recall"] >= 0.90 and b0["specificity"] < 0.20),
}
single = {t: ev(f"round4_{t}")[P0] for t in ["agent", "judge_gpt-4o-mini", "judge_gpt-4.1-mini"]}
pos = sum(v["diff"] > 0 for v in single.values())
h["H3"] = {
    "diff": maj[P0]["diff"],
    "ci": [maj[P0]["lo"], maj[P0]["hi"]],
    "non_inferior": bool(maj[P0]["lo"] > -0.03),
    "superior": bool(maj[P0]["lo"] > 0.01 and pos >= 2),
    "single_annotator_diffs": {k: [v["diff"], v["lo"], v["hi"]] for k, v in single.items()},
    "positive_on": pos,
}


def number_probs(gold_path: str, mode: str = "max") -> tuple[np.ndarray, np.ndarray]:
    gold = json.loads(Path(gold_path).read_text())["gold"]
    q, y = [], []
    for d, labels in gold.items():
        pred = pd.read_parquet(PRED_DIR / f"{d}.parquet")
        agg: dict[str, float] = {}
        for (n, _a), v in ledger_for(pred, mode).items():
            agg[n] = max(agg.get(n, 0.0), v)
        for n, lab in labels.items():
            lab = {"B": "B", "N": "N", "R": "N", "U": "U"}[lab]
            if lab != "U" and n in agg:
                q.append(agg[n])
                y.append(lab == "B")
    return np.asarray(q), np.asarray(y)


q2, y2 = number_probs("results/ledger_gold_round4_majority_binding.json")
err = (q2 >= 0.5) != y2
queue = (q2 > 0.1) & (q2 < 0.9)
h["H4"] = {
    "queue_share": float(queue.mean()),
    "errors": int(err.sum()),
    "errors_in_queue": int(err[queue].sum()),
    "share_of_errors_in_queue": float(err[queue].sum() / max(err.sum(), 1)),
    "accuracy_outside_queue": float(1 - err[~queue].mean()),
    "holds": bool(
        queue.mean() <= 0.45 and err[queue].sum() / max(err.sum(), 1) >= 0.60 and (1 - err[~queue].mean()) >= 0.93
    ),
}

# H5: objective over-count in strata M and L
fz = json.loads(Path("results/round4_docs_FROZEN.json").read_text())
registry = load_registry()
tot = only = 0
per_doc = []
for S in "ML":
    for d in fz["strata"][S]:
        pred = pd.read_parquet(PRED_DIR / f"{d}.parquet")
        plain = "\n".join(
            str(t) for t in pd.read_parquet(PROCESSED / "pages" / f"{d}.parquet", columns=["text_plain"])["text_plain"]
        )
        b0set = set(B.b0_ledger(extract_clause_numbers(plain), registry) if registry else extract_clause_numbers(plain))
        by = pred.groupby("number")
        n_un = 0
        for n in b0set:
            if n in by.groups:
                g = by.get_group(n)
                if (g["source"] == "box_rule").all() and (g["role"] == "CHECKLIST_NOT_SELECTED").all():
                    n_un += 1
        tot += len(b0set)
        only += n_un
        per_doc.append(n_un / max(len(b0set), 1))
h["H5"] = {
    "b0_entries": tot,
    "empty_box_entries": only,
    "share": only / tot,
    "median_doc_share": float(np.median(per_doc)),
    "holds": bool(only / tot >= 0.10),
}
h6 = json.loads((R / "round4_h6.json").read_text())
h["H6"] = {"items": h6["items"], "agreed": h6["agreed"], "holds": bool(h6["agreed"] >= 38)}

# annotator diagnostics (post-hoc, descriptive)
a = json.loads((R / "ledger_gold_round4_agent.json").read_text())["gold"]
diag = {}
for m in ["gpt-4o-mini", "gpt-4.1-mini"]:
    j = json.loads((R / f"ledger_gold_round4_judge_{m}.json").read_text())["gold"]
    cnt = collections.Counter((a[d][n], j[d].get(n, "U")) for d in a for n in a[d])
    n_agent_n = sum(v for (x, _), v in cnt.items() if x == "N")
    diag[m] = {
        "agent_N_judged_B": cnt[("N", "B")] / n_agent_n,
        "agent_B_judged_B": cnt[("B", "B")] / sum(v for (x, _), v in cnt.items() if x == "B"),
        "agent_N_total": n_agent_n,
    }
h["annotator_diagnostics"] = diag
Path("results/round4_report.json").write_text(json.dumps(h, indent=1, default=float))
print(json.dumps(h, indent=1, default=lambda x: round(float(x), 4)))
