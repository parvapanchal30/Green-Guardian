"""Cluster bootstrap and risk-coverage metrics for classification evaluation (docs/EVALUATION_PROTOCOL.md section 8). Pure.

METHOD (version `cluster-bootstrap/1`, recorded in every report)

* Estimand: the value that a pooled metric (accuracy, macro-F1, per-class recall or precision, coverage, selective risk)
  would take on a NEW random sample of independent groups (farms or sites, per the protocol's test-split unit) drawn from
  the same population as the evaluated ones. It is not "the accuracy on these exact images".
* Why clusters: images of one plant, plot or farm are correlated. Treating them as independent makes intervals too
  narrow (the Wilson interval used elsewhere assumes independence). The independent unit is the GROUP.
* Resampling unit: the group. Each replicate draws as many groups as there are, with replacement, keeps every image of a
  drawn group, and recomputes the metric on the pooled images (a ratio estimator, as the point estimate is).
* Replicates: 2,000 by default, never fewer than 1,000 (the protocol minimum). Seed: explicit, recorded; the same inputs,
  seed and replicate count give identical output regardless of the order of the rows.
* Interval: percentile interval at the stated confidence (default 95%), with the bootstrap standard error. The point
  estimate is the metric on the original data, not the mean of the replicates.
* Degenerate and insufficient cases: fewer than 2 groups is refused (no between-group variation can be estimated).
  Fewer than 10 groups gives an interval but flags every interval `ci_reliable: false`, because percentile bootstrap
  intervals are known to be too narrow with few clusters (10 is a conventional guard, not a domain-approved number). A metric
  that is undefined in a replicate (for example a class absent from the resample) drops that replicate; if more than 5% of
  replicates are dropped, no interval is reported for that metric and the reason is stated. A replicate set with zero
  spread (perfect or constant results) is reported with a warning that the bootstrap cannot express uncertainty there.

LIMITATIONS: the bootstrap does not fix a biased or unrepresentative test set, label errors, or leakage; a small
number of groups makes any interval unreliable; percentile intervals are not bias-corrected; group-level effects such as
camera or season are only captured if the groups span them. This module implements a statistical method. It is not
domain approval of any threshold and it does not make a model good.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Any

METHOD_VERSION = "cluster-bootstrap/1"
DEFAULT_REPLICATES = 2000
MIN_REPLICATES = 1000
MIN_GROUPS = 2
RELIABLE_GROUPS = 10
MIN_VALID_FRACTION = 0.95
AURC_WORK_LIMIT = 20_000_000  # items x replicates; beyond this the AURC interval is skipped (and said so)
ABSTAINED = "(abstained)"


class StatisticsError(ValueError):
    """The inputs cannot support the requested statistic."""


# ------------------------------------------------------------------------------------------------ small helpers
def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile (the common 'type 7' definition) of an already sorted, non-empty list."""
    if not sorted_values:
        raise StatisticsError("no values")
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _check_confidences(confidences: list[float] | None, n: int) -> None:
    if confidences is None:
        return
    if len(confidences) != n:
        raise StatisticsError("confidences must match the number of predictions")
    for c in confidences:
        if isinstance(c, bool) or not isinstance(c, int | float) or not math.isfinite(c) or not 0.0 <= c <= 1.0:
            raise StatisticsError("confidences must be finite numbers between 0 and 1")


# ------------------------------------------------------------------------------------------------ risk-coverage
def risk_coverage_curve(truth: list[str], predicted: list[str | None], confidences: list[float]) -> dict[str, Any]:
    """Selective-prediction curve. A prediction of None is an ABSTENTION by the model: it is never covered, at any threshold.

    Accepting every answered item whose confidence is at least a threshold gives a point: coverage = accepted / all items,
    selective risk = wrong among accepted / accepted. Items with equal confidence enter together, so the curve does not
    depend on the arbitrary order of ties. AURC is the area under the step curve over the covered range (0, max coverage];
    `mean_selective_risk` divides it by that range. Lower is better; compare it with `overall_error_when_answering_all`.
    """
    n = len(truth)
    if n == 0:
        raise StatisticsError("nothing to evaluate")
    if len(predicted) != n:
        raise StatisticsError("truth and predicted must have the same length")
    _check_confidences(confidences, n)
    answered = [(c, t != p) for t, p, c in zip(truth, predicted, confidences, strict=True) if p is not None]
    abstained = n - len(answered)
    out: dict[str, Any] = {
        "n": n, "answered": len(answered), "abstained_by_model": abstained,
        "max_coverage": len(answered) / n, "points": [], "aurc": None, "mean_selective_risk": None,
        "overall_error_when_answering_all": None,
        "notes": ["abstentions by the model are never covered and never counted as errors in selective risk"],
    }  # fmt: skip
    if not answered:
        out["notes"].append("the model answered nothing: there is no curve")
        return out
    answered.sort(key=lambda x: -x[0])
    accepted = errors = 0
    points: list[dict[str, Any]] = []
    i = 0
    while i < len(answered):
        j = i
        while j < len(answered) and answered[j][0] == answered[i][0]:
            accepted += 1
            errors += answered[j][1]
            j += 1
        points.append({
            "threshold": answered[i][0], "coverage": accepted / n, "selective_risk": errors / accepted,
            "accepted": accepted, "errors": errors,
        })  # fmt: skip
        i = j
    area, previous = 0.0, 0.0
    for p in points:
        area += p["selective_risk"] * (p["coverage"] - previous)
        previous = p["coverage"]
    out["points"] = points
    out["aurc"] = area
    out["mean_selective_risk"] = area / previous
    out["overall_error_when_answering_all"] = points[-1]["selective_risk"]
    return out


