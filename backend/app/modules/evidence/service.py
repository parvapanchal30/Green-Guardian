"""Evidence upload, validation, retrieval and removal.

Validation order (cheapest first, nothing is stored until all pass):
  1. size cap (read at most max+1 bytes)
  2. magic-byte sniff: the *bytes* decide the type; the client's Content-Type and filename are ignored
  3. Pillow header check: dimensions and the decompression-bomb guard
  4. full decode: catches truncated or corrupt files
  5. link checks: asset/observation/issue must belong to this workspace and to the same asset

Write order: blob first, then the row. If the row fails the blob is removed; if the blob fails nothing is written.
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from typing import BinaryIO

import structlog
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import WorkspaceContext
from app.core.errors import (
    Forbidden,
    NotFound,
    PayloadTooLarge,
    ProviderUnavailable,
    Unprocessable,
    UnsupportedMediaType,
)
from app.core.ids import uuid7
from app.core.pagination import Page, PageParams
from app.core.timeutil import utcnow
from app.modules.assets.service import get_asset
from app.modules.issues.service import get_issue
from app.modules.observations.service import get_observation
from app.modules.workspaces.models import Role

from .models import Evidence
from .schemas import EvidenceOut
from .storage import ObjectNotFound, ObjectStore, StorageError

log = structlog.get_logger()

# Pillow format -> (content type, extension). Only these are accepted.
FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}


def sniff(data: bytes) -> str | None:
    """Image format from the leading bytes, or None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def read_limited(fh: BinaryIO, limit: int) -> bytes:
    data = fh.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(f"File exceeds the {limit // (1024 * 1024)} MB limit", code="file_too_large")
    if not data:
        raise Unprocessable("The file is empty", code="empty_file")
    return data


def validate_image(data: bytes, settings: Settings) -> tuple[str, str, int, int]:
    """Return (content_type, extension, width, height) or raise a 4xx error."""
    fmt = sniff(data)
    if fmt is None:
        raise UnsupportedMediaType("Only JPEG, PNG and WebP images are accepted", code="unsupported_image_type")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size  # header only, nothing decoded yet
            if probe.format != fmt:
                raise UnsupportedMediaType(
                    "File content does not match its image format", code="unsupported_image_type"
                )
            if width * height > settings.storage_max_pixels:
                raise Unprocessable(
                    f"Image is {width}x{height}; the limit is {settings.storage_max_pixels:,} pixels",
                    code="image_too_large",
                )
        with Image.open(io.BytesIO(data)) as full:
            full.load()  # raises on truncated or corrupt data
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise Unprocessable("The image is corrupt or cannot be decoded", code="corrupt_image") from exc
    content_type, ext = FORMATS[fmt]
    return content_type, ext, width, height


_FILENAME_JUNK = re.compile(r"[^\w.\- ]+")


def clean_filename(name: str | None) -> str | None:
    """Display name only: path parts and odd characters removed."""
    if not name:
        return None
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = _FILENAME_JUNK.sub("_", base).strip()
    return base[:255] or None


def to_out(ev: Evidence) -> EvidenceOut:
    return EvidenceOut(
        id=ev.id,
        asset_id=ev.asset_id,
        observation_id=ev.observation_id,
        issue_id=ev.issue_id,
        uploaded_by=ev.uploaded_by,
        original_filename=ev.original_filename,
        content_type=ev.content_type,
        size_bytes=ev.size_bytes,
        sha256=ev.sha256,
        width=ev.width,
        height=ev.height,
        caption=ev.caption,
        created_at=ev.created_at,
        content_path=f"/workspaces/{ev.workspace_id}/evidence/{ev.id}/content",
    )


