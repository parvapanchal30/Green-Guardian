from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfoNotFoundError  # noqa: F401  (validated in validator below)

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import Role, WorkspaceMode


def _check_tz(v: str) -> str:
    from zoneinfo import ZoneInfo

    try:
        ZoneInfo(v)
    except Exception as e:  # noqa: BLE001 - ZoneInfo raises several types
        raise ValueError("Unknown IANA timezone") from e
    return v


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: WorkspaceMode
    timezone: str = "UTC"

    _tz = field_validator("timezone")(_check_tz)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    settings: dict | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        return _check_tz(v) if v is not None else v


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    mode: WorkspaceMode
    timezone: str
    settings: dict
    created_at: datetime


class WorkspaceWithRole(WorkspaceOut):
    role: Role


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: str
    role: Role


class MemberAdd(BaseModel):
    email: EmailStr
    role: Role = Role.WORKER


class MemberRoleUpdate(BaseModel):
    role: Role


class CapabilityOut(BaseModel):
    key: str
    label: str
    technique: str
    stage: str  # mvp | v2 | v3 | v4
    available: bool
    reason: str | None = None
