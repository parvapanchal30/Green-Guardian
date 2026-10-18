"""Dataset catalog, licence approval, label review, quality, splits and claim readiness. Every query is filtered by the
workspace of the caller. Nothing here downloads, trains or evaluates a model."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.pagination import Page, PageParams
from app.core.timeutil import utcnow
from app.modules.audit import service as audit
from app.modules.workspaces.models import Role

from . import agreement, evaluation, licences, quality, review, splits
from .models import Dataset, DatasetEvidence, DatasetSample, DatasetSplit, DatasetStatusHistory, LabelReview
from .schemas import (
    DatasetCreate,
    DatasetDetail,
    DatasetOut,
    DatasetTransition,
    EvidenceCreate,
    EvidenceOut,
    ReviewIn,
    ReviewOut,
    ReviewQueueSummary,
    SampleOut,
    SamplesCreate,
    SplitCreate,
    SplitDetail,
    SplitOut,
    StatusHistoryOut,
)

DATASET_TRANSITIONS = {
    "proposed": {"under_review", "rejected"},
    "under_review": {"approved", "rejected"},
    "approved": {"under_review", "rejected"},
    "rejected": set(),  # terminal: a corrected description is a new version
}
MAX_SAMPLES_FOR_ANALYSIS = 20_000


# ------------------------------------------------------------------------------------------------ helpers
def facts(d: Dataset) -> licences.DatasetFacts:
    return licences.DatasetFacts(
        d.name, d.version, d.kind, d.source_url, d.accessed_at, d.licence_spdx, d.images_licence_spdx,
        d.annotations_licence_spdx, d.has_annotations, d.attribution_required, d.attribution_text,
        d.commercial_use, d.redistribution, d.intended_use, d.image_origin,
    )  # fmt: skip


def evidence_of(db: Session, d: Dataset) -> list[DatasetEvidence]:
    return list(
        db.scalars(
            select(DatasetEvidence)
            .where(DatasetEvidence.workspace_id == d.workspace_id, DatasetEvidence.dataset_id == d.id)
            .order_by(DatasetEvidence.recorded_at, DatasetEvidence.id)
        )
    )


def blockers_for(db: Session, d: Dataset) -> list[str]:
    ev = [
        licences.Evidence(e.url, e.kind, e.scope, e.licence_spdx, e.excerpt, e.official, e.accessed_at)
        for e in evidence_of(db, d)
    ]
    return licences.approval_blockers(facts(d), ev)


def to_out(db: Session, d: Dataset) -> DatasetOut:
    out = DatasetOut.model_validate(d)
    out.licence_verdict = licences.classify(d.licence_spdx).verdict.value if d.kind == "real" else "not_applicable"
    out.blockers = blockers_for(db, d) if d.status != "approved" else []
    out.download_allowed = d.status == "approved" and d.kind == "real"
    out.is_biological_data = d.kind == "real"
    return out


def get_dataset(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, *, lock: bool = False) -> Dataset:
    q = select(Dataset).where(Dataset.id == dataset_id, Dataset.workspace_id == ctx.workspace_id)
    if lock:
        q = q.with_for_update()
    d = db.scalar(q)
    if d is None:
        raise NotFound("Dataset not found", code="dataset_not_found")
    return d


def _history(
    db: Session, ctx: WorkspaceContext, d: Dataset, frm: str | None, to: str, note: str | None, blockers: list[str]
) -> None:
    db.add(
        DatasetStatusHistory(
            workspace_id=ctx.workspace_id,
            dataset_id=d.id,
            from_status=frm,
            to_status=to,
            actor_id=ctx.user.id,
            note=note,
            blockers=blockers,
        )  # fmt: skip
    )


# ------------------------------------------------------------------------------------------------ catalog
def licence_policy() -> dict[str, Any]:
    return {
        "eligible": sorted(licences.ELIGIBLE),
        "excluded": [
            "CC BY-SA (any version)",
            "CC BY-NC (any version)",
            "CC BY-ND (any version)",
            "unclear, missing or custom licences",
        ],
        "not_covered": "any other licence: the application cannot approve it; the owner decides outside the application",
        "override": "none: an exception to this policy is a recorded owner decision and a code change, not a setting",
        "status": "CC0 and CC BY are accepted provisionally, subject to source-level verification",
        "approval_requires": [
            "an https source URL and its access date",
            "the licence of the images and, if there are annotations, of the annotations, each eligible",
            "an image origin of publisher_created or third_party_licensed: scraped or unknown images cannot be approved",
            "at least one evidence record from an OFFICIAL source with a quoted licence statement for the images and for the annotations",
            "no evidence that contradicts the declared licence (for example a second source naming CC BY-SA)",
            "commercial use confirmed as yes; redistribution rights recorded; attribution requirement recorded with its text",
            "intended use recorded",
            "the approval itself by an owner or admin, who is recorded",
        ],
        "download_rule": "a dataset must not be downloaded unless its status is 'approved'",
    }


def create_dataset(db: Session, ctx: WorkspaceContext, data: DatasetCreate) -> DatasetDetail:
    synthetic = data.kind == "synthetic"
    d = Dataset(
        workspace_id=ctx.workspace_id,
        name=data.name,
        version=data.version,
        kind=data.kind,
        source_url=data.source_url if not synthetic else (data.source_url or "synthetic://generated"),
        accessed_at=data.accessed_at,
        licence_spdx="SYNTHETIC" if synthetic else data.licence_spdx,
        images_licence_spdx="SYNTHETIC" if synthetic else (data.images_licence_spdx or data.licence_spdx),
        annotations_licence_spdx=None if synthetic else data.annotations_licence_spdx,
        has_annotations=data.has_annotations,
        image_origin="unknown" if synthetic else data.image_origin,
        attribution_required=data.attribution_required,
        attribution_text=data.attribution_text,
        commercial_use=data.commercial_use,
        redistribution=data.redistribution,
        intended_use=data.intended_use,
        notes=data.notes,
        created_by=ctx.user.id,
    )
    try:
        with db.begin_nested():
            db.add(d)
            db.flush()
    except IntegrityError as exc:
        raise Conflict(f"dataset {data.name!r} version {data.version!r} already exists", code="dataset_exists") from exc
    _history(db, ctx, d, None, "proposed", "Dataset proposed", [])
    audit.record_ctx(
        db,
        ctx,
        "dataset.create",
        target_type="dataset",
        target_id=d.id,
        details={"name": d.name, "version": d.version, "kind": d.kind, "licence": d.licence_spdx},
    )
    db.commit()
    return detail(db, ctx, d)


def detail(db: Session, ctx: WorkspaceContext, d: Dataset) -> DatasetDetail:
    hist = db.scalars(
        select(DatasetStatusHistory)
        .where(DatasetStatusHistory.workspace_id == ctx.workspace_id, DatasetStatusHistory.dataset_id == d.id)
        .order_by(DatasetStatusHistory.at, DatasetStatusHistory.id)
    )
    count = (
        db.scalar(
            select(func.count())
            .select_from(DatasetSample)
            .where(DatasetSample.workspace_id == ctx.workspace_id, DatasetSample.dataset_id == d.id)
        )
        or 0
    )
    base = to_out(db, d)
    return DatasetDetail(
        **base.model_dump(),
        evidence=[EvidenceOut.model_validate(e) for e in evidence_of(db, d)],
        history=[StatusHistoryOut.model_validate(h) for h in hist],
        sample_count=count,
    )


def get_detail(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID) -> DatasetDetail:
    return detail(db, ctx, get_dataset(db, ctx, dataset_id))


def list_datasets(db: Session, ctx: WorkspaceContext, page: PageParams, status: str | None) -> Page[DatasetOut]:
    q = select(Dataset).where(Dataset.workspace_id == ctx.workspace_id)
    if status:
        q = q.where(Dataset.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Dataset.created_at.desc(), Dataset.id).limit(page.limit).offset(page.offset))
    return Page(items=[to_out(db, d) for d in rows], total=total, limit=page.limit, offset=page.offset)


def add_evidence(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, data: EvidenceCreate) -> DatasetDetail:
    d = get_dataset(db, ctx, dataset_id, lock=True)
    if d.kind == "synthetic":
        raise Unprocessable("synthetic datasets have no external licence evidence", code="synthetic_no_evidence")
    if d.status in ("approved", "rejected"):
        raise Conflict(
            f"dataset is {d.status}; move it back to under_review before changing its evidence"
            if d.status == "approved"
            else "dataset is rejected",
            code="dataset_locked",
        )
    if not licences.is_https_url(data.url):
        raise Unprocessable("evidence URL must be an https URL", code="invalid_evidence_url")
    db.add(
        DatasetEvidence(
            workspace_id=ctx.workspace_id,
            dataset_id=d.id,
            url=data.url,
            kind=data.kind,
            scope=data.scope,
            licence_spdx=data.licence_spdx,
            excerpt=data.excerpt,
            official=data.official,
            accessed_at=data.accessed_at,
            recorded_by=ctx.user.id,
        )  # fmt: skip
    )
    audit.record_ctx(
        db,
        ctx,
        "dataset.evidence",
        target_type="dataset",
        target_id=d.id,
        details={"url": data.url, "scope": data.scope, "licence": data.licence_spdx, "official": data.official},
    )
    db.commit()
    return detail(db, ctx, d)


def transition(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, data: DatasetTransition) -> DatasetDetail:
    d = get_dataset(db, ctx, dataset_id, lock=True)
    to = data.to_status
    if to not in DATASET_TRANSITIONS[d.status]:
        allowed = ", ".join(sorted(DATASET_TRANSITIONS[d.status])) or "none"
        raise Conflict(
            f"a {d.status} dataset can only move to: {allowed}",
            code="invalid_dataset_transition",
            extra={"allowed": sorted(DATASET_TRANSITIONS[d.status])},
        )
    if to in ("approved", "rejected") and not ctx.has_role(Role.ADMIN):
        raise Forbidden("approving or rejecting a dataset needs an owner or admin")
    blockers: list[str] = []
    if to == "approved":
        blockers = blockers_for(db, d)
        if blockers:
            raise Unprocessable(
                "The dataset cannot be approved yet", code="dataset_not_approvable", extra={"blockers": blockers}
            )
    frm = d.status
    d.status = to
    if to == "approved":
        d.approved_by, d.approved_at = ctx.user.id, utcnow()
    elif frm == "approved":
        d.approved_by, d.approved_at = None, None
    _history(db, ctx, d, frm, to, data.note, blockers)
    audit.record_ctx(
        db,
        ctx,
        "dataset.status",
        target_type="dataset",
        target_id=d.id,
        details={"from": frm, "to": to, "note": data.note},
    )
    db.commit()
    return detail(db, ctx, d)


# ------------------------------------------------------------------------------------------------ samples
def register_samples(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, data: SamplesCreate) -> dict[str, int]:
    d = get_dataset(db, ctx, dataset_id, lock=True)
    if d.kind == "real" and d.status != "approved":
        raise Conflict(
            "samples of a real dataset can only be registered once it is approved (nothing may be downloaded before)",
            code="dataset_not_approved",
        )
    ids = [s.external_id for s in data.samples]
    if len(set(ids)) != len(ids):
        raise Unprocessable("external_id values repeat within the request", code="duplicate_external_id")
    existing = set(
        db.scalars(
            select(DatasetSample.external_id).where(
                DatasetSample.dataset_id == d.id,
                DatasetSample.workspace_id == ctx.workspace_id,
                DatasetSample.external_id.in_(ids),
            )
        )
    )
    if existing:
        raise Conflict(
            f"{len(existing)} sample(s) already exist", code="sample_exists", extra={"examples": sorted(existing)[:10]}
        )
    for s in data.samples:
        db.add(
            DatasetSample(
                workspace_id=ctx.workspace_id,
                dataset_id=d.id,
                external_id=s.external_id,
                group_key=s.group_key,
                label=s.label,
                content_sha256=s.content_sha256,
                phash=s.phash,
                file_status=s.file_status,
                width=s.width,
                height=s.height,
                provenance=s.provenance,
                is_synthetic=d.kind == "synthetic",
            )  # fmt: skip
        )
    audit.record_ctx(
        db, ctx, "dataset.samples", target_type="dataset", target_id=d.id, details={"registered": len(ids)}
    )
    db.commit()
    return {"registered": len(ids)}


def list_samples(
    db: Session,
    ctx: WorkspaceContext,
    dataset_id: uuid.UUID,
    page: PageParams,
    label_status: str | None,
    unlabelled: bool,
) -> Page[SampleOut]:
    d = get_dataset(db, ctx, dataset_id)
    q = select(DatasetSample).where(DatasetSample.workspace_id == ctx.workspace_id, DatasetSample.dataset_id == d.id)
    if label_status:
        q = q.where(DatasetSample.label_status == label_status)
    if unlabelled:
        q = q.where(DatasetSample.label.is_(None))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(DatasetSample.external_id).limit(page.limit).offset(page.offset))
    return Page(items=[SampleOut.model_validate(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


def review_sample(
    db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, sample_id: uuid.UUID, data: ReviewIn
) -> ReviewOut:
    d = get_dataset(db, ctx, dataset_id)
    if d.status == "rejected":
        raise Conflict("the dataset is rejected", code="dataset_locked")
    s = db.scalar(
        select(DatasetSample)
        .where(
            DatasetSample.id == sample_id,
            DatasetSample.workspace_id == ctx.workspace_id,
            DatasetSample.dataset_id == d.id,
        )
        .with_for_update()
    )
    if s is None:
        raise NotFound("Sample not found", code="sample_not_found")
    problem = review.check(s.label_status, data.to_status, s.label, data.to_label, data.evidence)
    if problem:
        raise Conflict(
            problem, code="invalid_review", extra={"allowed": sorted(review.ALLOWED.get(s.label_status, set()))}
        )
    row = LabelReview(
        workspace_id=ctx.workspace_id, dataset_id=d.id, sample_id=s.id, reviewer_id=ctx.user.id,
        reviewer_qualification=data.reviewer_qualification, from_status=s.label_status, to_status=data.to_status,
        from_label=s.label, to_label=data.to_label if data.to_status == "corrected" else s.label,
        evidence=data.evidence, at=utcnow(),
    )  # fmt: skip
    if data.to_status == "corrected":
        s.label = data.to_label
    s.label_status = data.to_status
    s.version += 1
    db.add(row)
    audit.record_ctx(
        db,
        ctx,
        "label.review",
        target_type="dataset_sample",
        target_id=s.id,
        details={"dataset": str(d.id), "from": row.from_status, "to": row.to_status},
    )
    db.commit()
    out = ReviewOut.model_validate(row)
    return out


def sample_history(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, sample_id: uuid.UUID) -> list[ReviewOut]:
    get_dataset(db, ctx, dataset_id)
    rows = db.scalars(
        select(LabelReview)
        .where(
            LabelReview.workspace_id == ctx.workspace_id,
            LabelReview.dataset_id == dataset_id,
            LabelReview.sample_id == sample_id,
        )
        .order_by(LabelReview.at, LabelReview.id)
    )
    return [ReviewOut.model_validate(r) for r in rows]


def agreement_of(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID) -> dict[str, Any]:
    get_dataset(db, ctx, dataset_id)
    rows = db.scalars(
        select(LabelReview)
        .where(
            LabelReview.workspace_id == ctx.workspace_id,
            LabelReview.dataset_id == dataset_id,
            LabelReview.to_status.in_(("accepted", "rejected", "corrected")),
        )
        .order_by(LabelReview.at, LabelReview.id)
        .limit(MAX_SAMPLES_FOR_ANALYSIS * 5)
    )
    decisions = [
        agreement.Decision(str(r.sample_id), str(r.reviewer_id), r.to_status, r.from_label, r.to_label, r.at)
        for r in rows
    ]
    report = agreement.agreement_report(decisions)
    # name the disagreeing samples by their own identifier: time-ordered UUIDs share a prefix and are useless on screen
    wanted = [uuid.UUID(x["sample_id"]) for x in report["disagreements"]]
    names = (
        dict(
            db.execute(
                select(DatasetSample.id, DatasetSample.external_id).where(
                    DatasetSample.workspace_id == ctx.workspace_id,
                    DatasetSample.dataset_id == dataset_id,
                    DatasetSample.id.in_(wanted),
                )
            ).all()
        )
        if wanted
        else {}
    )
    for x in report["disagreements"]:
        x["external_id"] = names.get(uuid.UUID(x["sample_id"]))
    return report


def review_summary(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID) -> ReviewQueueSummary:
    get_dataset(db, ctx, dataset_id)
    rows = db.execute(
        select(DatasetSample.label_status, func.count())
        .where(DatasetSample.workspace_id == ctx.workspace_id, DatasetSample.dataset_id == dataset_id)
        .group_by(DatasetSample.label_status)
    )
    counts = {k: v for k, v in rows}
    total = sum(counts.values())
    reviewed = counts.get("accepted", 0) + counts.get("corrected", 0)
    return ReviewQueueSummary(by_status=counts, reviewed_fraction=round(reviewed / total, 3) if total else 0.0)


# ------------------------------------------------------------------------------------------------ quality and splits
def _samples(db: Session, ctx: WorkspaceContext, d: Dataset) -> list[DatasetSample]:
    rows = list(
        db.scalars(
            select(DatasetSample)
            .where(DatasetSample.workspace_id == ctx.workspace_id, DatasetSample.dataset_id == d.id)
            .order_by(DatasetSample.external_id)
            .limit(MAX_SAMPLES_FOR_ANALYSIS + 1)
        )
    )
    if len(rows) > MAX_SAMPLES_FOR_ANALYSIS:
        raise Unprocessable(
            f"analysis is limited to {MAX_SAMPLES_FOR_ANALYSIS:,} samples per request", code="dataset_too_large"
        )
    return rows


def _records(rows: list[DatasetSample]) -> list[quality.SampleRecord]:
    return [
        quality.SampleRecord(
            str(r.id),
            r.external_id,
            r.group_key,
            r.label,
            r.label_status,
            r.content_sha256,
            r.phash,
            r.file_status,
            r.provenance or {},
            r.is_synthetic,
            r.width,
            r.height,
        )
        for r in rows
    ]


def quality_of(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID) -> dict[str, Any]:
    d = get_dataset(db, ctx, dataset_id)
    report = quality.quality_report(_records(_samples(db, ctx, d)))
    report["dataset"] = {"id": str(d.id), "name": d.name, "version": d.version, "kind": d.kind, "status": d.status}
    return report


def create_split(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, data: SplitCreate) -> SplitDetail:
    d = get_dataset(db, ctx, dataset_id, lock=True)
    if d.kind == "real" and d.status != "approved":
        raise Conflict("a split can only be made from an approved dataset", code="dataset_not_approved")
    eligible_status = {"accepted", "corrected"} | ({"unreviewed", "under_review"} if data.include_unreviewed else set())
    rows = _samples(db, ctx, d)
    use = [
        r for r in rows if r.label_status in eligible_status and r.label and r.group_key and r.file_status != "invalid"
    ]
    skipped = len(rows) - len(use)
    items = [splits.SplitItem(str(r.id), r.group_key or "", r.label, r.content_sha256, r.phash) for r in use]
    try:
        result = splits.grouped_split(items, data.fractions, data.seed)
    except splits.SplitError as exc:
        raise Unprocessable(
            str(exc), code="split_impossible", extra={"usable_samples": len(use), "skipped_samples": skipped}
        ) from exc
    violations = splits.verify_no_leakage(items, result.assignment)
    warnings = list(result.warnings)
    if skipped:
        warnings.append(f"{skipped} sample(s) were left out (rejected, unlabelled, ungrouped, invalid or not reviewed)")
    if data.include_unreviewed:
        warnings.append(
            "includes labels that are not reviewed: usable for engineering checks, not for evaluation claims"
        )
    version = (
        db.scalar(
            select(func.max(DatasetSplit.version)).where(
                DatasetSplit.dataset_id == d.id, DatasetSplit.workspace_id == ctx.workspace_id
            )
        )
        or 0
    ) + 1
    row = DatasetSplit(
        workspace_id=ctx.workspace_id, dataset_id=d.id, version=version, seed=data.seed, fractions=data.fractions,
        include_unreviewed=data.include_unreviewed, manifest=result.assignment, manifest_sha256=result.manifest_sha256,
        stats=result.stats, warnings=warnings, leakage_violations=violations, created_by=ctx.user.id,
    )  # fmt: skip
    db.add(row)
    audit.record_ctx(
        db,
        ctx,
        "dataset.split",
        target_type="dataset",
        target_id=d.id,
        details={"version": version, "seed": data.seed, "violations": len(violations)},
    )
    db.commit()
    return SplitDetail.model_validate(row)


def list_splits(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID) -> list[SplitOut]:
    get_dataset(db, ctx, dataset_id)
    rows = db.scalars(
        select(DatasetSplit)
        .where(DatasetSplit.workspace_id == ctx.workspace_id, DatasetSplit.dataset_id == dataset_id)
        .order_by(DatasetSplit.version.desc())
    )
    return [SplitOut.model_validate(r) for r in rows]


def get_split(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID, version: int) -> SplitDetail:
    get_dataset(db, ctx, dataset_id)
    row = db.scalar(
        select(DatasetSplit).where(
            DatasetSplit.workspace_id == ctx.workspace_id,
            DatasetSplit.dataset_id == dataset_id,
            DatasetSplit.version == version,
        )
    )
    if row is None:
        raise NotFound("Split not found", code="split_not_found")
    check = splits.manifest_checksum(row.manifest, row.seed, row.fractions)
    out = SplitDetail.model_validate(row)
    if check != row.manifest_sha256:  # would mean the stored manifest was altered
        out.warnings = [
            *out.warnings,
            "MANIFEST CHECKSUM MISMATCH: the stored assignment does not match its recorded checksum",
        ]
    return out


def claim_readiness(db: Session, ctx: WorkspaceContext, dataset_id: uuid.UUID) -> dict[str, Any]:
    d = get_dataset(db, ctx, dataset_id)
    rows = _samples(db, ctx, d)
    report = quality.quality_report(_records(rows))
    split = db.scalar(
        select(DatasetSplit)
        .where(DatasetSplit.workspace_id == ctx.workspace_id, DatasetSplit.dataset_id == d.id)
        .order_by(DatasetSplit.version.desc())
        .limit(1)
    )
    test_labels: dict[str, int] = {}
    test_items = 0
    leakage = 0
    if split is not None:
        test_stats = (split.stats or {}).get("test", {})
        test_items = int(test_stats.get("items", 0))
        test_labels = test_stats.get("labels", {})
        leakage = len(split.leakage_violations or [])
    all_labels = {r.label for r in rows if r.label}
    per_class_min = min((test_labels.get(lab, 0) for lab in all_labels), default=0)
    result = evaluation.claim_readiness(
        evaluation.ClaimInputs(
            dataset_kind=d.kind,
            dataset_status=d.status,
            samples=len(rows),
            reviewed_fraction=report.get("reviewed_fraction", 0.0),
            test_items=test_items,
            test_per_class_min=per_class_min,
            leakage_violations=leakage,
            quality_passed=bool(report.get("passed")),
        )  # fmt: skip
    )
    result["split_version"] = split.version if split else None
    result["note"] = (
        "Engineering gate. Even with no blockers, this does not prove a model is good; it only states that nothing here rules a claim out."
    )
    return result
