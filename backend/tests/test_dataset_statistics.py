"""Cluster bootstrap and risk-coverage metrics. Synthetic data only; no model exists."""

from __future__ import annotations

import math
import random

import pytest

from app.modules.datasets import statistics as st
from app.modules.datasets.evaluation import wilson_interval
from app.modules.datasets.statistics import (
    StatisticsError,
    cluster_bootstrap,
    percentile,
    risk_at_coverage,
    risk_coverage_curve,
)

R = st.MIN_REPLICATES  # 1,000: the protocol minimum, and fast enough for tests


def correlated(n_groups=20, size=30, good=10):
    """Groups are all-or-nothing: the first `good` groups are always right, the rest always wrong (maximal correlation)."""
    truth, pred, groups = [], [], []
    for g in range(n_groups):
        for k in range(size):
            truth.append("a" if k % 2 else "b")
            pred.append(("a" if k % 2 else "b") if g < good else ("b" if k % 2 else "a"))
            groups.append(f"farm-{g:02d}")
    return truth, pred, groups


def independent(n_groups=40, size=1, p=0.7, seed=1):
    rng = random.Random(seed)
    truth, pred, groups = [], [], []
    for g in range(n_groups):
        for _ in range(size):
            t = rng.choice("ab")
            truth.append(t)
            pred.append(t if rng.random() < p else ("b" if t == "a" else "a"))
            groups.append(f"farm-{g:03d}")
    return truth, pred, groups


# ------------------------------------------------------------------------------------------------ helpers
def test_percentile_is_linear_interpolation():
    v = [1.0, 2.0, 3.0, 4.0]
    assert percentile(v, 0.0) == 1.0 and percentile(v, 1.0) == 4.0 and percentile(v, 0.5) == 2.5
    assert math.isclose(percentile(v, 0.25), 1.75)
    with pytest.raises(StatisticsError):
        percentile([], 0.5)


# ------------------------------------------------------------------------------------------------ the bootstrap
def test_correlated_images_give_a_much_wider_interval_than_the_independent_assumption():
    t, p, g = correlated()
    rep = cluster_bootstrap(t, p, g, replicates=R, seed=3)
    acc = rep["metrics"]["accuracy"]
    assert acc["estimate"] == 0.5 and acc["ci"][0] < 0.35 and acc["ci"][1] > 0.65
    lo, hi = wilson_interval(300, 600)
    assert (hi - lo) < 0.09  # what the naive interval claims for the very same 600 images
    assert rep["accuracy_interval_width_vs_wilson"] > 3.5


def test_with_independent_images_the_two_intervals_agree_roughly():
    t, p, g = independent(n_groups=400, size=1)
    rep = cluster_bootstrap(t, p, g, replicates=R, seed=2)
    assert 0.8 < rep["accuracy_interval_width_vs_wilson"] < 1.25


def test_the_interval_covers_the_true_value_about_as_often_as_claimed():
    hits, sims = 0, 120
    for s in range(sims):
        t, p, g = independent(n_groups=40, size=5, p=0.7, seed=100 + s)
        ci = cluster_bootstrap(t, p, g, replicates=R, seed=s)["metrics"]["accuracy"]["ci"]
        hits += ci[0] <= 0.7 <= ci[1]
    assert 0.86 <= hits / sims <= 1.0, hits / sims  # nominal 95%; a little low is expected with 40 clusters


def test_results_are_deterministic_and_independent_of_row_order():
    t, p, g = independent(n_groups=30, size=4)
    a = cluster_bootstrap(t, p, g, replicates=R, seed=7)
    b = cluster_bootstrap(t, p, g, replicates=R, seed=7)
    assert a == b
    order = list(range(len(t)))
    random.Random(5).shuffle(order)
    c = cluster_bootstrap([t[i] for i in order], [p[i] for i in order], [g[i] for i in order], replicates=R, seed=7)
    assert c == a
    other = cluster_bootstrap(t, p, g, replicates=R, seed=8)["metrics"]["accuracy"]
    assert other["se"] != a["metrics"]["accuracy"]["se"]  # a different seed gives a different resampling


