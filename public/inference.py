"""Numpy-only inference for the public fedproc-ledger v1 weights (no pickle, no sklearn).

Replicates `RoleModel.proba` exactly: DictVectorizer features + char_wb (2,4)
TF-IDF with sublinear tf and l2 norm, one-vs-rest logistic sigmoid per class,
renormalisation over classes, temperature softmax. Parity with the sklearn
model is tested in the research repository (tests/test_public_inference.py).

Inputs (same contract as `featurize_doc`):
  feats: list of {feature_name: value} dicts (structural mention features)
  contexts: list of mention context strings
Returns: (n_mentions, n_classes) calibrated probabilities, columns = CLASSES.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

_WS = re.compile(r"\s+")

ROLE_LABELS = (
    "CHECKLIST_NOT_SELECTED",
    "CHECKLIST_SELECTED",
    "EXPLICITLY_EXCLUDED",
    "FULL_TEXT",
    "INCORPORATED_BY_REFERENCE",
    "INDEX_ENTRY",
    "INTERNAL_REFERENCE",
    "NARRATIVE_MENTION",
    "NOT_A_CLAUSE",
)
BINDING_ROLES = {"INCORPORATED_BY_REFERENCE", "FULL_TEXT", "CHECKLIST_SELECTED"}
CLASSES = ROLE_LABELS  # fixed order not assumed; the archive stores its own order


class LedgerScorer:
    """Mention-role scorer loaded from fedproc_ledger_v1.npz."""

    def __init__(self, path: str | Path) -> None:
        z = np.load(Path(path), allow_pickle=False)
        self.classes = [str(c) for c in z["classes"]]
        self.temperature = float(z["temperature"])
        self.dv_vocab = {str(w): i for i, w in enumerate(z["dv_vocab"])}
        self.tv_terms = {str(w): i for i, w in enumerate(z["tv_terms"])}
        self.tv_idf = np.asarray(z["tv_idf"], dtype=float)
        self.coef = np.asarray(z["coef"], dtype=float)
        self.intercept = np.asarray(z["intercept"], dtype=float)
        self.n_dv = len(self.dv_vocab)

    def _vectorize(self, feats: list[dict[str, float]], contexts: list[str]) -> np.ndarray:
        n = len(feats)
        x = np.zeros((n, self.n_dv + len(self.tv_terms)))
        for i, f in enumerate(feats):
            row = x[i]
            for k, v in f.items():
                j = self.dv_vocab.get(str(k))
                if j is not None:
                    row[j] = float(v)
        for i, ctx in enumerate(contexts):
            counts: dict[int, int] = {}
            for w in _WS.sub(" ", ctx.lower()).split():
                w = " " + w + " "
                for size in (2, 3, 4):
                    for off in range(len(w) - size + 1):
                        j = self.tv_terms.get(w[off : off + size])
                        if j is not None:
                            counts[j] = counts.get(j, 0) + 1
            row = x[i]
            base = self.n_dv
            norm = 0.0
            for j, c in counts.items():
                v = (1.0 + math.log(c)) * self.tv_idf[j]
                row[base + j] = v
                norm += v * v
            if norm > 0:
                row[base:] /= math.sqrt(norm)
        return x

    def proba(self, feats: list[dict[str, float]], contexts: list[str]) -> np.ndarray:
        """Calibrated role probabilities, columns in `self.classes` order."""
        x = self._vectorize(feats, contexts)
        z = x @ self.coef.T + self.intercept
        p = 1.0 / (1.0 + np.exp(-z))
        p = p / np.clip(p.sum(axis=1, keepdims=True), 1e-12, None)
        lz = np.log(np.clip(p, 1e-9, 1.0)) / self.temperature
        lz = lz - lz.max(axis=1, keepdims=True)
        e = np.exp(lz)
        return e / e.sum(axis=1, keepdims=True)

    def binding_prob(self, p: np.ndarray) -> np.ndarray:
        cols = [i for i, c in enumerate(self.classes) if c in BINDING_ROLES]
        return np.asarray(p[:, cols].sum(axis=1))