def upload(
    db: Session,
    ctx: WorkspaceContext,
    store: ObjectStore,
    settings: Settings,
    *,
    asset_id: uuid.UUID,
    fh: BinaryIO,
    filename: str | None,
    caption: str | None,
    observation_id: uuid.UUID | None,
    issue_id: uuid.UUID | None,
) -> EvidenceOut:
    # Authorisation-sensitive lookups first, so a caller outside the workspace learns nothing from the file checks.
    asset = get_asset(db, ctx, asset_id)
    if observation_id is not None and get_observation(db, ctx, observation_id).asset_id != asset.id:
        raise Unprocessable("The observation belongs to a different asset", code="evidence_link_mismatch")
    if issue_id is not None and get_issue(db, ctx, issue_id).asset_id != asset.id:
        raise Unprocessable("The issue belongs to a different asset", code="evidence_link_mismatch")
    caption = (caption or "").strip() or None
    if caption and len(caption) > 500:
        raise Unprocessable("Caption is limited to 500 characters", code="caption_too_long")

    data = read_limited(fh, settings.storage_max_bytes)
    content_type, ext, width, height = validate_image(data, settings)

    evidence_id = uuid7()
    key = f"{ctx.workspace_id}/{asset.id}/{evidence_id}.{ext}"
    try:
        store.put(key, data, content_type)
    except StorageError as exc:
        log.error("evidence_store_put_failed", key=key, error=str(exc))
        raise ProviderUnavailable(
            "Image storage is unavailable; nothing was saved", code="storage_unavailable"
        ) from exc

    try:
        ev = Evidence(
            id=evidence_id,
            workspace_id=ctx.workspace_id,
            asset_id=asset.id,
            observation_id=observation_id,
            issue_id=issue_id,
            uploaded_by=ctx.user.id,
            storage_key=key,
            original_filename=clean_filename(filename),
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            width=width,
            height=height,
            caption=caption,
        )
        db.add(ev)
        db.flush()
        db.commit()
    except BaseException:
        db.rollback()
        try:
            store.delete(key)  # compensate: never leave an orphan blob behind a failed row
        except StorageError as exc:
            log.error("evidence_orphan_blob", key=key, error=str(exc))
        raise
    return to_out(ev)


def get_evidence(db: Session, ctx: WorkspaceContext, evidence_id: uuid.UUID) -> Evidence:
    ev = db.scalar(
        select(Evidence).where(
            Evidence.id == evidence_id, Evidence.workspace_id == ctx.workspace_id, Evidence.deleted_at.is_(None)
        )
    )
    if ev is None:
        raise NotFound("Evidence not found", code="evidence_not_found")
    return ev


def list_evidence(
    db: Session,
    ctx: WorkspaceContext,
    page: PageParams,
    *,
    asset_id: uuid.UUID | None,
    observation_id: uuid.UUID | None,
    issue_id: uuid.UUID | None,
) -> Page[EvidenceOut]:
    conds = [Evidence.workspace_id == ctx.workspace_id, Evidence.deleted_at.is_(None)]
    if asset_id:
        conds.append(Evidence.asset_id == asset_id)
    if observation_id:
        conds.append(Evidence.observation_id == observation_id)
    if issue_id:
        conds.append(Evidence.issue_id == issue_id)
    total = db.scalar(select(func.count()).select_from(Evidence).where(*conds)) or 0
    rows = db.scalars(
        select(Evidence)
        .where(*conds)
        .order_by(Evidence.created_at.desc(), Evidence.id.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page[EvidenceOut](items=[to_out(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


def read_content(
    db: Session, ctx: WorkspaceContext, store: ObjectStore, evidence_id: uuid.UUID
) -> tuple[Evidence, bytes]:
    ev = get_evidence(db, ctx, evidence_id)
    try:
        return ev, store.get(ev.storage_key)
    except ObjectNotFound:
        log.error("evidence_blob_missing", evidence_id=str(ev.id), key=ev.storage_key)
        raise NotFound("The stored image is missing", code="evidence_blob_missing") from None
    except StorageError as exc:
        log.error("evidence_store_get_failed", evidence_id=str(ev.id), error=str(exc))
        raise ProviderUnavailable("Image storage is unavailable", code="storage_unavailable") from exc


def delete_evidence(db: Session, ctx: WorkspaceContext, evidence_id: uuid.UUID) -> None:
    """Soft delete: hidden from every read; the blob is retained until a purge job removes it."""
    ev = get_evidence(db, ctx, evidence_id)
    if not (ctx.has_role(Role.MANAGER) or ev.uploaded_by == ctx.user.id):
        raise Forbidden("Only a manager or the uploader can remove evidence", code="insufficient_role")
    ev.deleted_at = utcnow()
    ev.deleted_by = ctx.user.id
    db.commit()
