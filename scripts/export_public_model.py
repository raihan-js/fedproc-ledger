"""Export the frozen role model to a safe public format (no pickle).

Reads data/models/role_model.pkl (sha256 9e9611a4...) and writes
data/release/fedproc_ledger_v1.npz: classes, temperature, DictVectorizer
vocabulary, char-TF-IDF vocabulary + idf + params, OvR logistic coefficients.
`public/inference.py` loads it with numpy only. Parity is tested in
tests/test_public_inference.py.
"""

from __future__ import annotations

import hashlib

import numpy as np

from fedproc_ledger.model.classifier import RoleModel
from fedproc_ledger.paths import DATA

MODEL = DATA / "models" / "role_model.pkl"
OUT = DATA / "release" / "fedproc_ledger_v1.npz"


def main() -> None:
    sha = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    assert sha.startswith("9e9611a4"), sha
    m = RoleModel.load(MODEL)
    dv_vocab = np.array(sorted(m.dv.vocabulary_, key=m.dv.vocabulary_.__getitem__))
    tv_terms = np.array(sorted(m.tv.vocabulary_, key=m.tv.vocabulary_.__getitem__))
    order = [list(m.clf.classes_).index(c) for c in m.classes]
    coef = np.vstack([m.clf.estimators_[j].coef_[0] for j in order])
    intercept = np.array([m.clf.estimators_[j].intercept_[0] for j in order])
    assert coef.shape[1] == len(dv_vocab) + len(tv_terms), (coef.shape, len(dv_vocab), len(tv_terms))
    np.savez_compressed(
        OUT,
        classes=np.array(m.classes),
        temperature=np.float64(m.temperature),
        dv_vocab=dv_vocab,
        tv_terms=tv_terms,
        tv_idf=np.asarray(m.tv.idf_, dtype=np.float64),
        coef=coef.astype(np.float64),
        intercept=intercept.astype(np.float64),
        sklearn_model_sha256=np.array(sha),
    )
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB) from pickle {sha[:16]}")


if __name__ == "__main__":
    main()