def test_the_report_states_its_method_estimand_unit_seed_and_limits():
    t, p, g = independent()
    rep = cluster_bootstrap(t, p, g, replicates=R, seed=11, confidence=0.9)
    assert rep["method"] == "cluster-bootstrap/1" and rep["resampling_unit"] == "group"
    assert (rep["replicates"], rep["seed"], rep["confidence"]) == (R, 11, 0.9)
    assert "new random sample of independent groups" in rep["estimand"] and rep["limitations"]
    assert rep["n_groups"] == 40 and rep["group_size"] == {"min": 1, "max": 1, "mean": 1.0}


def test_per_class_and_macro_metrics_have_intervals():
    t, p, g = independent(n_groups=60, size=5)
    m = cluster_bootstrap(t, p, g, replicates=R, seed=1)["metrics"]
    for key in ("accuracy", "macro_f1", "recall:a", "recall:b", "precision:a", "coverage"):
        assert m[key]["ci"] and m[key]["ci"][0] <= m[key]["estimate"] <= m[key]["ci"][1], key
    assert m["coverage"]["estimate"] == 1.0 and m["selective_risk"]["estimate"] == pytest.approx(
        1 - m["accuracy"]["estimate"]
    )


def test_a_threshold_turns_low_confidence_answers_into_abstentions():
    t, p, g = independent(n_groups=50, size=4, p=0.7)
    conf = [0.9 if a == b else 0.4 for a, b in zip(t, p, strict=True)]  # a perfectly informative confidence
    rep = cluster_bootstrap(t, p, g, confidences=conf, threshold=0.5, replicates=R, seed=1)
    m = rep["metrics"]
    assert m["selective_risk"]["estimate"] == 0.0 and 0.5 < m["coverage"]["estimate"] < 0.9
    assert m["accuracy"]["estimate"] < 1.0  # abstentions still count as not-correct in accuracy


# ------------------------------------------------------------------------------------------------ failures and edge cases
def test_empty_mismatched_and_malformed_inputs_are_refused():
    t, p, g = independent()
    for call in (
        lambda: cluster_bootstrap([], [], [], replicates=R),
        lambda: cluster_bootstrap(t, p[:-1], g, replicates=R),
        lambda: cluster_bootstrap(t, p, g[:-1], replicates=R),
        lambda: cluster_bootstrap(t, p, ["" if i == 0 else x for i, x in enumerate(g)], replicates=R),
        lambda: cluster_bootstrap(t, p, g, replicates=R - 1),
        lambda: cluster_bootstrap(t, p, g, replicates=R, confidence=0.2),
        lambda: cluster_bootstrap(t, p, g, replicates=R, threshold=0.5),
        lambda: cluster_bootstrap(t, p, g, confidences=[0.5] * (len(t) - 1), replicates=R),
        lambda: cluster_bootstrap(t, p, g, confidences=[1.5] * len(t), replicates=R),
        lambda: cluster_bootstrap(t, p, g, confidences=[float("nan")] * len(t), replicates=R),
    ):
        with pytest.raises(StatisticsError):
            call()


def test_one_group_cannot_support_uncertainty():
    t, p, _ = independent(n_groups=10)
    with pytest.raises(StatisticsError, match="at least 2 independent groups"):
        cluster_bootstrap(t, p, ["only"] * len(t), replicates=R)


def test_few_groups_give_an_interval_flagged_unreliable():
    t, p, g = independent(n_groups=5, size=20)
    rep = cluster_bootstrap(t, p, g, replicates=R)
    assert rep["ci_reliable"] is False and all(m["ci_reliable"] is False for m in rep["metrics"].values())
    assert any("only 5 groups" in w for w in rep["warnings"])
    assert cluster_bootstrap(*independent(n_groups=12, size=5), replicates=R)["ci_reliable"] is True


def test_a_class_present_in_few_groups_gets_no_interval_and_a_reason():
    t, p, g = independent(n_groups=30, size=4)
    t += ["rare", "rare"]
    p += ["rare", "a"]
    g += ["farm-000", "farm-000"]  # the rare class lives in a single group
    rep = cluster_bootstrap(t, p, g, replicates=R, seed=1)
    recall = rep["metrics"]["recall:rare"]
    assert recall["estimate"] == 0.5 and recall["ci"] is None and "undefined in" in recall["reason"]
    assert any("a class was missing" in w for w in rep["warnings"])
    assert rep["metrics"]["accuracy"]["ci"]  # other metrics are unaffected


