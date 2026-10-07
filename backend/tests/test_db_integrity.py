"""Guarantees that must hold in the database itself, whatever the application code does.

PostgreSQL-only (skipped, visibly, in SQLite fast mode): triggers, composite foreign keys across tenants, CHECK
constraints, PostGIS generated columns, partial unique indexes and RLS on the schema the API tests actually use.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.assets.models import BiologicalAsset
from app.modules.assets.state import rebuild_state
from app.modules.intelligence.models import Recommendation
from tests.conftest import SEED_SPECIES, requires_pg_mode
from tests.helpers import make_asset, make_issue, make_location, make_task, observe

pg = requires_pg_mode


def _sql(db, query: str, **params):
    return db.execute(text(query), params)


@pg
def test_the_migration_seeds_global_species(world):
    with world.db() as db:
        names = {r[0] for r in _sql(db, "SELECT common_name FROM species WHERE workspace_id IS NULL")}
    assert {name for _, name in SEED_SPECIES} <= names and len(names) >= 11


@pg
@pytest.mark.parametrize(
    "table,column",
    [("observations", "notes"), ("issue_status_history", "note"), ("task_status_history", "note")],
)
def test_history_tables_reject_update_and_delete(api_for, team, world, table, column):
    mgr = api_for(team.manager)
    a = make_asset(mgr)
    observe(mgr, a["id"], health_score=50, notes="original")
    issue = make_issue(mgr, a["id"])
    make_task(mgr, issue_id=issue["id"])
    with world.db() as db:
        for statement in (f"UPDATE {table} SET {column} = 'tampered'", f"DELETE FROM {table}"):
            with pytest.raises(DBAPIError, match="append-only"):
                _sql(db, statement)
            db.rollback()
        assert _sql(db, f"SELECT count(*) FROM {table}").scalar() >= 1  # still there, unchanged


@pg
def test_cross_tenant_links_are_rejected_by_the_database(api_for, team, world):
    mine, theirs = api_for(team.manager), api_for(team.other_owner, team.other_ws)
    foreign_zone, foreign_asset = make_location(theirs, "Theirs"), make_asset(theirs, label="Theirs")
    my_asset = make_asset(mine)
    with world.db() as db:
        # a service bug must not be able to attach our asset to their location, or their asset to our records
        db.add(
            BiologicalAsset(
                workspace_id=UUID(team.ws), location_id=UUID(foreign_zone["id"]), kind="tree", label="x", attributes={}
            )
        )
        with pytest.raises(IntegrityError, match="fk_biological_assets_location"):
            db.flush()
        db.rollback()
        for table, cols, vals in (
            (
                "observations",
                "id, workspace_id, asset_id, observed_at, kind, source, symptoms, data, attachments, created_at",
                "gen_random_uuid(), :ws, :asset, now(), 'health', 'human', '[]', '{}', '[]', now()",
            ),
            (
                "issues",
                "id, workspace_id, key, title, category, severity, workflow_key, state, asset_id, source, opened_at, updated_at, version",
                "gen_random_uuid(), :ws, 'GG-999', 't', 'other', 'low', 'plant_health', 'open', :asset, 'manual', now(), now(), 1",
            ),
            (
                "tasks",
                "id, workspace_id, key, type, title, asset_id, priority, status, source, created_at, updated_at, version",
                "gen_random_uuid(), :ws, 'T-999', 'other', 't', :asset, 'p3', 'todo', 'manual', now(), now(), 1",
            ),
        ):
            with pytest.raises(IntegrityError):
                _sql(db, f"INSERT INTO {table} ({cols}) VALUES ({vals})", ws=team.ws, asset=foreign_asset["id"])
            db.rollback()
        _ = my_asset


@pg
def test_check_constraints_hold_even_for_direct_sql(api_for, team, world):
    a = make_asset(api_for(team.manager))
    cases = [
        (
            "UPDATE biological_assets SET tracking_mode = 'population', estimated_count = NULL WHERE id = :id",
            "population_has_count",
        ),
        ("UPDATE biological_assets SET estimated_count = 5 WHERE id = :id", "population_has_count"),
        ("UPDATE biological_assets SET latitude = 10 WHERE id = :id", "coords_pair"),
        ("UPDATE biological_assets SET latitude = 99, longitude = 0 WHERE id = :id", "lat_range"),
        ("UPDATE biological_assets SET kind = 'robot' WHERE id = :id", "ck_biological_assets_kind"),
        ("UPDATE asset_states SET health_score = 101 WHERE asset_id = :id", "health_range"),
    ]
    with world.db() as db:
        for statement, constraint in cases:
            with pytest.raises(IntegrityError, match=constraint):
                _sql(db, statement, id=a["id"])
            db.rollback()


@pg
def test_issue_resolution_columns_cannot_be_inconsistent(api_for, team, world):
    issue = make_issue(api_for(team.manager), make_asset(api_for(team.manager))["id"])
    with world.db() as db, pytest.raises(IntegrityError, match="resolution_consistent"):
        _sql(db, "UPDATE issues SET resolved_at = now() WHERE id = :id", id=issue["id"])  # closed but no outcome


@pg
def test_postgis_centroid_is_generated_from_latitude_and_longitude(api_for, team, world):
    mgr = api_for(team.manager)
    placed = make_asset(mgr, label="Placed", latitude=19.2012, longitude=72.9701)
    unplaced = make_asset(mgr, label="Unplaced")
    zone = make_location(mgr, "Zone", latitude=19.2, longitude=72.97)
    with world.db() as db:
        wkt = lambda t, i: _sql(db, f"SELECT ST_AsText(centroid) FROM {t} WHERE id = :i", i=i).scalar()  # noqa: E731
        assert wkt("biological_assets", placed["id"]) == "POINT(72.9701 19.2012)"  # x = longitude, y = latitude
        assert wkt("biological_assets", unplaced["id"]) is None
        assert wkt("locations", zone["id"]) == "POINT(72.97 19.2)"
        inside = _sql(
            db, "SELECT count(*) FROM biological_assets WHERE centroid && ST_MakeEnvelope(72.9, 19.1, 73.0, 19.3, 4326)"
        ).scalar()
        outside = _sql(
            db, "SELECT count(*) FROM biological_assets WHERE centroid && ST_MakeEnvelope(0, 0, 1, 1, 4326)"
        ).scalar()
        assert (inside, outside) == (1, 0)
        indexes = {
            r[0]
            for r in _sql(
                db,
                "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() AND indexdef ILIKE '%gist%centroid%'",
            )
        }
        assert len(indexes) == 2  # one per spatial table
    mgr.patch(f"/assets/{placed['id']}", {"latitude": 10.0, "longitude": 20.0})
    with world.db() as db:
        assert (
            _sql(db, "SELECT ST_AsText(centroid) FROM biological_assets WHERE id = :i", i=placed["id"]).scalar()
            == "POINT(20 10)"
        )


@pg
def test_only_one_open_recommendation_per_dedupe_key(api_for, team, world):
    a = make_asset(api_for(team.manager))

    def rec(status: str) -> Recommendation:
        return Recommendation(
            workspace_id=UUID(team.ws),
            rule_key="critical_health",
            method="rule",
            asset_id=UUID(a["id"]),
            dedupe_key="critical_health:x",
            title="t",
            explanation="e",
            severity="high",
            status=status,
        )

    with world.db() as db:
        db.add(rec("open"))
        db.flush()
        db.add(rec("open"))
        with pytest.raises(IntegrityError, match="uq_recommendations_open_dedupe"):
            db.flush()
        db.rollback()
        db.add(rec("dismissed"))  # history of decided recommendations is unconstrained
        db.add(rec("dismissed"))
        db.flush()


@pg
def test_history_is_protected_from_cascading_deletes(api_for, team, world):
    mgr = api_for(team.manager)
    a = make_asset(mgr)
    observe(mgr, a["id"])
    with world.db() as db, pytest.raises(IntegrityError):
        _sql(db, "DELETE FROM biological_assets WHERE id = :id", id=a["id"])  # observations RESTRICT the delete


@pg
def test_indexes_exist_for_the_real_query_patterns(world):
    expected = {
        "ix_biological_assets_workspace_kind",
        "ix_biological_assets_workspace_location",
        "ix_asset_states_workspace_band",
        "ix_asset_states_workspace_last_observed",
        "ix_observations_asset_observed",
        "ix_issues_workspace_state_severity",
        "ix_issues_workspace_asset",
        "ix_issues_workspace_assignee",
        "ix_issue_status_history_issue_at",
        "ix_tasks_workspace_assignee_status_due",
        "ix_tasks_workspace_issue",
        "ix_tasks_workspace_asset",
        "ix_task_status_history_task_at",
        "uq_recommendations_open_dedupe",
        "ix_recommendations_workspace_status",
    }
    with world.db() as db:
        have = {r[0] for r in _sql(db, "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()")}
    assert expected <= have, expected - have


@pg
def test_rls_is_enabled_on_every_table_the_api_uses(world):
    with world.db() as db:
        rows = _sql(
            db,
            "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind = 'r'",
        ).all()
    assert len(rows) >= 17 and all(on for _, on in rows), [n for n, on in rows if not on]


def test_the_state_projection_equals_a_rebuild_from_history(api_for, team, world):
    """asset_states is a cache of append-only history: recomputing it from scratch must give the same answer."""
    mgr, worker = api_for(team.manager), api_for(team.worker)
    a = make_asset(mgr)
    observe(worker, a["id"], health_score=30)
    issue = make_issue(mgr, a["id"])
    make_task(mgr, issue_id=issue["id"], assignee_id=str(team.worker.id))
    observe(worker, a["id"], health_score=75, notes="recovering")
    before = mgr.get(f"/assets/{a['id']}").json()["state"]
    with world.db() as db:
        rebuilt = rebuild_state(db, UUID(team.ws), UUID(a["id"]))
        db.commit()
    after = mgr.get(f"/assets/{a['id']}").json()["state"]
    assert rebuilt.health_score == 75 and rebuilt.open_issue_count == 1 and rebuilt.open_task_count == 1
    assert {k: after[k] for k in ("health_score", "health_band", "open_issue_count", "open_task_count")} == {
        k: before[k] for k in ("health_score", "health_band", "open_issue_count", "open_task_count")
    }
