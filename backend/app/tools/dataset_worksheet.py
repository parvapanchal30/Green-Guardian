"""Load the reviewed candidate-dataset worksheet into a workspace's catalog, through the same service code as the API.

    python -m app.tools.dataset_worksheet --workspace <uuid> --user-email <manager@...>            # dry run (default)
    python -m app.tools.dataset_worksheet --workspace <uuid> --user-email <manager@...> --apply   # write

The entries are created as `proposed` datasets with their evidence. Nothing is approved, no status is changed,
nothing is fetched or downloaded, and existing (name, version) pairs are left alone, so it is safe to run again.
The acting user must be an existing member of the workspace with the manager role or higher; their identity is what
the catalog records as the creator and evidence recorder (the tool never invents one). Each evidence excerpt gets a
suffix saying how it was verified.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_sessionmaker
from app.core.deps import WorkspaceContext
from app.modules.datasets import licences, service
from app.modules.datasets.models import Dataset
from app.modules.datasets.schemas import DatasetCreate, EvidenceCreate
from app.modules.identity.models import User
from app.modules.identity.service import normalize_email
from app.modules.workspaces.models import ROLE_RANK, Membership, Role, Workspace

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "docs" / "datasets" / "candidates.json"
MAX_EXCERPT = 600


class WorksheetError(Exception):
    pass


def load(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf8"))["entries"]


def evidence_payload(raw: dict[str, Any]) -> EvidenceCreate:
    """The API model plus how the evidence was verified, appended to the excerpt so the catalog carries it."""
    data = {k: v for k, v in raw.items() if k != "verified_how"}
    how = raw.get("verified_how")
    if how:
        suffix = f" [verified: {how}]"
        data["excerpt"] = data["excerpt"][: MAX_EXCERPT - len(suffix)] + suffix
    return EvidenceCreate(**data)


def blockers(catalog: DatasetCreate, evidence: list[EvidenceCreate]) -> list[str]:
    facts = licences.DatasetFacts(
        catalog.name, catalog.version, catalog.kind, catalog.source_url, catalog.accessed_at, catalog.licence_spdx,
        catalog.images_licence_spdx or catalog.licence_spdx, catalog.annotations_licence_spdx, catalog.has_annotations,
        catalog.attribution_required, catalog.attribution_text, catalog.commercial_use, catalog.redistribution,
        catalog.intended_use, catalog.image_origin,
    )  # fmt: skip
    ev = [
        licences.Evidence(e.url, e.kind, e.scope, e.licence_spdx, e.excerpt, e.official, e.accessed_at)
        for e in evidence
    ]
    return licences.approval_blockers(facts, ev)


def context(db: Session, workspace_id: uuid.UUID, email: str) -> WorkspaceContext:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    workspace = db.get(Workspace, workspace_id)
    if user is None or workspace is None or workspace.archived_at is not None:
        raise WorksheetError("unknown user or workspace")
    role = db.scalar(
        select(Membership.role).where(Membership.user_id == user.id, Membership.workspace_id == workspace_id)
    )
    if role is None or ROLE_RANK[Role(role)] < ROLE_RANK[Role.MANAGER]:
        raise WorksheetError("the user must be a member of the workspace with the manager role or higher")
    return WorkspaceContext(workspace=workspace, user=user, role=Role(role))


def run(
    db: Session, workspace_id: uuid.UUID, email: str, entries: list[dict[str, Any]], *, apply: bool
) -> list[dict[str, Any]]:
    ctx = context(db, workspace_id, email)
    report: list[dict[str, Any]] = []
    for entry in entries:
        catalog = DatasetCreate(**entry["catalog"])
        evidence = [evidence_payload(e) for e in entry["evidence"]]
        existing = db.scalar(
            select(Dataset.id).where(
                Dataset.workspace_id == workspace_id, Dataset.name == catalog.name, Dataset.version == catalog.version
            )
        )
        row = {
            "id": entry.get("id"), "name": catalog.name, "version": catalog.version, "evidence": len(evidence),
            "blockers_if_loaded": blockers(catalog, evidence), "outcome": entry.get("outcome"),
        }  # fmt: skip
        if existing is not None:
            row["action"] = "skipped: already in the catalog"
        elif not apply:
            row["action"] = "would create (dry run)"
        else:
            created = service.create_dataset(db, ctx, catalog)
            for e in evidence:
                service.add_evidence(db, ctx, created.id, e)
            row["action"] = "created as proposed"
        report.append(row)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", required=True, type=uuid.UUID)
    parser.add_argument("--user-email", required=True)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--apply", action="store_true", help="write to the catalog (default is a dry run)")
    args = parser.parse_args()
    with get_sessionmaker()() as db:
        try:
            report = run(db, args.workspace, args.user_email, load(args.file), apply=args.apply)
        except WorksheetError as exc:
            raise SystemExit(f"error: {exc}") from exc
    for r in report:
        print(f"{r['name']} {r['version']}: {r['action']}; evidence rows: {r['evidence']}")
        for b in r["blockers_if_loaded"]:
            print(f"    blocker: {b}")


if __name__ == "__main__":
    main()
