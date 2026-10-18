"""Grouped, deterministic, versionable train/validation/test splits. Pure.

Why grouped: photos of the same plant, field or day are near-copies of each other. A random split puts some on each side,
the model "recognises" the plant, and the score measures memorisation. Here a whole GROUP is assigned to exactly one
split, and `verify_no_leakage` re-checks the result independently (groups, identical files, near-identical images).

Determinism: the same items, fractions and seed always give the same assignment and the same manifest checksum, so a
split can be recorded as a version and reproduced. Balancing is greedy by label so each split gets roughly its share of
each class; with few groups this cannot be perfect and the result reports what it could not achieve.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .quality import NEAR_DUPLICATE_HAMMING, hamming

TOLERANCE = 1e-6


@dataclass(frozen=True)
class SplitItem:
    id: str
    group: str
    label: str | None = None
    content_sha256: str | None = None
    phash: str | None = None


@dataclass
class SplitResult:
    assignment: dict[str, str]
    seed: int
    fractions: dict[str, float]
    manifest_sha256: str
    stats: dict[str, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SplitError(ValueError):
    pass


def _tiebreak(seed: int, group: str) -> str:
    return hashlib.sha256(f"{seed}|{group}".encode()).hexdigest()


def manifest_checksum(assignment: dict[str, str], seed: int, fractions: dict[str, float]) -> str:
    body = {
        "seed": seed,
        "fractions": {k: round(v, 9) for k, v in sorted(fractions.items())},
        "assignment": sorted(assignment.items()),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def grouped_split(items: list[SplitItem], fractions: dict[str, float], seed: int = 0) -> SplitResult:
    if not items:
        raise SplitError("there are no items to split")
    if len(fractions) < 2 or any(f <= 0 for f in fractions.values()):
        raise SplitError("fractions must name at least two splits, each greater than zero")
    if abs(sum(fractions.values()) - 1.0) > TOLERANCE:
        raise SplitError(f"fractions must sum to 1 (got {sum(fractions.values()):g})")
    if len({i.id for i in items}) != len(items):
        raise SplitError("item ids must be unique")
    if any(not i.group for i in items):
        raise SplitError(
            "every item needs a group key; an ungrouped item cannot be kept out of the other splits safely"
        )

    groups: dict[str, list[SplitItem]] = defaultdict(list)
    for it in items:
        groups[it.group].append(it)
    names = list(fractions)
    if len(groups) < len(names):
        raise SplitError(
            f"{len(groups)} group(s) cannot fill {len(names)} splits without sharing a group between splits"
        )

    total = len(items)
    label_total = Counter(i.label for i in items)
    target_n = {s: fractions[s] * total for s in names}
    target_label = {s: {lab: fractions[s] * c for lab, c in label_total.items()} for s in names}
    got_n: dict[str, float] = dict.fromkeys(names, 0.0)
    got_label: dict[str, Counter] = {s: Counter() for s in names}
    assignment: dict[str, str] = {}
    group_split: dict[str, str] = {}

    # largest groups first (they constrain the result most); equal sizes ordered by a seeded hash
    order = sorted(groups, key=lambda g: (-len(groups[g]), _tiebreak(seed, g)))
    for g in order:
        members = groups[g]
        lab_counts = Counter(m.label for m in members)

        def score(s: str, lab_counts: Counter = lab_counts, size: int = len(members)) -> tuple[float, float, int]:
            label_gain = sum(
                min(c, max(target_label[s][lab] - got_label[s][lab], 0.0)) for lab, c in lab_counts.items()
            )
            size_gap = target_n[s] - got_n[s] - size  # closest to its target size after adding
            return (-label_gain, abs(size_gap), names.index(s))

        best = min(names, key=score)
        group_split[g] = best
        got_n[best] += len(members)
        got_label[best].update(lab_counts)
        for m in members:
            assignment[m.id] = best

    stats: dict[str, dict[str, Any]] = {
        s: {
            "items": sum(1 for v in assignment.values() if v == s),
            "target_fraction": fractions[s],
            "actual_fraction": round(sum(1 for v in assignment.values() if v == s) / total, 4),
            "groups": sum(1 for v in group_split.values() if v == s),
            "labels": dict(sorted((str(k), v) for k, v in got_label[s].items())),
        }
        for s in names
    }
    warnings: list[str] = []
    for s in names:
        missing = sorted(str(lab) for lab in label_total if got_label[s][lab] == 0)
        if missing:
            warnings.append(f"split {s!r} contains none of: {', '.join(missing)}")
        if abs(stats[s]["actual_fraction"] - fractions[s]) > 0.1:
            warnings.append(
                f"split {s!r} holds {stats[s]['actual_fraction']:.0%} of the items instead of {fractions[s]:.0%} (few or very uneven groups)"
            )
        if stats[s]["groups"] < 3:
            warnings.append(f"split {s!r} has only {stats[s]['groups']} group(s): its metrics will be very uncertain")
    return SplitResult(
        assignment, seed, dict(fractions), manifest_checksum(assignment, seed, fractions), stats, warnings
    )


def verify_no_leakage(items: list[SplitItem], assignment: dict[str, str]) -> list[dict]:
    """Independent re-check of a finished split. Returns violations (empty list = no leakage found)."""
    out: list[dict] = []
    by_id = {i.id: i for i in items}
    missing = sorted(set(by_id) - set(assignment))
    if missing:
        out.append({"kind": "unassigned_items", "ids": missing[:10], "count": len(missing)})
    groups: dict[str, set[str]] = defaultdict(set)
    hashes: dict[str, set[str]] = defaultdict(set)
    for i in items:
        split = assignment.get(i.id)
        if split is None:
            continue
        groups[i.group].add(split)
        if i.content_sha256:
            hashes[i.content_sha256].add(split)
    for g, in_splits in groups.items():
        if len(in_splits) > 1:
            out.append({"kind": "group_in_several_splits", "group": g, "splits": sorted(in_splits)})
    for h, in_splits in hashes.items():
        if len(in_splits) > 1:
            out.append({"kind": "identical_file_in_several_splits", "sha256": h, "splits": sorted(in_splits)})
    hashed = [i for i in items if i.phash and i.id in assignment]
    near = 0
    for n, a in enumerate(hashed):
        for b in hashed[n + 1 :]:
            if assignment[a.id] != assignment[b.id] and hamming(a.phash or "", b.phash or "") <= NEAR_DUPLICATE_HAMMING:
                near += 1
                if near <= 10:
                    out.append(
                        {
                            "kind": "near_duplicate_across_splits",
                            "ids": [a.id, b.id],
                            "splits": sorted({assignment[a.id], assignment[b.id]}),
                        }
                    )
    if near > 10:
        out.append({"kind": "near_duplicate_across_splits_truncated", "count": near})
    return out