def risk_at_coverage(curve: dict[str, Any], target: float) -> dict[str, Any] | None:
    """The curve point with the smallest coverage that is at least `target` (it may overshoot, because items enter in
    tied groups), or None if the model never reaches that coverage."""
    if not 0.0 < target <= 1.0:
        raise StatisticsError("target coverage must be in (0, 1]")
    for p in curve["points"]:
        if p["coverage"] >= target:
            return p
    return None


# ------------------------------------------------------------------------------------------------ group aggregation
def _confusion_metrics(conf: Counter, classes: list[str]) -> dict[str, Any]:
    """Pooled metrics from a confusion Counter keyed (truth, prediction-or-None)."""
    n = sum(conf.values())
    correct = sum(v for (t, p), v in conf.items() if t == p)
    answered = sum(v for (_, p), v in conf.items() if p is not None)
    answered_wrong = sum(v for (t, p), v in conf.items() if p is not None and t != p)
    support: Counter[str] = Counter()
    predicted_as: Counter[str] = Counter()
    tp: Counter[str] = Counter()
    for (t, p), v in conf.items():
        support[t] += v
        if p is not None:
            predicted_as[p] += v
        if t == p:
            tp[t] += v
    recalls: dict[str, float | None] = {}
    precisions: dict[str, float | None] = {}
    f1s: list[float] = []
    for c in classes:
        recalls[c] = tp[c] / support[c] if support[c] else None
        precisions[c] = tp[c] / predicted_as[c] if predicted_as[c] else None
        if support[c]:  # macro-F1 averages over the classes that exist in THIS sample
            r, pr = recalls[c] or 0.0, precisions[c]
            f1s.append(0.0 if not pr or not r else 2 * pr * r / (pr + r))
    return {
        "accuracy": correct / n if n else None,
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "coverage": answered / n if n else None,
        "selective_risk": answered_wrong / answered if answered else None,
        "classes_present": len(f1s),
        **{f"recall:{c}": recalls[c] for c in classes},
        **{f"precision:{c}": precisions[c] for c in classes},
    }


def _interval(
    values: list[float], estimate: float | None, total: int, confidence: float, reliable: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "estimate": estimate,
        "ci": None,
        "se": None,
        "valid_replicates": len(values),
        "ci_reliable": reliable,
    }
    if estimate is None:
        out["reason"] = "the metric is undefined on the original data"
        return out
    if len(values) < MIN_VALID_FRACTION * total:
        out["reason"] = (
            f"the metric was undefined in {total - len(values)} of {total} resamples (a class or all answers were missing "
            "from them), so no interval is reported"
        )
        return out
    values = sorted(values)
    alpha = (1.0 - confidence) / 2.0
    out["ci"] = [percentile(values, alpha), percentile(values, 1.0 - alpha)]
    mean = sum(values) / len(values)
    out["se"] = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1)) if len(values) > 1 else 0.0
    if out["ci"][0] == out["ci"][1]:
        out["warning"] = (
            "zero spread across resamples: the bootstrap cannot express uncertainty for constant or perfect results"
        )
    return out


