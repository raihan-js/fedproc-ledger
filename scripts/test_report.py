"""Pre-registered verdicts H1 to H4 (docs/preregistration.md) on the frozen test set, computed mechanically.
Primary gold: results/ledger_gold_test_majority_binding.json. The abstention threshold comes from the development set only."""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.model.commands import ledger_for
from fedproc_ledger.paths import PROCESSED

TAG = (
    sys.argv[1] if len(sys.argv) > 1 else "test"
)  # test = original judge run (D-028); test_v2 = corrected judges (D-031)
r = json.loads(Path(f"results/ledger_eval_{TAG}_majority_binding.json").read_text())
b0, b1, mod = r["B0 (VETR)"], r["B1 rules"], r["model noisy_or q>=0.5"]
p_b1 = r["paired model noisy_or q>=0.5 vs B1 rules"]
p_b0 = r["paired model noisy_or q>=0.5 vs B0 (VETR)"]
h = {}
h["H1"] = {
    "claim": "model - B1 >= +0.10 and interval excludes 0",
    "diff": p_b1["diff"],
    "ci": [p_b1["lo"], p_b1["hi"]],
    "holds": bool(p_b1["diff"] >= 0.10 and p_b1["lo"] > 0),
}
h["H2"] = {
    "claim": "model specificity >= 0.60 with recall >= 0.90; B0 specificity < 0.20",
    "model_specificity": mod["specificity"],
    "model_recall": mod["recall"],
    "b0_specificity": b0["specificity"],
    "holds": bool(mod["specificity"] >= 0.60 and mod["recall"] >= 0.90 and b0["specificity"] < 0.20),
}
h["H3"] = {
    "claim": "non-inferiority: lower interval bound of model - B0 above -0.03 (superiority only if above 0)",
    "diff": p_b0["diff"],
    "ci": [p_b0["lo"], p_b0["hi"]],
    "non_inferior": bool(p_b0["lo"] > -0.03),
    "superior": bool(p_b0["lo"] > 0),
}


def number_probs(gold_path: str) -> tuple[np.ndarray, np.ndarray]:
    gold = json.loads(Path(gold_path).read_text())["gold"]
    q, y = [], []
    for d, labels in gold.items():
        pred = pd.read_parquet(PROCESSED / "predictions" / f"{d}.parquet")
        agg: dict[str, float] = {}
        for (n, _a), v in ledger_for(pred).items():
            agg[n] = max(agg.get(n, 0.0), v)
        for n, lab in labels.items():
            lab = {"B": "B", "N": "N", "R": "N", "U": "U"}[lab]
            if lab != "U" and n in agg:
                q.append(agg[n])
                y.append(lab == "B")
    return np.asarray(q), np.asarray(y)


qd, yd = number_probs("results/ledger_gold_majority3.json")  # development
qt, yt = number_probs(f"results/ledger_gold_{TAG}_majority_binding.json")  # test
c = M.choose_threshold(qd, yd, target=0.95)
if c:
    conf = np.maximum(qt, 1 - qt)
    keep = conf >= c["t"]
    acc = float(((qt[keep] >= 0.5) == yt[keep]).mean()) if keep.any() else float("nan")
    cov = float(keep.mean())
    h["H4"] = {
        "claim": "dev-chosen threshold: coverage >= 0.85 and accuracy >= 0.90 on test",
        "t_from_dev": c["t"],
        "dev_coverage": c["coverage"],
        "dev_accuracy": c["accuracy"],
        "test_coverage": cov,
        "test_accuracy": acc,
        "holds": bool(cov >= 0.85 and acc >= 0.90),
    }
else:
    h["H4"] = {"claim": "dev threshold", "holds": False, "note": "no threshold reached the dev target"}
Path("results/test_report.json" if TAG == "test" else f"results/test_report_{TAG}.json").write_text(
    json.dumps(h, indent=1, default=float)
)
for k, v in h.items():
    print(k, json.dumps(v, default=lambda x: round(float(x), 3)))
