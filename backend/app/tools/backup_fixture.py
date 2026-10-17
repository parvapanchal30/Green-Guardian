"""A small, realistic dataset for proving backup and restore (used by ops/ci-backup-restore.sh).

    python -m app.tools.backup_fixture

Writes into whatever DATABASE_URL/DB_SCHEMA point at, so only run it against a database you created for the purpose.
It exercises what a restore must preserve: geometry (the generated PostGIS centroids), the append-only history,
tenant links, and the audit trail. It refuses to run against a database that already holds users.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.db import get_sessionmaker
from app.core.timeutil import utcnow
from app.models import (
    AssetState,
    AuditEvent,
    BiologicalAsset,
    Location,
    Membership,
    Observation,
    Organization,
    User,
    Workspace,
)


def build() -> dict[str, int]:
    with get_sessionmaker()() as db:
        if db.scalar(select(func.count()).select_from(User)):
            raise SystemExit("refusing: this database already has users; use an empty scratch database")
        now = utcnow()
        org = Organization(name="Fixture Org", slug=f"fixture-{uuid.uuid4().hex[:8]}")
        user = User(
            email=f"fixture-{uuid.uuid4().hex[:8]}@example.com", password_hash="!", name="Fixture", is_active=True
        )
        db.add_all([org, user])
        db.flush()
        ws = Workspace(
            organization_id=org.id,
            name="Fixture workspace",
            mode="green_management",
            timezone="UTC",
            settings={},
            capabilities={},
            key_counters={"issue": 0, "task": 0},
        )
        db.add(ws)
        db.flush()
        db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
        zone = Location(
            workspace_id=ws.id, name="Zone 1", kind="zone", latitude=19.076, longitude=72.8777, attributes={}
        )
        db.add(zone)
        db.flush()
        for i in range(5):
            asset = BiologicalAsset(
                workspace_id=ws.id,
                location_id=zone.id,
                kind="tree",
                tracking_mode="individual",
                label=f"Tree {i}",
                latitude=19.07 + i * 0.001 if i < 4 else None,
                longitude=72.87 + i * 0.001 if i < 4 else None,
                current_stage="planted",
                attributes={},
                created_by=user.id,
            )
            db.add(asset)
            db.flush()
            db.add(
                AssetState(
                    asset_id=asset.id,
                    workspace_id=ws.id,
                    health_score=60 + i * 5,
                    health_band="at_risk",
                    open_issue_count=0,
                    open_task_count=0,
                    updated_at=now,
                )
            )
            db.add(
                Observation(
                    workspace_id=ws.id,
                    asset_id=asset.id,
                    observed_at=now - timedelta(days=i),
                    observer_id=user.id,
                    kind="health",
                    source="human",
                    health_score=60 + i * 5,
                    symptoms=[],
                    data={},
                    attachments=[],
                )
            )
        db.add(
            AuditEvent(
                workspace_id=ws.id,
                actor_id=user.id,
                action="fixture.created",
                outcome="success",
                details={"note": "backup test"},
            )
        )
        db.commit()
        return {
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
            "assets": db.scalar(select(func.count()).select_from(BiologicalAsset)) or 0,
            "observations": db.scalar(select(func.count()).select_from(Observation)) or 0,
        }


if __name__ == "__main__":
    print("fixture created:", build())
