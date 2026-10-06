"""Scores, confidence and thresholds (docs/EVALUATION_DESIGN.md). Pure functions: no model, no data, no side effects."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

Key = tuple[str, str | None]  # (clause number, alternate)


# -- the primary score: document-level binding-set F1 ---------------------------------------------------------------
def ledger_counts(pred: Sequence[Collection[Any]], gold: Sequence[Collection[Any]]) -> np.ndarray:
    """Per-document (tp, fp, fn) of predicted versus gold ledger entries, shape (n_docs, 3)."""
    if len(pred) != len(gold):
        raise ValueError("pred and gold need one set per document")
    rows = []
    for p, g in zip(pred, gold, strict=True):
        p, g = set(p), set(g)
        rows.append((len(p & g), len(p - g), len(g - p)))
    return np.asarray(rows, dtype=float).reshape(-1, 3)


def prf(tp: float, fp: float, fn: float, beta: float = 1.0) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    b2 = beta * beta
    f = (1 + b2) * p * r / (b2 * p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f": f}


def micro_f(counts: np.ndarray, beta: float = 1.0) -> dict[str, float]:
    tp, fp, fn = counts.sum(axis=0)
    return prf(tp, fp, fn, beta)


def _resample_stat(counts: np.ndarray, idx: np.ndarray, beta: float) -> np.ndarray:
    s = counts[idx].sum(axis=1)  # (n_boot, 3)
    tp, fp, fn = s[:, 0], s[:, 1], s[:, 2]
    p = np.divide(tp, tp + fp, out=np.zeros_like(tp), where=(tp + fp) > 0)
    r = np.divide(tp, tp + fn, out=np.zeros_like(tp), where=(tp + fn) > 0)
    b2 = beta * beta
    den = b2 * p + r
    return np.asarray(np.divide((1 + b2) * p * r, den, out=np.zeros_like(p), where=den > 0), dtype=float)


def cluster_bootstrap(
    counts: np.ndarray, beta: float = 1.0, n_boot: int = 10_000, seed: int = 0, level: float = 0.95
) -> dict[str, float]:
    """Point estimate and percentile interval of the micro F over documents, resampling DOCUMENTS (never mentions)."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(counts), size=(n_boot, len(counts)))
    samples = _resample_stat(counts, idx, beta)
    a = (1 - level) / 2
    return {
        "point": micro_f(counts, beta)["f"],
        "lo": float(np.quantile(samples, a)),
        "hi": float(np.quantile(samples, 1 - a)),
    }


def paired_bootstrap(
    counts_a: np.ndarray,
    counts_b: np.ndarray,
    beta: float = 1.0,
    n_boot: int = 10_000,
    seed: int = 0,
    level: float = 0.95,
) -> dict[str, float]:
    """F(b) - F(a) on the same document resamples: difference, interval, share of resamples where b is not better."""
    if counts_a.shape != counts_b.shape:
        raise ValueError("both systems need counts for the same documents")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(counts_a), size=(n_boot, len(counts_a)))
    diff = _resample_stat(counts_b, idx, beta) - _resample_stat(counts_a, idx, beta)
    a = (1 - level) / 2
    return {
        "diff": micro_f(counts_b, beta)["f"] - micro_f(counts_a, beta)["f"],
        "lo": float(np.quantile(diff, a)),
        "hi": float(np.quantile(diff, 1 - a)),
        "share_not_better": float((diff <= 0).mean()),
    }


# -- confidence: temperature scaling and the ledger probability -------------------------------------
def softmax(z: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=float) / temperature
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)  # type: ignore[no-any-return]


def nll(probs: np.ndarray, labels: np.ndarray, eps: float = 1e-12) -> float:
    return float(-np.log(np.clip(probs[np.arange(len(labels)), labels], eps, 1.0)).mean())


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """The single T > 0 minimising NLL of softmax(logits / T) on (dev) data."""
    res = minimize_scalar(
        lambda lt: nll(softmax(logits, float(np.exp(lt))), labels), bounds=(-3.0, 3.0), method="bounded"
    )
    return float(np.exp(res.x))


