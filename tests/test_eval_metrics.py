import numpy as np
import pytest

from fedproc_ledger.eval import metrics as M
from fedproc_ledger.eval.leaderboard import log_run, read


def test_ledger_counts_and_micro_f1_pool_counts_over_documents():
    pred = [{"a", "b"}, {"x"}, set()]
    gold = [{"b", "c"}, {"x"}, {"y"}]
    c = M.ledger_counts(pred, gold)
    assert c.tolist() == [[1, 1, 1], [1, 0, 0], [0, 0, 1]]
    f = M.micro_f(c)  # tp 2, fp 1, fn 2
    assert (
        f["precision"] == pytest.approx(2 / 3) and f["recall"] == pytest.approx(0.5) and f["f"] == pytest.approx(4 / 7)
    )
    assert M.micro_f(c, beta=2.0)["f"] == pytest.approx(5 * (2 / 3) * 0.5 / (4 * (2 / 3) + 0.5))  # F2 leans on recall


def test_bootstrap_resamples_documents_and_is_reproducible():
    rng = np.random.default_rng(1)
    pred = [{f"n{i}" for i in range(10) if rng.random() < 0.8} for _ in range(60)]
    gold = [{f"n{i}" for i in range(10) if rng.random() < 0.8} for _ in range(60)]
    c = M.ledger_counts(pred, gold)
    a, b = M.cluster_bootstrap(c, n_boot=2000, seed=3), M.cluster_bootstrap(c, n_boot=2000, seed=3)
    assert a == b and a["lo"] < a["point"] < a["hi"]
    assert (
        M.cluster_bootstrap(c[:6], n_boot=2000)["hi"] - M.cluster_bootstrap(c[:6], n_boot=2000)["lo"]
        > a["hi"] - a["lo"]
    )  # fewer documents, wider


def test_paired_bootstrap_separates_a_better_system_from_an_identical_one():
    gold = [{f"n{i}" for i in range(8)} for _ in range(40)]
    weak = [set(list(g)[:5]) for g in gold]
    c_gold, c_weak = M.ledger_counts(gold, gold), M.ledger_counts(weak, gold)
    better = M.paired_bootstrap(c_weak, c_gold, n_boot=2000)
    assert better["diff"] > 0.2 and better["lo"] > 0 and better["share_not_better"] == 0
    same = M.paired_bootstrap(c_weak, c_weak, n_boot=2000)
    assert same["diff"] == 0 and same["lo"] == 0 == same["hi"]
    with pytest.raises(ValueError):
        M.paired_bootstrap(c_weak, c_gold[:5])


def test_temperature_scaling_fixes_an_overconfident_model_and_leaves_a_calibrated_one():
    rng = np.random.default_rng(0)
    n = 4000
    true_logits = rng.normal(size=(n, 3)) * 1.5
    labels = np.array([rng.choice(3, p=p) for p in M.softmax(true_logits)])
    t_ok = M.fit_temperature(true_logits, labels)
    assert 0.85 < t_ok < 1.15
    t_over = M.fit_temperature(true_logits * 3.0, labels)  # the same model, three times too sure
    assert 2.6 < t_over < 3.4
    assert M.nll(M.softmax(true_logits * 3, t_over), labels) < M.nll(M.softmax(true_logits * 3), labels)


def test_ledger_probability_noisy_or_max_exclusion_and_alternates():
    ms = [
        {"number": "52.219-9", "alternate": None, "b": 0.5, "e": 0.0},
        {"number": "52.219-9", "alternate": None, "b": 0.5, "e": 0.0},
        {"number": "52.219-9", "alternate": "Alternate II", "b": 0.4, "e": 0.0},
        {"number": "52.204-21", "alternate": None, "b": 0.9, "e": 0.5},
    ]
    q = M.ledger_probabilities(ms)
    assert q[("52.219-9", None)] == pytest.approx(0.75) and q[("52.219-9", "Alternate II")] == pytest.approx(0.4)
    assert q[("52.204-21", None)] == pytest.approx(0.9 * 0.5)  # an exclusion cuts the probability
    assert M.ledger_probabilities(ms, mode="max")[("52.219-9", None)] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        M.ledger_probabilities(ms, mode="mean")


def test_verdicts_have_an_abstain_band_and_t_cannot_be_below_one_half():
    q = {("a", None): 0.97, ("b", None): 0.5, ("c", None): 0.03, ("d", None): 0.8}
    assert M.verdicts(q, 0.9) == {("a", None): True, ("b", None): None, ("c", None): False, ("d", None): None}
    with pytest.raises(ValueError):
        M.verdicts(q, 0.4)


def test_choose_threshold_maximises_coverage_under_the_precision_target():
    q = np.array([0.99, 0.98, 0.97, 0.95, 0.9, 0.85, 0.2, 0.1, 0.05, 0.6])
    y = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)  # the 0.85 entry is wrong, the 0.6 entry is wrong
    got = M.choose_threshold(q, y, target=1.0)
    assert got["t"] == pytest.approx(0.9) and got["accuracy"] == 1.0 and got["coverage"] == pytest.approx(0.7)
    loose = M.choose_threshold(q, y, target=0.8)
    assert loose["coverage"] >= got["coverage"] and loose["accuracy"] >= 0.8
    assert M.choose_threshold(np.array([0.55, 0.55]), np.array([False, False]), 0.9) is None  # unreachable


def test_best_f1_threshold_beats_the_default_when_scores_are_shifted():
    q = np.array([0.45, 0.4, 0.38, 0.1, 0.05])
    y = np.array([1, 1, 1, 0, 0], dtype=bool)
    assert M.best_f1_threshold(q, y) == {"threshold": 0.38, "f1": 1.0}


def test_calibration_metrics_reward_honest_confidence():
    rng = np.random.default_rng(5)
    conf = rng.uniform(0.5, 1.0, 5000)
    honest = rng.random(5000) < conf
    over = rng.random(5000) < conf - 0.2
    assert M.ece(conf, honest) < 0.03 and M.ece(conf, over) > 0.15
    p, y = np.array([0.9, 0.2, 0.7]), np.array([1, 0, 0])
    assert M.brier(p, y) == pytest.approx((0.01 + 0.04 + 0.49) / 3)
    assert M.log_loss_binary(p, y) == pytest.approx(-(np.log(0.9) + np.log(0.8) + np.log(0.3)) / 3)


def test_risk_coverage_and_aurc_are_lower_when_confidence_orders_errors_last():
    y = np.array([1, 1, 1, 1, 0, 0], dtype=bool)
    good = np.array(
        [0.99, 0.95, 0.9, 0.8, 0.3, 0.6]
    )  # the one wrong prediction (0.6 for a negative) is the least confident
    bad = np.array([0.6, 0.95, 0.9, 0.8, 0.3, 0.99])  # the confident one is wrong
    rg, rb = M.risk_coverage(good, y), M.risk_coverage(bad, y)
    assert rg["aurc"] < rb["aurc"] and rg["risk"][0] == 0 and rb["risk"][0] == 1 and rg["coverage"][-1] == 1


def test_leaderboard_counts_the_looks_at_dev(tmp_path):
    path = tmp_path / "lb.jsonl"
    a = log_run(path, "b1", {"x": 1}, {"f1": 0.7})
    b = log_run(path, "b1+feat", {"x": 2}, {"f1": 0.75})
    t = log_run(path, "final", {"x": 2}, {"f1": 0.74}, split="test")
    assert (a["looks_at_split"], b["looks_at_split"], t["looks_at_split"]) == (1, 2, 1)
    assert a["config_hash"] != b["config_hash"] and len(read(path)) == 3
