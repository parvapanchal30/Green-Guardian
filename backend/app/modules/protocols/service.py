from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.pagination import Page, PageParams
from app.modules.audit import service as audit
from app.modules.workspaces.models import Role

from . import content as content_mod
from . import status as status_mod
from .models import EvaluationProtocol, ProtocolSignoff
from .schemas import ProtocolCreate, ProtocolDetail, ProtocolSummary, SignoffCreate, SignoffOut, StatusOut


def _signoffs(db: Session, workspace_id: uuid.UUID, protocol_id: uuid.UUID) -> list[ProtocolSignoff]:
    return list(
        db.scalars(
            select(ProtocolSignoff)
            .where(ProtocolSignoff.workspace_id == workspace_id, ProtocolSignoff.protocol_id == protocol_id)
            .order_by(ProtocolSignoff.at, ProtocolSignoff.id)
        )
    )


def _latest_version(db: Session, workspace_id: uuid.UUID, key: str) -> int:
    return (
        db.scalar(
            select(func.max(EvaluationProtocol.version)).where(
                EvaluationProtocol.workspace_id == workspace_id, EvaluationProtocol.key == key
            )
        )
        or 0
    )


def compute(db: Session, p: EvaluationProtocol) -> StatusOut:
    rows = _signoffs(db, p.workspace_id, p.id)
    sign = [
        status_mod.Signoff(
            r.role, r.decision, str(r.signer_id), r.declared_qualification, r.qualification_verified, r.at
        )
        for r in rows
    ]
    superseded = _latest_version(db, p.workspace_id, p.key) > p.version
    return StatusOut(
        **status_mod.compute_status(list(p.content.get("required_signoffs", [])), sign, superseded=superseded)
    )


def summary(db: Session, p: EvaluationProtocol) -> ProtocolSummary:
    return ProtocolSummary(
        id=p.id, key=p.key, version=p.version, title=p.title, content_sha256=p.content_sha256, created_by=p.created_by,
        created_at=p.created_at, status=compute(db, p),
    )  # fmt: skip


def detail(db: Session, ctx: WorkspaceContext, p: EvaluationProtocol) -> ProtocolDetail:
    base = summary(db, p)
    return ProtocolDetail(
        **base.model_dump(),
        content=p.content,
        signoffs=[SignoffOut.model_validate(s) for s in _signoffs(db, ctx.workspace_id, p.id)],
    )


def get_protocol(db: Session, ctx: WorkspaceContext, protocol_id: uuid.UUID) -> EvaluationProtocol:
    p = db.scalar(
        select(EvaluationProtocol).where(
            EvaluationProtocol.id == protocol_id, EvaluationProtocol.workspace_id == ctx.workspace_id
        )
    )
    if p is None:
        raise NotFound("Protocol not found", code="protocol_not_found")
    return p


def get_detail(db: Session, ctx: WorkspaceContext, protocol_id: uuid.UUID) -> ProtocolDetail:
    return detail(db, ctx, get_protocol(db, ctx, protocol_id))


def list_protocols(db: Session, ctx: WorkspaceContext, page: PageParams) -> Page[ProtocolSummary]:
    q = select(EvaluationProtocol).where(EvaluationProtocol.workspace_id == ctx.workspace_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(EvaluationProtocol.created_at.desc(), EvaluationProtocol.id).limit(page.limit).offset(page.offset)
    )
    return Page(items=[summary(db, p) for p in rows], total=total, limit=page.limit, offset=page.offset)


def create(db: Session, ctx: WorkspaceContext, data: ProtocolCreate) -> ProtocolDetail:
    body = data.content.model_dump(mode="json")
    version = _latest_version(db, ctx.workspace_id, data.key) + 1
    p = EvaluationProtocol(
        workspace_id=ctx.workspace_id, key=data.key, version=version, title=data.content.title, content=body,
        content_sha256=content_mod.content_sha256(body), created_by=ctx.user.id,
    )  # fmt: skip
    try:
        with db.begin_nested():
            db.add(p)
            db.flush()
    except IntegrityError as exc:  # two people created the same next version at once
        raise Conflict(
            "another version was created at the same time; try again", code="protocol_version_conflict"
        ) from exc
    audit.record_ctx(
        db,
        ctx,
        "protocol.create",
        target_type="evaluation_protocol",
        target_id=p.id,
        details={"key": p.key, "version": version},
    )
    db.commit()
    return detail(db, ctx, p)


def sign(db: Session, ctx: WorkspaceContext, protocol_id: uuid.UUID, data: SignoffCreate) -> ProtocolDetail:
    p = get_protocol(db, ctx, protocol_id)
    if _latest_version(db, ctx.workspace_id, p.key) > p.version:
        raise Conflict("this version has been superseded; sign the newest version", code="protocol_superseded")
    if data.role not in p.content.get("required_signoffs", []):
        raise Conflict("this protocol does not require that role", code="role_not_required")
    if data.role == "data_owner" and not ctx.has_role(Role.OWNER):
        raise Forbidden("only the workspace owner can sign as the data owner")
    if data.role != "data_owner" and not (data.declared_qualification or "").strip():
        raise Conflict(
            "state the qualification you are signing under; it is recorded as declared and is not verified",
            code="qualification_required",
        )
    db.add(
        ProtocolSignoff(
            workspace_id=ctx.workspace_id,
            protocol_id=p.id,
            role=data.role,
            decision=data.decision,
            signer_id=ctx.user.id,
            declared_qualification=data.declared_qualification,
            qualification_verified=False,
            note=data.note,
        )  # fmt: skip
    )
    audit.record_ctx(
        db,
        ctx,
        "protocol.signoff",
        target_type="evaluation_protocol",
        target_id=p.id,
        details={"role": data.role, "decision": data.decision, "version": p.version},
    )
    db.commit()
    return detail(db, ctx, p)


def has_approved_protocol(db: Session, workspace_id: uuid.UUID) -> bool:
    """Used by the dataset claim gate. True only for a protocol whose computed state is `approved`, which requires
    verified qualifications that the application cannot establish today."""
    rows = db.scalars(select(EvaluationProtocol).where(EvaluationProtocol.workspace_id == workspace_id))
    return any(compute(db, p).state == "approved" for p in rows)


def template() -> dict[str, Any]:
    return {
        "content": content_mod.template(),
        "note": "A proposal from docs/EVALUATION_PROTOCOL.md. It is not approved; copy it to create a protocol version, then collect sign-offs.",
        "required_roles": list(content_mod.REQUIRED_ROLES),
    }
