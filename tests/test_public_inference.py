"""Parity: public numpy-only inference matches the sklearn RoleModel exactly."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "public")
from inference import LedgerScorer

from fedproc_ledger.label.commands import build_items
from fedproc_ledger.model.classifier import RoleModel
from fedproc_ledger.model.dataset import featurize_doc


def test_numpy_inference_matches_sklearn():
    docs = Path("data/interim/round7_docs.txt").read_text().split()[:4]
    model = RoleModel.load(Path("data/models/role_model.pkl"))
    pub = LedgerScorer(Path("data/release/fedproc_ledger_v1.npz"))
    assert pub.classes == model.classes
    for d in docs:
        rows = featurize_doc(d, build_items(d))[:150]
        feats = [r["feat"] for r in rows]
        ctx = [r["context"] for r in rows]
        a = model.proba(feats, ctx)
        b = pub.proba(feats, ctx)
        assert a.shape == b.shape and len(a)
        assert np.allclose(a, b, rtol=1e-9, atol=1e-12), (d, np.abs(a - b).max())
        assert np.allclose(model.binding_prob(a), pub.binding_prob(b), rtol=1e-9, atol=1e-12)
