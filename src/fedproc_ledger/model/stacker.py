"""Number-level stacker (D-038): logistic regression over features aggregated from the mentions of one number.

Trained on the agent's number labels of rounds 2 to 4 (development data); applied after the role model and the rules."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from fedproc_ledger.model.commands import ledger_for

ROLES = [
    "INCORPORATED_BY_REFERENCE", "FULL_TEXT", "CHECKLIST_SELECTED", "CHECKLIST_NOT_SELECTED", "INTERNAL_REFERENCE",
    "NARRATIVE_MENTION", "INDEX_ENTRY", "NOT_A_CLAUSE",
]  # fmt: skip
FEATURES = [
    "qmax", "qnor", "n", "n_model", "n_rule", "bp_mean", "bp_min", *["max_" + r for r in ROLES],
]  # fmt: skip
STACKER = Path("data/models/stacker_v3.pkl")


def number_features(pred: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct number of one document's predictions (index = number)."""
    qm = ledger_for(pred, "max")
    qn = ledger_for(pred, "noisy_or")
    out = {}
    for n, g in pred.groupby("number"):
        f = {
            "qmax": max((v for (k, _a), v in qm.items() if k == n), default=0.0),
            "qnor": max((v for (k, _a), v in qn.items() if k == n), default=0.0),
            "n": float(len(g)),
            "n_model": float((g["source"] == "model").sum()),
            "n_rule": float((g["source"] != "model").sum()),
            "bp_mean": float(g["binding_prob"].mean()),
            "bp_min": float(g["binding_prob"].min()),
        }
        for r in ROLES:
            col = f"p_{r}"
            f["max_" + r] = float(g[col].max()) if col in g else 0.0
        out[n] = f
    return pd.DataFrame.from_dict(out, orient="index", columns=FEATURES) if out else pd.DataFrame(columns=FEATURES)


@dataclass
class Stacker:
    clf: LogisticRegression

    def proba(self, feats: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.clf.predict_proba(feats[FEATURES].values)[:, 1]) if len(feats) else np.zeros(0)

    def save(self, path: Path = STACKER) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self))

    @staticmethod
    def load(path: Path = STACKER) -> Stacker:
        s = pickle.loads(path.read_bytes())  # our own artifact, written by save()
        assert isinstance(s, Stacker)
        return s
