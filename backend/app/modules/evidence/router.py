from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.deps import WorkspaceContext, viewer_ctx, worker_ctx
from app.core.pagination import Page, PageParams, page_params

from . import service
from .schemas import EvidenceOut
from .storage import ObjectStore, get_object_store

router = APIRouter(prefix="/workspaces/{ws}/evidence", tags=["evidence"])


@router.post("", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
def upload_evidence(
    asset_id: uuid.UUID = Form(),
    file: UploadFile = File(),
    caption: str | None = Form(default=None),
    observation_id: uuid.UUID | None = Form(default=None),
    issue_id: uuid.UUID | None = Form(default=None),
    ctx: WorkspaceContext = Depends(worker_ctx),
    db: Session = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings),
):
    """Upload a JPEG, PNG or WebP photo for an asset (multipart). The type is decided from the bytes, not the
    client's headers. Optionally link it to an observation and/or issue of the same asset."""
    return service.upload(
        db,
        ctx,
        store,
        settings,
        asset_id=asset_id,
        fh=file.file,
        filename=file.filename,
        caption=caption,
        observation_id=observation_id,
        issue_id=issue_id,
    )


@router.get("", response_model=Page[EvidenceOut])
def list_evidence(
    asset_id: uuid.UUID | None = None,
    observation_id: uuid.UUID | None = None,
    issue_id: uuid.UUID | None = None,
    page: PageParams = Depends(page_params),
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
):
    return service.list_evidence(db, ctx, page, asset_id=asset_id, observation_id=observation_id, issue_id=issue_id)


@router.get("/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: uuid.UUID, ctx: WorkspaceContext = Depends(viewer_ctx), db: Session = Depends(get_db)):
    return service.to_out(service.get_evidence(db, ctx, evidence_id))


@router.get("/{evidence_id}/content")
def get_evidence_content(
    evidence_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(viewer_ctx),
    db: Session = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
):
    """The image bytes. Authenticated like every other route (fetch it with the bearer token, then use a blob URL)."""
    ev, data = service.read_content(db, ctx, store, evidence_id)
    return Response(
        content=data,
        media_type=ev.content_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{ev.sha256}"',
            "Content-Disposition": "inline",
        },
    )


@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(evidence_id: uuid.UUID, ctx: WorkspaceContext = Depends(worker_ctx), db: Session = Depends(get_db)):
    service.delete_evidence(db, ctx, evidence_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
