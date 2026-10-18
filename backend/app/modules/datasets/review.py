"""Label review state machine. Pure.

    unreviewed -> under_review -> accepted | rejected | corrected
    accepted | rejected | corrected -> under_review      (a decision can be re-opened; the history keeps the old one)
    under_review -> unreviewed                            (release a claim without deciding)

Every decision needs written evidence (what the reviewer looked at). `corrected` needs a new label that differs from
the old one. The reviewer is always the authenticated user; this module never takes a name from a request. Nothing here
or in the database can verify that a reviewer is qualified: the record says who decided, not that they are an expert.
"""

from __future__ import annotations

STATUSES = ("unreviewed", "under_review", "accepted", "rejected", "corrected")
DECISIONS = {"accepted", "rejected", "corrected"}
ALLOWED: dict[str, set[str]] = {
    "unreviewed": {"under_review"},
    "under_review": {"unreviewed", *DECISIONS},
    "accepted": {"under_review"},
    "rejected": {"under_review"},
    "corrected": {"under_review"},
}
MIN_EVIDENCE = 10


def check(
    from_status: str, to_status: str, from_label: str | None, to_label: str | None, evidence: str | None
) -> str | None:
    """None when the change is allowed, otherwise the reason it is not."""
    if to_status not in STATUSES:
        return f"unknown status {to_status!r}"
    if to_status not in ALLOWED.get(from_status, set()):
        allowed = ", ".join(sorted(ALLOWED.get(from_status, set()))) or "none"
        return f"a label that is {from_status} can only move to: {allowed}"
    if to_status in DECISIONS and len((evidence or "").strip()) < MIN_EVIDENCE:
        return f"a decision needs written evidence of at least {MIN_EVIDENCE} characters (what was checked, and against what)"
    if to_status == "accepted" and not from_label:
        return "there is no label to accept"
    if to_status == "corrected":
        if not (to_label or "").strip():
            return "a correction needs the new label"
        if to_label == from_label:
            return "the new label equals the old one; accept it instead"
    if to_status != "corrected" and to_label not in (None, "", from_label):
        return "a new label is only allowed when correcting"
    return None
