from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import SmallDict, StrictModel

Tri = Literal["yes", "no", "unknown"]


class DatasetCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    kind: Literal["real", "synthetic"] = "real"
    source_url: str = Field(min_length=1, max_length=500)
    accessed_at: datetime | None = None
    licence_spdx: str = Field(min_length=1, max_length=60)
    images_licence_spdx: str | None = Field(default=None, max_length=60)  # defaults to the dataset licence
    annotations_licence_spdx: str | None = Field(default=None, max_length=60)
    has_annotations: bool = False
    image_origin: Literal["publisher_created", "third_party_licensed", "third_party_scraped", "unknown"] = "unknown"
    attribution_required: bool | None = None
    attribution_text: str | None = Field(default=None, max_length=2000)
    commercial_use: Tri = "unknown"
    redistribution: Tri = "unknown"
    intended_use: str = Field(default="", max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


class EvidenceCreate(StrictModel):
    url: str = Field(min_length=1, max_length=500)
    kind: Literal["licence_page", "readme", "paper", "repository", "archive_record", "data_card", "other"]
    scope: Literal["images", "annotations", "both"]
    licence_spdx: str = Field(min_length=1, max_length=60)
    excerpt: str = Field(min_length=10, max_length=600)
    official: bool
    accessed_at: datetime


class DatasetTransition(StrictModel):
    to_status: Literal["under_review", "approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    kind: str
    scope: str
    licence_spdx: str
    excerpt: str
    official: bool
    accessed_at: datetime
    recorded_by: uuid.UUID | None
    recorded_at: datetime


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: str | None
    to_status: str
    actor_id: uuid.UUID | None
    note: str | None
    blockers: list[str]
    at: datetime


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    kind: str
    source_url: str
    accessed_at: datetime | None
    licence_spdx: str
    images_licence_spdx: str
    annotations_licence_spdx: str | None
    has_annotations: bool
    image_origin: str
    attribution_required: bool | None
    attribution_text: str | None
    commercial_use: str
    redistribution: str
    intended_use: str
    notes: str | None
    status: str
    created_by: uuid.UUID | None
    created_at: datetime
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    # computed
    licence_verdict: str = ""
    blockers: list[str] = []
    download_allowed: bool = False
    is_biological_data: bool = True


class DatasetDetail(DatasetOut):
    evidence: list[EvidenceOut]
    history: list[StatusHistoryOut]
    sample_count: int = 0


class SampleIn(StrictModel):
    external_id: str = Field(min_length=1, max_length=300)
    group_key: str | None = Field(default=None, max_length=200)
    label: str | None = Field(default=None, max_length=120)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    phash: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    file_status: Literal["ok", "invalid"] | None = None
    width: int | None = Field(default=None, gt=0, le=100_000)
    height: int | None = Field(default=None, gt=0, le=100_000)
    provenance: SmallDict = Field(default_factory=dict)


class SamplesCreate(StrictModel):
    samples: list[SampleIn] = Field(min_length=1, max_length=500)


class SampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_id: str
    group_key: str | None
    label: str | None
    label_status: str
    content_sha256: str | None
    phash: str | None
    file_status: str | None
    width: int | None
    height: int | None
    provenance: dict
    is_synthetic: bool
    version: int


class ReviewIn(StrictModel):
    """The reviewer is the signed-in user: there is deliberately no field for a name."""

    to_status: Literal["unreviewed", "under_review", "accepted", "rejected", "corrected"]
    to_label: str | None = Field(default=None, max_length=120)
    evidence: str | None = Field(default=None, max_length=4000)
    reviewer_qualification: str | None = Field(default=None, max_length=300)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sample_id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_qualification: str | None
    qualification_verified: bool = False  # always false: the application cannot verify a qualification
    from_status: str
    to_status: str
    from_label: str | None
    to_label: str | None
    evidence: str | None
    at: datetime


class SplitCreate(StrictModel):
    fractions: dict[str, float] = Field(default_factory=lambda: {"train": 0.7, "validation": 0.15, "test": 0.15})
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    include_unreviewed: bool = False


class SplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    seed: int
    fractions: dict
    include_unreviewed: bool
    manifest_sha256: str
    stats: dict
    warnings: list
    leakage_violations: list
    created_by: uuid.UUID | None
    created_at: datetime


class SplitDetail(SplitOut):
    manifest: dict


class ReviewQueueSummary(BaseModel):
    by_status: dict[str, int]
    reviewed_fraction: float
    qualified_reviewers_verified: int = 0
    note: str = (
        "Reviews record who decided and on what evidence. The application does not verify that a reviewer is "
        "qualified, so no label here is described as expert-validated."
    )
