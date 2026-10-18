"""Evaluation harness for classification, and the gate that decides whether any performance CLAIM may be made. Pure.

The harness only computes metrics from (truth, prediction) pairs; it knows nothing about models and none exists yet.
`claim_readiness` is deliberately strict and partly unsatisfiable inside the application today: a scientific claim needs a
verified qualified reviewer and a registered field-domain evaluation protocol, and GreenGuardian records neither.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

Z95 = 1.959963984540054
MIN_REVIEWED_FRACTION = 0.95
MIN_CLAIM_CLASSES = 2  # a claim about classification needs at least two classes that each have enough test images
# Sample-size PLANNING rule from docs/EVALUATION_PROTOCOL.md section 8 (not a performance threshold).
PLANNING_HALF_WIDTH = 0.05  # the widest interval half-width we are willing to accept on a per-class recall
PLANNING_RECALL = 0.90  # the recall we plan around; the interval is widest (and n largest) at 0.50


def required_images_per_class(
    half_width: float = PLANNING_HALF_WIDTH, recall: float = PLANNING_RECALL, z: float = Z95
) -> int:
    """Smallest n for which a normal-approximation interval around a per-class recall near `recall` has half-width at most
    `half_width`: n = z^2 r (1 - r) / h^2, rounded UP. With the defaults this is 139; at recall 0.5 it is 385.

    ASSUMPTIONS: images of a class are independent (they are not, within a group: see the cluster bootstrap, which can
    need more), the true recall is near the planning value, and the normal approximation holds. This plans how many test
    images are needed to MEASURE recall with a given precision. It does not show that a model's recall is high enough, and
    meeting it proves nothing about accuracy."""
    if not 0.0 < half_width < 1.0 or not 0.0 < recall < 1.0 or z <= 0:
        raise ValueError("half_width and recall must be in (0, 1) and z positive")
    return math.ceil(z * z * recall * (1.0 - recall) / (half_width * half_width))


MIN_TEST_PER_CLASS = required_images_per_class()


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion; well behaved at small n and at 0 or 1, unlike the normal approximation."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def expected_calibration_error(correct: list[bool], confidences: list[float], bins: int = 10) -> float:
    n = len(correct)
    if n == 0:
        return 0.0
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if idx:
            acc = sum(correct[i] for i in idx) / len(idx)
            conf = sum(confidences[i] for i in idx) / len(idx)
            ece += len(idx) / n * abs(acc - conf)
    return ece


def evaluate_classification(
    truth: list[str], predicted: list[str | None], *, confidences: list[float] | None = None
) -> dict[str, Any]:
    """Metrics for single-label classification. A prediction of None means the model abstained: it counts as wrong and
    is reported as coverage, never silently dropped (dropping abstentions inflates accuracy)."""
    if len(truth) != len(predicted):
        raise ValueError("truth and predicted must have the same length")
    if confidences is not None and len(confidences) != len(truth):
        raise ValueError("confidences must match the number of predictions")
    n = len(truth)
    if n == 0:
        raise ValueError("nothing to evaluate")
    labels = sorted({*truth, *(p for p in predicted if p is not None)})
    matrix: dict[str, dict[str, int]] = {t: dict.fromkeys([*labels, "(abstained)"], 0) for t in labels}
    for t, p in zip(truth, predicted, strict=True):
        matrix[t][p if p is not None else "(abstained)"] += 1
    per_class: dict[str, dict[str, Any]] = {}
    for c in labels:
        tp = matrix[c][c]
        support = sum(matrix[c].values())
        predicted_c = sum(matrix[t][c] for t in labels)
        precision = tp / predicted_c if predicted_c else None
        recall = tp / support if support else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if support else None)
        lo, hi = wilson_interval(tp, support)
        per_class[c] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "recall_ci95": [round(lo, 4), round(hi, 4)] if support else None,
        }
    correct = [t == p for t, p in zip(truth, predicted, strict=True)]
    k = sum(correct)
    lo, hi = wilson_interval(k, n)
    f1s = [v["f1"] for v in per_class.values() if v["f1"] is not None and v["support"] > 0]
    out: dict[str, Any] = {
        "n": n,
        "accuracy": k / n,
        "accuracy_ci95": [round(lo, 4), round(hi, 4)],
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "coverage": sum(p is not None for p in predicted) / n,
        "per_class": per_class,
        "confusion_matrix": matrix,
        "majority_baseline_accuracy": max(Counter(truth).values()) / n,
    }
    if confidences is not None:
        out["expected_calibration_error"] = expected_calibration_error(correct, confidences)
    return out


@dataclass(frozen=True)
class ClaimInputs:
    dataset_kind: str  # real | synthetic
    dataset_status: str  # proposed | under_review | approved | rejected
    samples: int
    reviewed_fraction: float  # accepted + corrected, over all samples
    test_class_counts: dict[
        str, int
    ]  # test images per class, for EVERY class of the dataset (0 if absent from the test split)
    leakage_violations: int
    quality_passed: bool
    qualified_reviewer_verified: bool = False  # the application has no way to verify this yet
    evaluation_protocol_registered: bool = False  # nor a registry of field-domain protocols


def claim_readiness(i: ClaimInputs) -> dict[str, Any]:
    """May a model performance claim be made on this data? Returns the blockers; `allowed` is True only if none remain."""
    b: list[dict[str, Any]] = []

    def block(code: str, message: str, resolvable: bool = True) -> None:
        b.append({"code": code, "message": message, "resolvable_in_application": resolvable})

    if i.dataset_kind == "synthetic":
        block(
            "synthetic_data",
            "synthetic fixtures are not biological data; no performance claim about plants can rest on them",
            False,
        )
    if i.dataset_status != "approved":
        block("dataset_not_approved", f"dataset status is {i.dataset_status!r}; only an approved dataset may be used")
    if not i.quality_passed:
        block("quality_checks_failed", "the data-quality report has errors")
    if i.leakage_violations:
        block("split_leakage", f"{i.leakage_violations} leakage violation(s) between train and evaluation data")
    if i.reviewed_fraction < MIN_REVIEWED_FRACTION:
        block(
            "labels_not_reviewed",
            f"only {i.reviewed_fraction:.0%} of labels are reviewed (need at least {MIN_REVIEWED_FRACTION:.0%})",
        )
    claimable = sorted(c for c, n in i.test_class_counts.items() if n >= MIN_TEST_PER_CLASS)
    excluded = {c: n for c, n in sorted(i.test_class_counts.items()) if n < MIN_TEST_PER_CLASS}
    if len(claimable) < MIN_CLAIM_CLASSES:
        block(
            "test_set_too_small",
            f"only {len(claimable)} class(es) have at least {MIN_TEST_PER_CLASS} test images (need {MIN_CLAIM_CLASSES}); "
            f"counts: {dict(sorted(i.test_class_counts.items())) or 'no test images'}",
        )
    if not i.qualified_reviewer_verified:
        block(
            "no_verified_reviewer",
            "no qualified plant-health reviewer is verified; reviews record who decided but not their qualification",
            False,
        )
    if not i.evaluation_protocol_registered:
        block(
            "no_evaluation_protocol",
            "no defensible evaluation protocol (field-domain test data, acceptance thresholds, intended use) is registered",
            False,
        )
    return {
        "allowed": not b,
        "blockers": b,
        "sample_size_rule": {
            "required_per_class": MIN_TEST_PER_CLASS,
            "worst_case_per_class": required_images_per_class(recall=0.5),
            "claimable_classes": claimable,
            "classes_excluded_from_claims": excluded,
            "basis": (
                "n = z^2 r(1-r)/h^2 with z = 1.96, planning recall r = 0.90 and half-width h = 0.05, rounded up. A planning rule "
                "for measuring recall precisely under independence, not evidence that a model is accurate."
            ),
        },
    }
