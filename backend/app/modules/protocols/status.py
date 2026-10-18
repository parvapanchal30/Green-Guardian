"""Protocol approval state, computed from the sign-offs. Pure.

States: `awaiting_signoffs` (a required role has not signed), `rejected` (a required role's latest decision is reject),
`invalid_signoffs` (one person signed for several roles: the roles must be independent), `awaiting_qualification_verification`
(everyone approved, but at least one signer's qualification is unverified) and `approved`, which requires every signer's
qualification to be VERIFIED. The application has no mechanism to verify a qualification, so `approved` cannot be reached
today. A newer version of the same protocol makes this one `superseded`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .content import REQUIRED_ROLES


@dataclass(frozen=True)
class Signoff:
    role: str
    decision: str  # approve | reject
    signer_id: str
    declared_qualification: str | None
    qualification_verified: bool
    at: datetime


def compute_status(required: list[str], signoffs: list[Signoff], *, superseded: bool = False) -> dict[str, Any]:
    latest: dict[str, Signoff] = {}
    for s in sorted(signoffs, key=lambda x: x.at):
        latest[s.role] = s
    blockers: list[str] = []
    roles = [r for r in REQUIRED_ROLES if r in required]
    state = "approved"

    if superseded:
        return {
            "state": "superseded",
            "blockers": ["a newer version of this protocol exists"],
            "signed_roles": sorted(latest),
        }
    rejected = [r for r in roles if r in latest and latest[r].decision == "reject"]
    if rejected:
        state = "rejected"
        blockers.append(f"rejected by: {', '.join(rejected)}")
    missing = [r for r in roles if r not in latest]
    if missing:
        state = state if state == "rejected" else "awaiting_signoffs"
        blockers.append(f"awaiting sign-off from: {', '.join(missing)}")
    signers = [latest[r].signer_id for r in roles if r in latest]
    if len(set(signers)) < len(signers):
        state = "invalid_signoffs" if state not in ("rejected",) else state
        blockers.append("one person signed for more than one role; each required role needs a different person")
    if state == "approved":
        unverified = [r for r in roles if not latest[r].qualification_verified]
        if unverified:
            state = "awaiting_qualification_verification"
            blockers.append(
                "qualifications are not verified for: "
                + ", ".join(unverified)
                + ". The application records the qualification a signer declares but cannot verify it, so this protocol cannot be approved yet"
            )
    return {"state": state, "blockers": blockers, "signed_roles": sorted(latest)}