def test_perfect_results_are_flagged_as_having_no_expressible_uncertainty():
    t = ["a", "b"] * 30
    rep = cluster_bootstrap(t, list(t), [f"g{i // 2}" for i in range(60)], replicates=R)
    acc = rep["metrics"]["accuracy"]
    assert acc["ci"] == [1.0, 1.0] and "zero spread" in acc["warning"]


def test_a_model_that_answers_nothing_has_no_selective_risk():
    t, _, g = independent(n_groups=20, size=3)
    rep = cluster_bootstrap(t, [None] * len(t), g, replicates=R)
    m = rep["metrics"]
    assert m["coverage"]["estimate"] == 0.0 and m["selective_risk"]["estimate"] is None
    assert "undefined" in m["selective_risk"]["reason"] and m["accuracy"]["estimate"] == 0.0


# ------------------------------------------------------------------------------------------------ risk-coverage
def test_the_risk_coverage_curve_by_hand():
    truth = ["a", "a", "a", "a"]
    pred = ["a", "a", "b", "b"]  # items 3 and 4 are wrong
    conf = [0.9, 0.8, 0.6, 0.3]
    c = risk_coverage_curve(truth, pred, conf)
    assert [(p["threshold"], p["coverage"], p["selective_risk"]) for p in c["points"]] == [
        (0.9, 0.25, 0.0), (0.8, 0.5, 0.0), (0.6, 0.75, 1 / 3), (0.3, 1.0, 0.5)
    ]  # fmt: skip
    assert c["aurc"] == pytest.approx(0.0 * 0.25 + 0.0 * 0.25 + (1 / 3) * 0.25 + 0.5 * 0.25)
    assert c["mean_selective_risk"] == pytest.approx(c["aurc"]) and c["overall_error_when_answering_all"] == 0.5


def test_tied_confidences_enter_together_so_order_does_not_matter():
    truth = ["a"] * 4
    pred = ["a", "b", "a", "b"]
    forward = risk_coverage_curve(truth, pred, [0.7, 0.7, 0.7, 0.7])
    backward = risk_coverage_curve(truth[::-1], pred[::-1], [0.7, 0.7, 0.7, 0.7])
    assert forward["points"] == backward["points"] and len(forward["points"]) == 1
    assert forward["points"][0]["selective_risk"] == 0.5


def test_abstentions_are_never_covered_and_never_counted_as_selective_errors():
    truth = ["a", "a", "a", "a"]
    pred = ["a", None, "b", None]
    c = risk_coverage_curve(truth, pred, [0.9, 0.99, 0.5, 0.99])
    assert c["abstained_by_model"] == 2 and c["max_coverage"] == 0.5
    assert [(p["coverage"], p["selective_risk"]) for p in c["points"]] == [(0.25, 0.0), (0.5, 0.5)]
    assert c["aurc"] == pytest.approx(0.0 * 0.25 + 0.5 * 0.25) and c["mean_selective_risk"] == pytest.approx(0.25)


def test_a_good_confidence_ranking_beats_a_useless_one():
    rng = random.Random(4)
    truth = ["a"] * 400
    wrong = [rng.random() < 0.3 for _ in truth]
    pred = ["b" if w else "a" for w in wrong]
    informative = risk_coverage_curve(truth, pred, [0.2 if w else 0.9 for w in wrong])
    useless = risk_coverage_curve(truth, pred, [rng.random() for _ in truth])
    assert informative["aurc"] < useless["aurc"]
    assert informative["overall_error_when_answering_all"] == pytest.approx(useless["overall_error_when_answering_all"])


