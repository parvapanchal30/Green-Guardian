"""Evaluation metrics (hand-computed expectations) and the claim gate. Synthetic labels only; there is no model."""

from __future__ import annotations

import math

import pytest

from app.modules.datasets.evaluation import (
    ClaimInputs,
    claim_readiness,
    evaluate_classification,
    expected_calibration_error,
    wilson_interval,
)


def test_wilson_interval_matches_known_values():
    lo, hi = wilson_interval(8, 10)
    assert round(lo, 3) == 0.490 and round(hi, 3) == 0.943  # standard worked example
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo0, hi0 = wilson_interval(0, 20)
    assert lo0 == 0.0 and 0.1 < hi0 < 0.2
    lo1, hi1 = wilson_interval(20, 20)
    assert hi1 == 1.0 and 0.8 < lo1 < 0.9


def test_confusion_matrix_precision_recall_f1_by_hand():
    truth = ["a", "a", "a", "a", "b", "b", "b", "c"]
    pred = ["a", "a", "b", "a", "b", "b", "a", "c"]
    r = evaluate_classification(truth, pred)
    assert r["n"] == 8 and r["accuracy"] == 6 / 8
    assert r["confusion_matrix"]["a"] == {"a": 3, "b": 1, "c": 0, "(abstained)": 0}
    a, b, c = r["per_class"]["a"], r["per_class"]["b"], r["per_class"]["c"]
    assert a["precision"] == 3 / 4 and a["recall"] == 3 / 4 and a["support"] == 4
    assert b["precision"] == 2 / 3 and b["recall"] == 2 / 3
    assert c["precision"] == 1.0 and c["recall"] == 1.0 and c["f1"] == 1.0
    assert math.isclose(r["macro_f1"], (0.75 + 2 / 3 + 1.0) / 3)
    assert r["majority_baseline_accuracy"] == 0.5  # 4 of 8 are "a"


def test_abstentions_count_as_errors_and_lower_coverage():
    r = evaluate_classification(["a", "a", "b", "b"], ["a", None, "b", None])
    assert r["accuracy"] == 0.5 and r["coverage"] == 0.5
    assert r["confusion_matrix"]["a"]["(abstained)"] == 1 and r["per_class"]["a"]["recall"] == 0.5


def test_a_class_never_predicted_has_no_precision_and_zero_f1():
    r = evaluate_classification(["a", "b", "b"], ["a", "a", "a"])
    assert r["per_class"]["b"]["precision"] is None and r["per_class"]["b"]["recall"] == 0.0
    assert r["per_class"]["b"]["f1"] == 0.0


def test_accuracy_alone_is_shown_next_to_the_trivial_baseline():
    truth = ["a"] * 95 + ["b"] * 5
    r = evaluate_classification(truth, ["a"] * 100)  # a "model" that always says a
    assert r["accuracy"] == 0.95 == r["majority_baseline_accuracy"] and r["per_class"]["b"]["recall"] == 0.0


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        evaluate_classification(["a"], ["a", "b"])
    with pytest.raises(ValueError):
        evaluate_classification([], [])
    with pytest.raises(ValueError):
        evaluate_classification(["a"], ["a"], confidences=[0.5, 0.6])


def test_calibration_error():
    assert expected_calibration_error([True, True, True, True], [1.0, 1.0, 1.0, 1.0]) == 0.0
    over = expected_calibration_error([True, False, False, False], [0.9, 0.9, 0.9, 0.9])
    assert math.isclose(over, 0.65)  # accuracy 0.25 vs confidence 0.9
    r = evaluate_classification(["a", "b"], ["a", "a"], confidences=[0.9, 0.9])
    assert math.isclose(r["expected_calibration_error"], 0.4)


# ------------------------------------------------------------------------------------------------ claim gate
def inputs(**over) -> ClaimInputs:
    base = dict(
        dataset_kind="real", dataset_status="approved", samples=5000, reviewed_fraction=1.0,
        test_class_counts={"a": 300, "b": 200, "c": 139}, leakage_violations=0, quality_passed=True,
    )  # fmt: skip
    base.update(over)
    return ClaimInputs(**base)  # type: ignore[arg-type]


