"""Grouped splits and the independent leakage check. Synthetic records only."""

from __future__ import annotations

import random
from collections import Counter, defaultdict

import pytest

from app.modules.datasets.splits import SplitError, SplitItem, grouped_split, manifest_checksum, verify_no_leakage

FRACTIONS = {"train": 0.7, "validation": 0.15, "test": 0.15}


def corpus(n_groups: int = 40, seed: int = 1, labels=("a", "b", "c")) -> list[SplitItem]:
    rng = random.Random(seed)
    items = []
    for g in range(n_groups):
        label = rng.choice(labels)
        for k in range(rng.randint(1, 9)):
            items.append(SplitItem(f"g{g}-{k}", f"g{g}", label))
    return items


def groups_by_split(items, assignment):
    out = defaultdict(set)
    for i in items:
        out[i.group].add(assignment[i.id])
    return out


def test_no_group_is_ever_shared_between_splits():
    for seed in range(25):
        items = corpus(n_groups=30 + seed, seed=seed)
        r = grouped_split(items, FRACTIONS, seed)
        assert all(len(s) == 1 for s in groups_by_split(items, r.assignment).values())
        assert verify_no_leakage(items, r.assignment) == []


def test_every_item_is_assigned_exactly_once():
    items = corpus()
    r = grouped_split(items, FRACTIONS, 3)
    assert sorted(r.assignment) == sorted(i.id for i in items)
    assert set(r.assignment.values()) <= set(FRACTIONS)


def test_the_split_is_deterministic_and_the_seed_matters():
    items = corpus()
    a, b = grouped_split(items, FRACTIONS, 7), grouped_split(list(reversed(items)), FRACTIONS, 7)
    assert a.assignment == b.assignment and a.manifest_sha256 == b.manifest_sha256  # input order is irrelevant
    c = grouped_split(items, FRACTIONS, 8)
    assert c.assignment != a.assignment and c.manifest_sha256 != a.manifest_sha256


def test_sizes_are_close_to_the_requested_fractions_when_groups_are_plentiful():
    items = corpus(n_groups=300, seed=5)
    r = grouped_split(items, FRACTIONS, 0)
    for name, target in FRACTIONS.items():
        assert abs(r.stats[name]["actual_fraction"] - target) < 0.04, r.stats
    assert r.warnings == []


def test_classes_are_spread_across_splits_when_possible():
    items = corpus(n_groups=300, seed=6)
    r = grouped_split(items, FRACTIONS, 0)
    total = Counter(i.label for i in items)
    for name, target in FRACTIONS.items():
        for label, count in total.items():
            share = r.stats[name]["labels"].get(label, 0) / count
            assert abs(share - target) < 0.08, (name, label, share)


def test_a_dominant_group_is_reported_not_hidden():
    items = [SplitItem(f"big-{k}", "big", "a") for k in range(80)] + [
        SplitItem(f"s{g}-0", f"s{g}", "b") for g in range(10)
    ]
    r = grouped_split(items, FRACTIONS, 0)
    assert any("instead of" in w for w in r.warnings)  # the split cannot honour the fractions and says so
    assert verify_no_leakage(items, r.assignment) == []


def test_too_few_groups_is_an_error_not_a_leaky_split():
    two = [SplitItem(f"a{k}", "A", "x") for k in range(5)] + [SplitItem(f"b{k}", "B", "y") for k in range(5)]
    with pytest.raises(SplitError, match="cannot fill 3 splits"):
        grouped_split(two, FRACTIONS, 0)


@pytest.mark.parametrize(
    "fractions",
    [
        {"train": 1.0},
        {"train": 0.5, "test": 0.4},
        {"train": 0.6, "test": 0.6},
        {"train": 1.2, "test": -0.2},
        {"a": 0.0, "b": 1.0},
    ],
)
def test_invalid_fractions_are_rejected(fractions):
    with pytest.raises(SplitError):
        grouped_split(corpus(), fractions, 0)


def test_ungrouped_or_duplicate_items_are_rejected():
    with pytest.raises(SplitError, match="group key"):
        grouped_split([SplitItem("a", "", "x"), SplitItem("b", "g", "x")], {"train": 0.5, "test": 0.5})
    with pytest.raises(SplitError, match="unique"):
        grouped_split([SplitItem("a", "g1", "x"), SplitItem("a", "g2", "x")], {"train": 0.5, "test": 0.5})
    with pytest.raises(SplitError, match="no items"):
        grouped_split([], {"train": 0.5, "test": 0.5})


def test_a_class_missing_from_a_split_is_a_warning():
    items = [SplitItem(f"x{g}", f"gx{g}", "common") for g in range(30)] + [SplitItem("r0", "gr0", "rare")]
    r = grouped_split(items, FRACTIONS, 0)
    assert any("contains none of: rare" in w for w in r.warnings)


# ------------------------------------------------------------------------------------------------ the checker
def test_the_checker_catches_a_group_split_across_two_sets():
    items = corpus(10)
    assignment = grouped_split(items, {"train": 0.5, "test": 0.5}, 0).assignment
    victim = next(i for i in items if i.group == "g0")
    other = "test" if assignment[victim.id] == "train" else "train"
    assignment[victim.id] = other
    members = [i for i in items if i.group == "g0"]
    if len(members) > 1:  # make sure the group really is now in both sets
        assignment[members[1].id] = "train" if other == "test" else "test"
    kinds = {v["kind"] for v in verify_no_leakage(items, assignment)}
    assert "group_in_several_splits" in kinds


def test_the_checker_catches_identical_files_under_different_groups():
    items = [
        SplitItem("a", "g1", "x", content_sha256="f" * 64),
        SplitItem("b", "g2", "x", content_sha256="f" * 64),
        SplitItem("c", "g3", "x"),
    ]
    v = verify_no_leakage(items, {"a": "train", "b": "test", "c": "train"})
    assert [x["kind"] for x in v] == ["identical_file_in_several_splits"]
    assert verify_no_leakage(items, {"a": "train", "b": "train", "c": "test"}) == []


def test_the_checker_catches_near_duplicates_across_splits():
    items = [
        SplitItem("a", "g1", "x", phash="0" * 16),
        SplitItem("b", "g2", "x", phash="000000000000000f"),
        SplitItem("c", "g3", "x", phash="f" * 16),
    ]
    v = verify_no_leakage(items, {"a": "train", "b": "test", "c": "test"})
    assert [x["kind"] for x in v] == ["near_duplicate_across_splits"] and v[0]["ids"] == ["a", "b"]


def test_the_checker_reports_unassigned_items():
    items = corpus(5)
    assert verify_no_leakage(items, {})[0]["kind"] == "unassigned_items"


def test_the_manifest_checksum_detects_any_change():
    items = corpus()
    r = grouped_split(items, FRACTIONS, 2)
    assert manifest_checksum(r.assignment, 2, FRACTIONS) == r.manifest_sha256
    tampered = dict(r.assignment)
    k = next(iter(tampered))
    tampered[k] = "test" if tampered[k] != "test" else "train"
    assert manifest_checksum(tampered, 2, FRACTIONS) != r.manifest_sha256
    assert manifest_checksum(r.assignment, 3, FRACTIONS) != r.manifest_sha256