def cluster_bootstrap(
    truth: list[str],
    predicted: list[str | None],
    groups: list[str],
    *,
    confidences: list[float] | None = None,
    threshold: float | None = None,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = 0,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Cluster-bootstrap report. `threshold`, if given with `confidences`, turns every prediction below it into an
    abstention before anything is computed (choose the threshold on the validation set, never on the test set)."""
    n = len(truth)
    if n == 0:
        raise StatisticsError("nothing to evaluate")
    if not (len(predicted) == len(groups) == n):
        raise StatisticsError("truth, predicted and groups must have the same length")
    if any(not isinstance(g, str) or not g for g in groups):
        raise StatisticsError("every item needs a non-empty group")
    if replicates < MIN_REPLICATES:
        raise StatisticsError(f"at least {MIN_REPLICATES} replicates are required (the protocol minimum)")
    if not 0.5 <= confidence < 1.0:
        raise StatisticsError("confidence must be in [0.5, 1)")
    _check_confidences(confidences, n)
    if threshold is not None:
        if confidences is None:
            raise StatisticsError("a threshold needs confidences")
        if not 0.0 <= threshold <= 1.0:
            raise StatisticsError("threshold must be in [0, 1]")
        predicted = [
            p if (p is not None and c >= threshold) else None for p, c in zip(predicted, confidences, strict=True)
        ]

    ids = sorted(set(groups))
    if len(ids) < MIN_GROUPS:
        raise StatisticsError(
            f"{len(ids)} group(s): at least {MIN_GROUPS} independent groups are needed to estimate uncertainty"
        )
    index = {g: i for i, g in enumerate(ids)}
    per_group: list[Counter] = [Counter() for _ in ids]
    for t, p, g in zip(truth, predicted, groups, strict=True):
        per_group[index[g]][(t, p)] += 1
    classes = sorted(set(truth))
    sizes = [sum(c.values()) for c in per_group]

    def pooled(chosen: list[int]) -> Counter:
        total: Counter = Counter()
        for gi in chosen:
            total.update(per_group[gi])
        return total

    original = _confusion_metrics(pooled(list(range(len(ids)))), classes)
    rng = random.Random(seed)
    names = [k for k in original if k not in ("classes_present",)]
    draws: dict[str, list[float]] = {k: [] for k in names}
    class_dropouts = 0
    for _ in range(replicates):
        chosen = rng.choices(range(len(ids)), k=len(ids))
        m = _confusion_metrics(pooled(chosen), classes)
        class_dropouts += m["classes_present"] < len(classes)
        for k in names:
            if m[k] is not None:
                draws[k].append(m[k])

    reliable = len(ids) >= RELIABLE_GROUPS
    warnings: list[str] = []
    if not reliable:
        warnings.append(
            f"only {len(ids)} groups: percentile bootstrap intervals are too narrow with few clusters; treat every interval as optimistic"
        )
    if class_dropouts:
        warnings.append(
            f"a class was missing from {class_dropouts} of {replicates} resamples; macro-F1 averages over the classes present in each resample"
        )
    metrics = {k: _interval(draws[k], original[k], replicates, confidence, reliable) for k in names}

    # how much narrower the usual independent-images interval is
    from .evaluation import wilson_interval

    k_correct = round(original["accuracy"] * n)
    wl, wh = wilson_interval(k_correct, n)
    acc_ci = metrics["accuracy"]["ci"]
    ratio = (acc_ci[1] - acc_ci[0]) / (wh - wl) if acc_ci and wh > wl else None

    report: dict[str, Any] = {
        "method": METHOD_VERSION, "estimand": "pooled metric on a new random sample of independent groups from the same population",
        "resampling_unit": "group", "replicates": replicates, "seed": seed, "confidence": confidence,
        "n_items": n, "n_groups": len(ids), "group_size": {"min": min(sizes), "max": max(sizes), "mean": n / len(ids)},
        "threshold": threshold, "ci_reliable": reliable, "metrics": metrics,
        "accuracy_interval_width_vs_wilson": ratio, "warnings": warnings,
        "limitations": [
            "the interval reflects sampling of groups only, not label errors, leakage or an unrepresentative test set",
            "percentile intervals are not bias-corrected and are optimistic with few groups",
            "this is a statistical method, not domain approval of any threshold",
        ],
    }  # fmt: skip

    if confidences is not None:
        curve_source = [(t, p, c) for t, p, c in zip(truth, predicted, confidences, strict=True)]
        curve = risk_coverage_curve(
            [t for t, _, _ in curve_source], [p for _, p, _ in curve_source], [c for _, _, c in curve_source]
        )
        report["risk_coverage"] = {
            k: curve[k] for k in ("aurc", "mean_selective_risk", "max_coverage", "answered", "abstained_by_model")
        }
        report["risk_coverage"]["aurc_interval"] = _aurc_interval(
            truth, predicted, confidences, groups, ids, replicates, seed, confidence, reliable
        )
    return report


def _aurc_interval(
    truth, predicted, confidences, groups, ids, replicates, seed, confidence, reliable
) -> dict[str, Any]:
    n = len(truth)
    if n * replicates > AURC_WORK_LIMIT:
        return {
            "estimate": None,
            "ci": None,
            "reason": f"skipped: {n} items x {replicates} resamples exceeds the work limit",
        }
    members: dict[str, list[int]] = {g: [] for g in ids}
    for i, g in enumerate(groups):
        members[g].append(i)
    base = risk_coverage_curve(truth, predicted, confidences)
    rng = random.Random(seed + 1)  # an independent stream, so adding this interval never changes the other results
    values: list[float] = []
    for _ in range(replicates):
        idx: list[int] = []
        for gi in rng.choices(range(len(ids)), k=len(ids)):
            idx.extend(members[ids[gi]])
        c = risk_coverage_curve([truth[i] for i in idx], [predicted[i] for i in idx], [confidences[i] for i in idx])
        if c["aurc"] is not None:
            values.append(c["aurc"])
    return _interval(values, base["aurc"], replicates, confidence, reliable)
