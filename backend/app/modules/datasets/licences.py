"""Dataset licence policy and the evidence an approval needs. Pure: no database, no network.

Policy (owner decision, 2026-10-18): CC0 and CC BY are accepted PROVISIONALLY, subject to source-level verification.
CC BY-SA, CC BY-NC, CC BY-ND and unclear licences are excluded. There is deliberately no override in the application: an
exception to this policy is a decision for the owner, recorded in DECISION_LOG.md and made in code, never a button.

A licence being eligible is necessary but not sufficient. A dataset is approved only when the blockers below are empty,
i.e. when the licence of the IMAGES and of the ANNOTATIONS is each supported by evidence read at an OFFICIAL source, the
rights that matter (commercial use, redistribution, attribution) are recorded, and no evidence contradicts the declared
licence. Nothing here downloads anything; a dataset that is not approved must not be downloaded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlparse

ELIGIBLE = frozenset({"CC0-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0"})
_EXCLUDED_MARKERS = ("-SA", "-NC", "-ND")  # in SPDX ids: CC-BY-SA-4.0, CC-BY-NC-4.0, CC-BY-ND-4.0, CC-BY-NC-SA-4.0 ...
UNCLEAR = frozenset({"", "UNKNOWN", "UNCLEAR", "OTHER", "NOASSERTION", "NONE", "CUSTOM", "SEE-LICENSE"})
IMAGE_ORIGINS_OK = frozenset({"publisher_created", "third_party_licensed"})
EVIDENCE_KINDS = ("licence_page", "readme", "paper", "repository", "archive_record", "data_card", "other")
EVIDENCE_SCOPES = ("images", "annotations", "both")
MAX_EXCERPT = 600


class Verdict(StrEnum):
    ELIGIBLE = "eligible"  # may be approved if the evidence requirements are met
    EXCLUDED = "excluded"  # policy forbids it
    NEEDS_REVIEW = "needs_review"  # a real licence the policy does not cover: cannot be approved in the application


@dataclass(frozen=True)
class LicenceVerdict:
    spdx: str
    verdict: Verdict
    reason: str


def normalise(spdx: str | None) -> str:
    """Canonical form for comparison: trimmed, upper-case 'CC' prefix kept as SPDX writes it (CC-BY-4.0, CC0-1.0)."""
    s = (spdx or "").strip()
    s = re.sub(r"\s+", "-", s)
    return s.upper()


def classify(spdx: str | None) -> LicenceVerdict:
    raw = (spdx or "").strip()
    s = normalise(raw)
    if s in UNCLEAR:
        return LicenceVerdict(raw, Verdict.EXCLUDED, "licence is missing or unclear")
    if s in {x.upper() for x in ELIGIBLE}:
        return LicenceVerdict(s, Verdict.ELIGIBLE, "CC0 and CC BY are accepted provisionally, subject to verification")
    if s.startswith("CC-BY") or s.startswith("CC0") or s.startswith("CC-"):
        if any(m in s for m in _EXCLUDED_MARKERS):
            return LicenceVerdict(
                s, Verdict.EXCLUDED, "share-alike, non-commercial and no-derivatives licences are excluded"
            )
        return LicenceVerdict(s, Verdict.EXCLUDED, "unrecognised Creative Commons variant")
    return LicenceVerdict(s, Verdict.NEEDS_REVIEW, "not covered by the policy; the application cannot approve it")


@dataclass(frozen=True)
class Evidence:
    """One piece of licence evidence, as recorded (see DatasetEvidence)."""

    url: str
    kind: str
    scope: str  # images | annotations | both
    licence_spdx: str  # what this source says
    excerpt: str  # the licence statement, quoted briefly
    official: bool  # read at the dataset's own publisher/host, not a redistributor, summary or secondary article
    accessed_at: datetime | None


@dataclass(frozen=True)
class DatasetFacts:
    name: str
    version: str
    kind: str  # real | synthetic
    source_url: str
    accessed_at: datetime | None
    licence_spdx: str
    images_licence_spdx: str
    annotations_licence_spdx: str | None
    has_annotations: bool
    attribution_required: bool | None
    attribution_text: str | None
    commercial_use: str  # yes | no | unknown
    redistribution: str  # yes | no | unknown
    intended_use: str
    image_origin: str = "unknown"  # publisher_created | third_party_licensed | third_party_scraped | unknown


def is_https_url(url: str | None) -> bool:
    try:
        p = urlparse(url or "")
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.netloc) and "." in p.netloc


def approval_blockers(d: DatasetFacts, evidence: list[Evidence]) -> list[str]:
    """Everything that currently prevents approval, in plain language. Empty means the dataset may be approved."""
    out: list[str] = []
    if d.kind == "synthetic":
        return out  # synthetic fixtures are generated here, have no external licence, and are never biological data
    if not is_https_url(d.source_url):
        out.append("source URL is missing or is not an https URL")
    if d.accessed_at is None:
        out.append("access date of the source is not recorded")
    if not d.intended_use.strip():
        out.append("intended use is not recorded")

    scopes = [("dataset", d.licence_spdx), ("images", d.images_licence_spdx)]
    if d.has_annotations:
        scopes.append(("annotations", d.annotations_licence_spdx or ""))
    for scope, spdx in scopes:
        v = classify(spdx)
        if v.verdict is not Verdict.ELIGIBLE:
            out.append(f"{scope} licence {spdx or '(none)'!r}: {v.reason}")
    if not d.has_annotations and d.annotations_licence_spdx:
        out.append("annotations licence is given but the dataset is declared to have no annotations")

    if d.image_origin not in IMAGE_ORIGINS_OK:
        out.append(
            f"image origin is {d.image_origin!r}: a publisher's licence only covers images the publisher had the right "
            "to license, so images scraped from third-party sites (or of unknown origin) cannot be approved without "
            "written confirmation of the rights; record 'third_party_licensed' only when the publisher documents it"
        )

    if d.commercial_use != "yes":
        out.append(f"commercial use is {d.commercial_use!r}; it must be confirmed as 'yes' from the licence text")
    if d.redistribution not in ("yes", "no"):
        out.append("redistribution rights are not recorded")
    if d.attribution_required is None:
        out.append("whether attribution is required is not recorded")
    elif d.attribution_required and not (d.attribution_text or "").strip():
        out.append("attribution is required but the attribution text is not recorded")

    if not evidence:
        out.append("no licence evidence is recorded")
        return out
    needed = ["images"] + (["annotations"] if d.has_annotations else [])
    for scope in needed:
        official = [e for e in evidence if e.official and e.scope in (scope, "both") and e.excerpt.strip()]
        if not official:
            out.append(f"no official-source evidence with a quoted licence statement covers the {scope}")
    declared = {"images": normalise(d.images_licence_spdx), "annotations": normalise(d.annotations_licence_spdx)}
    for e in evidence:
        if not is_https_url(e.url):
            out.append(f"evidence {e.url!r} is not an https URL")
        if e.accessed_at is None:
            out.append(f"evidence {e.url!r} has no access date")
        for scope in ("images", "annotations"):
            if e.scope in (scope, "both") and (scope == "images" or d.has_annotations):
                if normalise(e.licence_spdx) != declared[scope]:
                    out.append(
                        f"evidence {e.url!r} states {e.licence_spdx!r} for the {scope}, which contradicts the declared "
                        f"{declared[scope] or '(none)'!r}"
                    )
    return sorted(set(out))