def test_risk_at_a_target_coverage_and_its_edge_cases():
    c = risk_coverage_curve(["a"] * 4, ["a", "a", "b", "b"], [0.9, 0.8, 0.6, 0.3])
    assert risk_at_coverage(c, 0.5)["selective_risk"] == 0.0
    assert risk_at_coverage(c, 0.6)["coverage"] == 0.75  # overshoots: items enter in steps
    assert risk_at_coverage(c, 1.0)["selective_risk"] == 0.5
    partial = risk_coverage_curve(["a"] * 4, ["a", None, "a", None], [0.9, 0.9, 0.8, 0.8])
    assert risk_at_coverage(partial, 0.9) is None  # never reaches 90% coverage
    for bad in (0.0, -1, 1.5):
        with pytest.raises(StatisticsError):
            risk_at_coverage(c, bad)


def test_curve_edge_cases():
    none_answered = risk_coverage_curve(["a", "b"], [None, None], [0.5, 0.5])
    assert none_answered["points"] == [] and none_answered["aurc"] is None and none_answered["max_coverage"] == 0.0
    perfect = risk_coverage_curve(["a", "b"], ["a", "b"], [0.9, 0.8])
    assert perfect["aurc"] == 0.0 and perfect["max_coverage"] == 1.0
    for bad in (
        lambda: risk_coverage_curve([], [], []),
        lambda: risk_coverage_curve(["a"], ["a", "b"], [0.5]),
        lambda: risk_coverage_curve(["a"], ["a"], [0.5, 0.5]),
        lambda: risk_coverage_curve(["a"], ["a"], [True]),
        lambda: risk_coverage_curve(["a"], ["a"], [-0.1]),
    ):
        with pytest.raises(StatisticsError):
            bad()


def test_the_bootstrap_reports_an_aurc_interval_reproducibly():
    t, p, g = independent(n_groups=30, size=4, p=0.7)
    conf = [0.9 if a == b else 0.4 for a, b in zip(t, p, strict=True)]
    a = cluster_bootstrap(t, p, g, confidences=conf, replicates=R, seed=5)
    b = cluster_bootstrap(t, p, g, confidences=conf, replicates=R, seed=5)
    assert a == b and a["risk_coverage"]["aurc_interval"]["ci"]
    lo, hi = a["risk_coverage"]["aurc_interval"]["ci"]
    assert lo <= a["risk_coverage"]["aurc"] <= hi


def test_a_very_large_aurc_interval_is_skipped_and_says_so(monkeypatch):
    monkeypatch.setattr(st, "AURC_WORK_LIMIT", 10)
    t, p, g = independent(n_groups=20, size=2)
    rep = cluster_bootstrap(t, p, g, confidences=[0.5] * len(t), replicates=R)
    assert (
        rep["risk_coverage"]["aurc_interval"]["ci"] is None
        and "work limit" in rep["risk_coverage"]["aurc_interval"]["reason"]
    )


def test_the_interval_level_is_the_stated_confidence():
    """Widths of nested intervals follow the normal quantiles: 95% is about 2.9 times as wide as 50% (1.96 / 0.674)."""
    t, p, g = independent(n_groups=300, size=1, p=0.7, seed=9)

    def width(conf):
        lo, hi = cluster_bootstrap(t, p, g, replicates=R, seed=1, confidence=conf)["metrics"]["accuracy"]["ci"]
        return hi - lo

    w50, w90, w95, w99 = width(0.5), width(0.9), width(0.95), width(0.99)
    assert 0 < w50 < w90 < w95 < w99
    assert 2.4 < w95 / w50 < 3.5 and 1.1 < w99 / w95 < 1.5


def test_a_threshold_keeps_answers_at_or_above_it():
    truth, pred, groups = ["a"] * 6, ["a"] * 6, ["g1", "g1", "g2", "g2", "g3", "g3"]
    conf = [0.5, 0.5, 0.5, 0.9, 0.9, 0.9]
    cov = cluster_bootstrap(truth, pred, groups, confidences=conf, threshold=0.5, replicates=R)["metrics"]["coverage"][
        "estimate"
    ]
    assert cov == 1.0  # confidence equal to the threshold is kept
    assert (
        cluster_bootstrap(truth, pred, groups, confidences=conf, threshold=0.51, replicates=R)["metrics"]["coverage"][
            "estimate"
        ]
        == 0.5
    )
