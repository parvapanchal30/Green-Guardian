"""Inter-reviewer agreement. Hand-computed kappa values; synthetic decisions only."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.datasets.agreement import REJECTED, Decision, agreement_report, cohens_kappa

T0 = datetime(2026, 10, 18, tzinfo=UTC)


def test_kappa_known_values():
    # classic 2x2 example: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po 0.7, pe 0.5, kappa 0.4
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert math.isclose(cohens_kappa(a, b) or 0, 0.4)
    assert cohens_kappa(["a", "b", "a"], ["a", "b", "a"]) == 1.0
    assert cohens_kappa(["a", "b"], ["b", "a"]) == -1.0  # systematic disagreement


def test_kappa_is_undefined_when_there_is_nothing_to_compare():
    assert cohens_kappa([], []) is None
    assert cohens_kappa(["a", "a"], ["a", "a"]) is None  # chance agreement is already 1
    with pytest.raises(ValueError):
        cohens_kappa(["a"], [])


def dec(sample, reviewer, status, before="a", after=None, minutes=0) -> Decision:
    return Decision(sample, reviewer, status, before, after, T0 + timedelta(minutes=minutes))


def test_a_pair_needs_two_different_reviewers():
    r = agreement_report([dec("s1", "r1", "accepted"), dec("s2", "r1", "accepted")])
    assert r["samples_with_a_decision"] == 2 and r["samples_with_two_reviewers"] == 0 and r["cohens_kappa"] is None
    assert any("fewer than 2" in c for c in r["caveats"])


def test_accept_and_correct_decisions_are_compared_by_the_resulting_label():
    ds = [
        dec("s1", "r1", "accepted", "a"), dec("s1", "r2", "accepted", "a"),  # agree: a / a
        dec("s2", "r1", "accepted", "b"), dec("s2", "r2", "corrected", "b", "a"),  # disagree: b / a
        dec("s3", "r1", "corrected", "a", "b"), dec("s3", "r2", "accepted", "b"),  # agree: b / b
        dec("s4", "r1", "rejected", "a"), dec("s4", "r2", "rejected", "a"),  # agree: rejected
    ]  # fmt: skip
    r = agreement_report(ds)
    assert r["samples_with_two_reviewers"] == 4 and r["observed_agreement"] == 0.75
    assert r["disagreements"] == [{"sample_id": "s2", "verdicts": ["b", "a"]}]
    assert r["cohens_kappa"] is not None and 0 < r["cohens_kappa"] < 1
    assert REJECTED not in r["disagreements"][0]["verdicts"]


def test_only_a_reviewers_latest_decision_counts():
    ds = [
        dec("s1", "r1", "accepted", "a", minutes=0),
        dec("s1", "r1", "corrected", "a", "b", minutes=5),  # r1 changed their mind
        dec("s1", "r2", "accepted", "b", minutes=10),
    ]
    r = agreement_report(ds)
    assert r["samples_with_two_reviewers"] == 1 and r["observed_agreement"] == 1.0


def test_a_third_reviewer_never_changes_an_existing_pair():
    base = [dec("s1", "r1", "accepted", "a", minutes=0), dec("s1", "r2", "accepted", "a", minutes=1)]
    with_third = [*base, dec("s1", "r3", "rejected", "a", minutes=2)]
    assert agreement_report(base)["observed_agreement"] == agreement_report(with_third)["observed_agreement"] == 1.0
    assert agreement_report(with_third)["reviewers"] == 3


def test_non_decisions_are_ignored_and_small_samples_are_flagged():
    r = agreement_report([dec("s1", "r1", "under_review"), dec("s1", "r2", "unreviewed")])
    assert r["samples_with_a_decision"] == 0
    ds = [dec(f"s{i}", rv, "accepted", "ab"[i % 2]) for i in range(6) for rv in ("r1", "r2")]
    out = agreement_report(ds)
    assert out["cohens_kappa"] == 1.0 and any("very uncertain" in c for c in out["caveats"])
    assert any("not verified as qualified" in c for c in out["caveats"])
