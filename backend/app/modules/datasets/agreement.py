"""Inter-reviewer agreement on labels. Pure.

When two different people independently decide the same sample, how often do they agree beyond chance? Cohen's kappa
answers that. It is computed from the append-only review history: for each sample, each reviewer's LATEST decision is
their verdict (`accepted` = the label as it stood, `corrected` = their new label, `rejected` = a separate category).
Samples with verdicts from at least two reviewers contribute one pair (the two earliest reviewers, so adding a third
reviewer later never changes an existing pair).

Caveats the report states: agreement measures consistency, not correctness (two people can agree and both be wrong);
reviewers here are not verified as qualified; and with few pairs kappa is very uncertain.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

REJECTED = "(rejected)"
MIN_PAIRS_FOR_KAPPA = 2


@dataclass(frozen=True)
class Decision:
    sample_id: str
    reviewer_id: str
    status: str  # accepted | rejected | corrected
    label_before: str | None
    label_after: str | None
    at: datetime


def verdict(d: Decision) -> str | None:
    if d.status == "accepted":
        return d.label_before
    if d.status == "corrected":
        return d.label_after
    if d.status == "rejected":
        return REJECTED
    return None


def cohens_kappa(a: list[str], b: list[str]) -> float | None:
    """Kappa for two raters over the same items; None when it is undefined (no items, or chance agreement is 1)."""
    if len(a) != len(b):
        raise ValueError("both raters must rate the same items")
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def agreement_report(decisions: list[Decision]) -> dict[str, Any]:
    latest: dict[tuple[str, str], Decision] = {}
    for d in sorted(decisions, key=lambda x: (x.at, x.reviewer_id)):
        if d.status in ("accepted", "rejected", "corrected"):
            latest[(d.sample_id, d.reviewer_id)] = d  # later decisions replace earlier ones by the same reviewer
    per_sample: dict[str, list[Decision]] = {}
    for d in latest.values():
        per_sample.setdefault(d.sample_id, []).append(d)
    pairs: list[tuple[str, str]] = []
    disagreements: list[dict[str, Any]] = []
    for sample_id, ds in per_sample.items():
        if len(ds) < 2:
            continue
        first, second = sorted(ds, key=lambda x: (x.at, x.reviewer_id))[:2]
        va, vb = verdict(first), verdict(second)
        if va is None or vb is None:
            continue
        pairs.append((va, vb))
        if va != vb:
            disagreements.append({"sample_id": sample_id, "verdicts": [va, vb]})
    n = len(pairs)
    observed = sum(x == y for x, y in pairs) / n if n else None
    kappa = cohens_kappa([x for x, _ in pairs], [y for _, y in pairs]) if n >= MIN_PAIRS_FOR_KAPPA else None
    return {
        "samples_with_a_decision": len(per_sample),
        "samples_with_two_reviewers": n,
        "reviewers": len({r for (_, r) in latest}),
        "observed_agreement": round(observed, 4) if observed is not None else None,
        "cohens_kappa": round(kappa, 4) if kappa is not None else None,
        "disagreements": disagreements[:50],
        "caveats": [
            "agreement measures consistency, not correctness: two reviewers can agree and both be wrong",
            "reviewers are not verified as qualified",
            *(
                [f"fewer than {MIN_PAIRS_FOR_KAPPA} doubly-reviewed samples: kappa is not computed"]
                if n < MIN_PAIRS_FOR_KAPPA
                else []
            ),
            *(["few doubly-reviewed samples: kappa is very uncertain"] if MIN_PAIRS_FOR_KAPPA <= n < 30 else []),
        ],
    }