def blockers(**over) -> set[str]:
    return {b["code"] for b in claim_readiness(inputs(**over))["blockers"]}


def test_a_claim_is_blocked_today_even_for_perfect_data_because_no_reviewer_or_protocol_is_verified():
    out = claim_readiness(inputs())
    assert out["allowed"] is False
    assert {b["code"] for b in out["blockers"]} == {"no_verified_reviewer", "no_evaluation_protocol"}
    assert all(not b["resolvable_in_application"] for b in out["blockers"])


def test_each_data_problem_has_its_own_blocker():
    assert "synthetic_data" in blockers(dataset_kind="synthetic")
    assert "dataset_not_approved" in blockers(dataset_status="under_review")
    assert "quality_checks_failed" in blockers(quality_passed=False)
    assert "split_leakage" in blockers(leakage_violations=2)
    assert "labels_not_reviewed" in blockers(reviewed_fraction=0.5)
    assert "test_set_too_small" in blockers(test_class_counts={"a": 50, "b": 50})
    assert "test_set_too_small" in blockers(test_class_counts={})


def test_only_a_verified_reviewer_and_a_registered_protocol_lift_the_structural_blockers():
    ok = claim_readiness(
        ClaimInputs(
            "real",
            "approved",
            5000,
            1.0,
            {"a": 400, "b": 400},
            0,
            True,
            qualified_reviewer_verified=True,
            evaluation_protocol_registered=True,
        )
    )
    assert ok["allowed"] is True and ok["blockers"] == []


# ------------------------------------------------------------------------------------------------ sample-size rule
def test_the_planning_rule_gives_the_protocols_numbers():
    from app.modules.datasets.evaluation import MIN_TEST_PER_CLASS, required_images_per_class

    assert required_images_per_class() == 139 == MIN_TEST_PER_CLASS
    assert required_images_per_class(recall=0.5) == 385  # the worst case
    assert required_images_per_class(half_width=0.1) == 35  # a looser interval needs fewer images
    assert (
        required_images_per_class(recall=0.95)
        < required_images_per_class(recall=0.9)
        < required_images_per_class(recall=0.5)
    )
    for bad in ({"half_width": 0.0}, {"recall": 1.0}, {"recall": 0.0}, {"z": 0.0}):
        with pytest.raises(ValueError):
            required_images_per_class(**bad)


def gate(counts):
    return claim_readiness(inputs(test_class_counts=counts))


def test_the_boundary_is_139_images_per_class_and_two_qualifying_classes():
    codes = lambda out: {b["code"] for b in out["blockers"]}  # noqa: E731
    assert "test_set_too_small" in codes(gate({"a": 138, "b": 138}))
    assert "test_set_too_small" not in codes(gate({"a": 139, "b": 139}))
    assert "test_set_too_small" in codes(gate({"a": 139, "b": 138}))  # one qualifying class is not enough
    assert "test_set_too_small" in codes(gate({"a": 5000}))  # a single class cannot support a classification claim
    assert "test_set_too_small" not in codes(gate({"a": 139, "b": 139, "c": 0}))


def test_a_class_with_too_few_images_is_excluded_from_claims_but_does_not_block_the_others():
    rule = gate({"a": 300, "b": 139, "rare": 12})["sample_size_rule"]
    assert rule["claimable_classes"] == ["a", "b"] and rule["classes_excluded_from_claims"] == {"rare": 12}
    assert rule["required_per_class"] == 139 and rule["worst_case_per_class"] == 385
    assert "not evidence that a model is accurate" in rule["basis"]


def test_meeting_the_sample_size_rule_never_clears_the_reviewer_or_protocol_blockers():
    out = gate({"a": 10_000, "b": 10_000})
    assert {b["code"] for b in out["blockers"]} == {"no_verified_reviewer", "no_evaluation_protocol"} and out[
        "allowed"
    ] is False
