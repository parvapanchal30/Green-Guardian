from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import StrictModel

from .content import ProtocolContent


class ProtocolCreate(StrictModel):
    key: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    content: ProtocolContent


class SignoffCreate(StrictModel):
    """The signer is the signed-in user; there is no field for a name. The qualification is only what they declare."""

    role: Literal["plant_pathologist", "data_owner", "independent_evaluator"]
    decision: Literal["approve", "reject"]
    declared_qualification: str | None = Field(default=None, max_length=300)
    note: str = Field(min_length=10, max_length=2000)


class SignoffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    decision: str
    signer_id: uuid.UUID
    declared_qualification: str | None
    qualification_verified: bool
    note: str
    at: datetime


class StatusOut(BaseModel):
    state: str
    blockers: list[str]
    signed_roles: list[str]


class ProtocolSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    version: int
    title: str
    content_sha256: str
    created_by: uuid.UUID | None
    created_at: datetime
    status: StatusOut
    is_proposal_only: bool = True


class ProtocolDetail(ProtocolSummary):
    content: dict[str, Any]
    signoffs: list[SignoffOut]