def ledger_probabilities(mentions: Iterable[Mapping[str, Any]], mode: str = "noisy_or") -> dict[Key, float]:
    """q(n, a) = [1 - prod_m (1 - b_m)] * prod over all mentions of n of (1 - e_m).

    Each mention is {number, alternate, b, e}: b = probability its role is binding, e = probability it is
    EXPLICITLY_EXCLUDED.
    `mode="max"` replaces the noisy-OR by the largest b (mentions of one clause are correlated, so noisy-OR can
    overstate).
    """
    if mode not in ("noisy_or", "max"):
        raise ValueError(mode)
    by_entry: dict[Key, list[float]] = defaultdict(list)
    not_excluded: dict[str, float] = defaultdict(lambda: 1.0)
    for m in mentions:
        by_entry[(m["number"], m.get("alternate"))].append(float(m["b"]))
        not_excluded[m["number"]] *= 1.0 - float(m.get("e", 0.0))
    out: dict[Key, float] = {}
    for (n, a), bs in by_entry.items():
        base = 1.0 - float(np.prod([1.0 - b for b in bs])) if mode == "noisy_or" else max(bs)
        out[(n, a)] = base * not_excluded[n]
    return out


# -- decisions: verdict, abstain band, threshold choice ---------------------------------------------
def verdicts(q: Mapping[Key, float], t: float) -> dict[Key, bool | None]:
    """True if q >= t, False if q <= 1 - t, else None (not determined). Needs t >= 0.5."""
    if t < 0.5:
        raise ValueError("t must be at least 0.5")
    return {k: (True if v >= t else False if v <= 1 - t else None) for k, v in q.items()}


def choose_threshold(q: np.ndarray, y: np.ndarray, target: float = 0.98) -> dict[str, float] | None:
    """The t that gives the largest coverage whose verdict accuracy is >= target (dev data only).

    Confidence of an entry is max(q, 1 - q); entries with confidence >= t get a verdict. Returns None if no t reaches
    the target.
    """
    q, y = np.asarray(q, dtype=float), np.asarray(y, dtype=bool)
    conf = np.maximum(q, 1 - q)
    correct = (q >= 0.5) == y
    best = None
    for u in np.unique(conf):  # ascending: the first u that reaches the target has the largest coverage
        keep = conf >= u
        acc = float(correct[keep].mean())
        if acc >= target:
            best = {"t": float(u), "coverage": float(keep.mean()), "accuracy": acc}
            break
    return best


def best_f1_threshold(q: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """The single threshold on q that maximises F1 of the binding class (dev data only)."""
    q, y = np.asarray(q, dtype=float), np.asarray(y, dtype=bool)
    best = {"threshold": 0.5, "f1": -1.0}
    for t in np.unique(q):
        pred = q >= t
        tp, fp, fn = float((pred & y).sum()), float((pred & ~y).sum()), float((~pred & y).sum())
        f = prf(tp, fp, fn)["f"]
        if f > best["f1"]:
            best = {"threshold": float(t), "f1": f}
    return best


# -- diagnostics: calibration and risk-coverage -----------------------------------------------------------------
def ece(conf: np.ndarray, correct: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error with equal-mass bins."""
    conf, correct = np.asarray(conf, dtype=float), np.asarray(correct, dtype=float)
    order = np.argsort(conf)
    total = 0.0
    for chunk in np.array_split(order, bins):
        if len(chunk):
            total += len(chunk) / len(conf) * abs(conf[chunk].mean() - correct[chunk].mean())
    return float(total)


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2).mean())


def log_loss_binary(p: np.ndarray, y: np.ndarray, eps: float = 1e-12) -> float:
    p, y = np.clip(np.asarray(p, dtype=float), eps, 1 - eps), np.asarray(y, dtype=float)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def risk_coverage(q: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Error rate among the k most confident entries for every k, and AURC (mean error over coverage)."""
    q, y = np.asarray(q, dtype=float), np.asarray(y, dtype=bool)
    conf = np.maximum(q, 1 - q)
    order = np.argsort(-conf, kind="stable")
    wrong = ((q >= 0.5) != y)[order].astype(float)
    k = np.arange(1, len(q) + 1)
    risk = np.cumsum(wrong) / k
    return {"coverage": k / len(q), "risk": risk, "aurc": float(risk.mean())}
