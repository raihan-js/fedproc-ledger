"""Mention-role classifier: structural features + character TF-IDF of the context, one-vs-rest logistic regression,
temperature-scaled probabilities. Checkbox item lines are decided by rule (objective glyph), not by the model."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.rules.baseline import BINDING


@dataclass
class RoleModel:
    classes: list[str]
    dv: DictVectorizer
    tv: TfidfVectorizer
    clf: OneVsRestClassifier
    temperature: float = 1.0

    def _x(self, feats: list[dict[str, float]], ctx: list[str]) -> Any:
        return hstack([self.dv.transform(feats), self.tv.transform(ctx)]).tocsr()

    def proba(self, feats: list[dict[str, float]], ctx: list[str]) -> np.ndarray:
        """Calibrated role probabilities, columns in `self.classes` order."""
        p = self.clf.predict_proba(self._x(feats, ctx))
        full = np.zeros((len(feats), len(self.classes)))
        for j, c in enumerate(self.clf.classes_):
            full[:, self.classes.index(c)] = p[:, j]
        full = full / np.clip(full.sum(axis=1, keepdims=True), 1e-12, None)
        return M.softmax(np.log(np.clip(full, 1e-9, 1.0)), self.temperature)

    def binding_prob(self, p: np.ndarray) -> np.ndarray:
        cols = [i for i, c in enumerate(self.classes) if c in BINDING]
        return np.asarray(p[:, cols].sum(axis=1))

    def exclusion_prob(self, p: np.ndarray) -> np.ndarray:
        j = self.classes.index("EXPLICITLY_EXCLUDED") if "EXPLICITLY_EXCLUDED" in self.classes else None
        return np.zeros(len(p)) if j is None else np.asarray(p[:, j])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self))

    @staticmethod
    def load(path: Path) -> RoleModel:
        m = pickle.loads(path.read_bytes())  # our own artifact, written by save()
        assert isinstance(m, RoleModel)
        return m


def fit(
    feats: list[dict[str, float]], ctx: list[str], y: list[str], temperature: float = 1.0, C: float = 0.5
) -> RoleModel:
    dv = DictVectorizer(sparse=True)
    tv = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=3, max_features=8000, sublinear_tf=True)
    X = hstack([dv.fit_transform(feats), tv.fit_transform(ctx)]).tocsr()
    clf = OneVsRestClassifier(LogisticRegression(solver="liblinear", C=C, class_weight="balanced")).fit(X, y)
    return RoleModel(sorted(set(y)), dv, tv, clf, temperature)
