"""Audit retention: configurable purge, hard floor, idempotence, database guard, housekeeping and the meta endpoint."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.modules.audit import retention
from app.modules.audit import service as audit_service
from app.modules.audit.models import AuditEvent
from app.tools import housekeeping
from tests.conftest import requires_pg_mode
from tests.helpers import make_asset


def seed(world, ages_days: list[float], workspace=None) -> list[uuid.UUID]:
    ids = []
    with world.db() as db:
        for age in ages_days:
            ev = AuditEvent(
                occurred_at=utcnow() - timedelta(days=age),
                workspace_id=uuid.UUID(workspace) if workspace else None,
                action="test.event",
                outcome="success",
                details={"age": age},
            )
            db.add(ev)
            db.flush()
            ids.append(ev.id)
        db.commit()
    return ids


def remaining(world, action: str | None = None) -> list[AuditEvent]:
    with world.db() as db:
        q = select(AuditEvent)
        if action:
            q = q.where(AuditEvent.action == action)
        return list(db.scalars(q))


def test_purge_removes_only_records_older_than_the_retention_and_records_itself(world):
    seed(world, [5, 40, 400, 800, 900])
    with world.db() as db:
        result = retention.purge_expired(db, 730)
    assert (result.matched, result.deleted, result.dry_run) == (2, 2, False)
    ages = sorted(e.details["age"] for e in remaining(world, "test.event"))
    assert ages == [5, 40, 400]
    purge = remaining(world, "audit.purge")
    assert len(purge) == 1 and purge[0].details["deleted"] == 2 and purge[0].details["retention_days"] == 730


def test_purge_is_idempotent_and_a_noop_run_writes_nothing(world):
    seed(world, [800])
    with world.db() as db:
        retention.purge_expired(db, 730)
        again = retention.purge_expired(db, 730)
    assert again.deleted == 0 and again.matched == 0
    assert len(remaining(world, "audit.purge")) == 1  # the second run found nothing and recorded nothing


def test_dry_run_reports_but_deletes_nothing(world):
    seed(world, [800, 900])
    with world.db() as db:
        result = retention.purge_expired(db, 730, dry_run=True)
    assert (result.matched, result.deleted, result.dry_run) == (2, 0, True)
    assert len(remaining(world, "test.event")) == 2 and not remaining(world, "audit.purge")


def test_zero_keeps_everything_forever(world):
    seed(world, [5000, 9000])
    with world.db() as db:
        result = retention.purge_expired(db, 0)
    assert result.deleted == 0 and len(remaining(world, "test.event")) == 2


@pytest.mark.parametrize("days", [1, 10, 29])
def test_a_retention_below_the_floor_is_refused(world, days):
    seed(world, [31])
    with world.db() as db, pytest.raises(ValueError, match="at least 30"):
        retention.purge_expired(db, days)
    assert len(remaining(world, "test.event")) == 1


def test_the_setting_itself_rejects_an_unsafe_retention():
    base = dict(_env_file=None, env="test", jwt_secret="x" * 40, database_url="sqlite://")
    for bad in (1, 29, -5):
        with pytest.raises(ValueError, match="AUDIT_RETENTION_DAYS"):
            Settings(audit_retention_days=bad, **base)
    assert Settings(audit_retention_days=0, **base).audit_retention_days == 0
    assert Settings(audit_retention_days=30, **base).audit_retention_days == 30


def test_purging_works_in_batches(world, monkeypatch):
    monkeypatch.setattr(retention, "BATCH", 2)
    seed(world, [800, 801, 802, 803, 804])
    with world.db() as db:
        assert retention.purge_expired(db, 365).deleted == 5
    assert not remaining(world, "test.event")


def test_other_workspaces_records_are_purged_by_the_same_rule_but_nothing_newer_ever(world, team):
    seed(world, [900], workspace=team.ws)
    seed(world, [900], workspace=team.other_ws)
    seed(world, [10], workspace=team.ws)
    with world.db() as db:
        retention.purge_expired(db, 365)
    left = remaining(world, "test.event")
    assert len(left) == 1 and left[0].details["age"] == 10


def test_housekeeping_runs_both_jobs_and_supports_dry_run(world, monkeypatch):
    seed(world, [800])
    monkeypatch.setattr(housekeeping, "get_settings", lambda: world.settings)
    monkeypatch.setattr(housekeeping, "get_sessionmaker", lambda: world.maker)
    dry = housekeeping.run(dry_run=True)
    assert dry["dry_run"] is True and dry["audit_matched"] == 1 and dry["audit_deleted"] == 0
    done = housekeeping.run()
    assert done["audit_deleted"] == 1 and done["audit_retention_days"] == world.settings.audit_retention_days


@requires_pg_mode
def test_postgresql_guard_allows_only_the_flagged_purge_of_old_rows(world):
    old, recent = seed(world, [40, 10])
    with world.db() as db:
        stmts = [
            ("UPDATE audit_events SET action = 'x'", None),
            ("DELETE FROM audit_events WHERE true", None),  # no purge flag
        ]
        for sql, _ in stmts:
            with pytest.raises(Exception, match="append-only"), db.begin_nested():
                db.execute(text(sql))
        with db.begin_nested():  # flag on, but the row is younger than the 30-day floor
            db.execute(text("SELECT set_config('gg.audit_purge', 'on', true)"))
            with pytest.raises(Exception, match="append-only"), db.begin_nested():
                db.execute(text("DELETE FROM audit_events WHERE id = :i"), {"i": recent})
        with pytest.raises(Exception, match="append-only"), db.begin_nested():  # UPDATE is refused even with the flag
            db.execute(text("SELECT set_config('gg.audit_purge', 'on', true)"))
            db.execute(text("UPDATE audit_events SET action = 'x' WHERE id = :i"), {"i": old})
        with db.begin_nested():  # flag on and old enough: allowed
            db.execute(text("SELECT set_config('gg.audit_purge', 'on', true)"))
            assert db.execute(text("DELETE FROM audit_events WHERE id = :i"), {"i": old}).rowcount == 1
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.id == recent)) == recent


def test_the_meta_endpoint_lists_filters_and_states_the_policy(api_for, team):
    w, m = api_for(team.worker), api_for(team.manager)
    make_asset(w, label="Meta")
    meta = m.get("/audit/meta").json()
    assert "asset.create" in meta["actions"] and "asset" in meta["target_types"]
    assert meta["retention_days"] == 730 and meta["min_retention_days"] == 30
    assert w.get("/audit/meta").status_code == 403
    assert api_for(team.other_owner, team.other_ws).get("/audit/meta").json()["actions"] == []  # per workspace


def test_actions_endpoint_data_is_scoped_to_the_workspace(api_for, team, world):
    seed(world, [1], workspace=team.other_ws)
    assert "test.event" not in api_for(team.manager).get("/audit/meta").json()["actions"]
    assert audit_service is not None
