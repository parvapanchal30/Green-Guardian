"""Asset lifecycle (ADR-055): templates per mode, append-only events, transition rules, roles, corrections, exits, and what
the rest of the product does with an asset that has left the lifecycle (agent, dashboard, map)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.modules.assets.lifecycle import ALL_STAGES, EXIT_STAGES, check_transition, next_choices
from app.modules.assets.models import BiologicalAsset, LifecycleEvent
from app.modules.audit.models import AuditEvent
from tests.conftest import requires_pg_mode
from tests.helpers import ago, ahead, make_asset, observe

pg = requires_pg_mode


def lifecycle(api, asset_id: str) -> dict:
    r = api.get(f"/assets/{asset_id}/lifecycle")
    assert r.status_code == 200, r.text
    return r.json()


def record(api, asset_id: str, stage: str, **over):
    return api.post(f"/assets/{asset_id}/lifecycle", {"stage": stage, **over})


def stages(history: list[dict]) -> list[str]:
    return [e["stage"] for e in history]  # newest first


# ------------------------------------------------------------------ the templates


def test_each_mode_has_its_own_template_and_everyone_in_the_workspace_may_read_it(api_for, team):
    green = api_for(team.viewer).get("/lifecycle-template").json()
    agri = api_for(team.owner, team.agri_ws).get("/lifecycle-template").json()
    assert [s["key"] for s in green["stages"]] == [
        "planted",
        "growing",
        "mature",
        "maintained",
        "health_monitoring",
        "survival",
    ]
    assert [s["key"] for s in agri["stages"]] == [
        "planted",
        "germination",
        "vegetative",
        "flowering",
        "fruiting",
        "harvest",
        "post_harvest",
    ]
    assert [s["key"] for s in green["exits_individual"]] == ["dead", "removed", "replaced"]
    assert [s["key"] for s in green["exits_population"]] == ["failed", "removed", "replaced"]
    assert {s["key"] for s in green["exits_individual"] if s["manager_only"]} == {"removed", "replaced"}
    assert api_for(team.outsider).get("/lifecycle-template").status_code == 404


def test_stage_vocabulary_is_closed_and_consistent():
    assert set(EXIT_STAGES) <= set(ALL_STAGES) and len(ALL_STAGES) == len(set(ALL_STAGES))
    assert next_choices("green_management", "individual", "dead") == ()
    assert next_choices("green_management", "individual", "mature")[:3] == (
        "maintained",
        "health_monitoring",
        "survival",
    )
    assert "failed" not in next_choices("green_management", "individual", "planted")
    assert "failed" in next_choices("green_management", "population", "planted")
    assert (
        check_transition("green_management", "individual", "planted", "planted", correction=False).code == "same_stage"
    )


# ------------------------------------------------------------------ the initial stage


def test_a_new_asset_starts_in_planted_with_one_initial_event(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w)
    assert a["current_stage"] == "planted" and a["is_active"] is True
    lc = lifecycle(w, a["id"])
    assert lc["current_stage"] == "planted" and [e["stage"] for e in lc["history"]] == ["planted"]
    first = lc["history"][0]
    assert first["previous_stage"] is None and first["source"] == "manual" and first["correction"] is False


def test_the_initial_event_is_dated_by_the_planting_date_but_never_in_the_future(api_for, team):
    w = api_for(team.worker)
    past = make_asset(w, planted_at="2023-04-01")
    assert lifecycle(w, past["id"])["history"][0]["entered_at"].startswith("2023-04-01")
    tomorrow = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    future = make_asset(w, label="Planned", planted_at=tomorrow)
    entered = datetime.fromisoformat(lifecycle(w, future["id"])["history"][0]["entered_at"]).replace(tzinfo=UTC)
    assert entered <= datetime.now(UTC) + timedelta(minutes=5)


def test_an_asset_can_be_registered_in_a_later_stage_of_its_workspace_template(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w, stage="mature")
    assert a["current_stage"] == "mature" and lifecycle(w, a["id"])["history"][0]["stage"] == "mature"
    for bad in ("dead", "flowering", "nonsense"):  # an exit, another mode's stage, a made-up stage
        r = w.post("/assets", {"label": "x", "kind": "tree", "stage": bad})
        assert r.status_code == 422 and r.json()["code"] == "invalid_stage", bad
    agri = api_for(team.owner, team.agri_ws)
    assert make_asset(agri, stage="flowering")["current_stage"] == "flowering"
    assert agri.post("/assets", {"label": "x", "kind": "tree", "stage": "mature"}).status_code == 422


# ------------------------------------------------------------------ recording stage changes


def test_a_forward_change_is_appended_and_projected(api_for, team, world):
    w = api_for(team.worker)
    a = make_asset(w)
    r = record(w, a["id"], "growing", note="first leaves")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["current_stage"] == "growing" and stages(body["history"]) == ["growing", "planted"]
    top = body["history"][0]
    assert top["previous_stage"] == "planted" and top["note"] == "first leaves" and top["stage_label"] == "Growing"
    assert w.get(f"/assets/{a['id']}").json()["current_stage"] == "growing"
    with world.db() as db:
        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.action == "asset.lifecycle.record")).all()
    assert len(actions) == 1


def test_skipping_ahead_is_allowed(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w)
    assert record(w, a["id"], "mature").status_code == 201
    assert lifecycle(w, a["id"])["current_stage"] == "mature"


def test_going_back_or_repeating_a_stage_is_refused_and_says_what_is_allowed(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w)
    record(w, a["id"], "mature")
    back = record(w, a["id"], "growing")
    assert back.status_code == 409 and back.json()["code"] == "backward_transition"
    assert back.json()["allowed"][:2] == ["maintained", "health_monitoring"]
    same = record(w, a["id"], "mature")
    assert same.status_code == 409 and same.json()["code"] == "same_stage"
    other_mode = record(w, a["id"], "flowering")
    assert other_mode.status_code == 422 and other_mode.json()["code"] == "invalid_stage"
    assert lifecycle(w, a["id"])["current_stage"] == "mature"


def test_the_next_choices_follow_the_template_and_the_tracking_mode(api_for, team):
    w = api_for(team.worker)
    tree = make_asset(w)
    batch = make_asset(w, label="Batch", kind="crop_batch", tracking_mode="population", estimated_count=50)
    t = [c["key"] for c in lifecycle(w, tree["id"])["next_choices"]]
    b = [c["key"] for c in lifecycle(w, batch["id"])["next_choices"]]
    assert t[-3:] == ["dead", "removed", "replaced"] and b[-3:] == ["failed", "removed", "replaced"]
    assert "growing" in t and "planted" not in t


def test_dates_cannot_be_in_the_future_or_before_the_previous_change(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w, planted_at="2020-01-01")  # the initial stage is dated by the planting date
    r = record(w, a["id"], "growing", entered_at=ahead(days=2))
    assert r.status_code == 422 and r.json()["code"] == "entered_in_future"
    record(w, a["id"], "growing", entered_at=ago(days=10))
    r = record(w, a["id"], "mature", entered_at=ago(days=20))
    assert r.status_code == 422 and r.json()["code"] == "entered_before_previous"
    assert record(w, a["id"], "mature", entered_at=ago(days=5)).status_code == 201  # back-dated but in order
    assert stages(lifecycle(w, a["id"])["history"]) == ["mature", "growing", "planted"]


def test_unknown_fields_are_rejected_and_the_stage_is_required(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w)
    assert w.post(f"/assets/{a['id']}/lifecycle", {}).status_code == 422
    assert w.post(f"/assets/{a['id']}/lifecycle", {"stage": "growing", "current_stage": "dead"}).status_code == 422


# ------------------------------------------------------------------ exits and corrections


def test_a_worker_can_report_a_death_but_removal_and_replacement_need_a_manager(api_for, team):
    w, m = api_for(team.worker), api_for(team.manager)
    a, b, c = (make_asset(w, label=f"Tree {i}") for i in range(3))
    assert record(w, a["id"], "dead", note="storm damage").status_code == 201
    for stage in ("removed", "replaced"):
        r = record(w, b["id"], stage)
        assert r.status_code == 403 and r.json()["code"] == "exit_requires_manager"
    assert record(m, b["id"], "removed").status_code == 201
    assert record(m, c["id"], "replaced").status_code == 201


def test_failed_is_for_batches_and_dead_is_for_individuals(api_for, team):
    w = api_for(team.worker)
    tree = make_asset(w)
    batch = make_asset(w, label="Batch", kind="crop_batch", tracking_mode="population", estimated_count=50)
    assert record(w, tree["id"], "failed").status_code == 422
    assert record(w, batch["id"], "dead").status_code == 422
    assert record(w, batch["id"], "failed").status_code == 201


def test_an_exited_asset_takes_no_more_ordinary_changes(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w)
    record(w, a["id"], "dead")
    lc = lifecycle(w, a["id"])
    assert lc["is_active"] is False and lc["next_choices"] == []
    assert w.get(f"/assets/{a['id']}").json()["is_active"] is False
    r = record(w, a["id"], "growing")
    assert r.status_code == 409 and r.json()["code"] == "asset_exited"


def test_corrections_need_a_manager_and_a_written_reason_and_are_recorded_as_such(api_for, team):
    w, m = api_for(team.worker), api_for(team.manager)
    a = make_asset(w)
    record(w, a["id"], "mature")
    r = record(w, a["id"], "growing", correction=True, note="entered mature by mistake")
    assert r.status_code == 403 and r.json()["code"] == "correction_requires_manager"
    for note in (None, "", "short"):
        r = record(m, a["id"], "growing", correction=True, **({"note": note} if note is not None else {}))
        assert r.status_code == 422 and r.json()["code"] == "correction_reason_required", note
    r = record(m, a["id"], "growing", correction=True, note="entered mature by mistake")
    assert r.status_code == 201
    top = r.json()["history"][0]
    assert top["correction"] is True and top["stage"] == "growing" and top["previous_stage"] == "mature"
    assert r.json()["current_stage"] == "growing"
    assert len(r.json()["history"]) == 3  # the mistaken entry is still there


def test_a_manager_can_reinstate_an_exited_asset_only_as_a_correction(api_for, team):
    w, m = api_for(team.worker), api_for(team.manager)
    a = make_asset(w)
    record(w, a["id"], "dead")
    r = record(m, a["id"], "growing", correction=True, note="the tree was resprouting; recorded dead in error")
    assert r.status_code == 201 and r.json()["is_active"] is True
    assert stages(r.json()["history"]) == ["growing", "dead", "planted"]


def test_a_correction_to_the_same_stage_is_still_refused(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    r = record(m, a["id"], "planted", correction=True, note="a perfectly good reason")
    assert r.status_code == 409 and r.json()["code"] == "same_stage"


# ------------------------------------------------------------------ permissions and tenancy


def test_roles_and_tenants(api_for, team):
    w = api_for(team.worker)
    a = make_asset(w)
    v = api_for(team.viewer)
    assert record(v, a["id"], "growing").status_code == 403
    assert lifecycle(v, a["id"])["current_stage"] == "planted"
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get(f"/assets/{a['id']}/lifecycle").status_code == 404
    assert record(theirs, a["id"], "growing").status_code == 404
    assert record(api_for(team.worker, team.other_ws), a["id"], "growing").status_code == 404
    assert api_for(team.outsider).get(f"/assets/{a['id']}/lifecycle").status_code == 404
    assert lifecycle(w, a["id"])["current_stage"] == "planted"


def test_archived_assets_take_no_lifecycle_changes_but_keep_their_history_in_the_timeline(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    record(m, a["id"], "growing")
    assert m.delete(f"/assets/{a['id']}").status_code == 204
    assert record(m, a["id"], "mature").status_code == 404
    assert m.get(f"/assets/{a['id']}/lifecycle").status_code == 404
    kinds = [e["title"] for e in m.get(f"/assets/{a['id']}/timeline").json() if e["type"] == "lifecycle"]
    assert any("Planted → Growing" in t or "Growing" in t for t in kinds) and len(kinds) == 2


# ------------------------------------------------------------------ history, filters, invariant


def test_current_stage_always_equals_the_latest_event(api_for, team, world):
    w, m = api_for(team.worker), api_for(team.manager)
    a = make_asset(w)
    steps = [
        (w, "growing", {}),
        (w, "mature", {}),
        (m, "growing", {"correction": True, "note": "mistaken maturity entry"}),
        (w, "mature", {}),
        (w, "dead", {}),
        (m, "mature", {"correction": True, "note": "recorded dead in error"}),
    ]
    for api, stage, over in steps:
        assert record(api, a["id"], stage, **over).status_code == 201, (stage, over)
        with world.db() as db:
            asset = db.get(BiologicalAsset, UUID(a["id"]))
            latest = db.scalars(
                select(LifecycleEvent)
                .where(LifecycleEvent.asset_id == asset.id)
                .order_by(LifecycleEvent.entered_at.desc(), LifecycleEvent.id.desc())
            ).first()
            assert asset.current_stage == latest.stage == stage


def test_the_asset_list_filters_by_stage_and_by_active(api_for, team):
    w = api_for(team.worker)
    alive = make_asset(w, label="Alive")
    dead = make_asset(w, label="Dead")
    record(w, dead["id"], "dead")
    record(w, alive["id"], "growing")
    names = lambda **p: sorted(i["label"] for i in w.get("/assets", params=p).json()["items"])  # noqa: E731
    assert names() == ["Alive", "Dead"]
    assert names(active=True) == ["Alive"] and names(active=False) == ["Dead"]
    assert names(stage="growing") == ["Alive"] and names(stage="dead") == ["Dead"]


def test_the_timeline_merges_lifecycle_entries_and_marks_corrections(api_for, team):
    m = api_for(team.manager)
    a = make_asset(m)
    record(m, a["id"], "mature")
    record(m, a["id"], "growing", correction=True, note="mistaken maturity entry")
    observe(m, a["id"], health_score=70)
    items = m.get(f"/assets/{a['id']}/timeline").json()
    titles = [e["title"] for e in items if e["type"] == "lifecycle"]
    assert len(titles) == 3 and titles[0].startswith("Correction: ") and "Mature → Growing" in titles[0]
    assert {e["type"] for e in items} == {"lifecycle", "observation"}


# ------------------------------------------------------------------ the rest of the product


def test_an_exited_asset_is_dropped_from_dashboard_counts_agent_suggestions_and_the_map(api_for, team, world):
    from tests.test_agent_api import age_asset

    m = api_for(team.manager)
    live = make_asset(m, label="Live", latitude=19.2, longitude=72.97)
    gone = make_asset(m, label="Gone", latitude=19.21, longitude=72.98)
    for asset in (live, gone):
        age_asset(world, asset["id"], 40)  # both would trigger an inspection suggestion
    record(m, gone["id"], "dead")

    d = m.get("/dashboard").json()
    assert d["assets"]["total"] == 1 and d["assets"]["exited"] == 1 and d["work"]["inspections_due"] == 1
    run = m.post("/agent/run").json()
    assert [r["title"].split(" has ")[0] for r in run["created"]] == ["Live"]
    layer = m.get("/map/layers/assets").json()
    labels = {f["properties"]["label"] for f in layer["features"]}
    assert labels == {"Live"}  # the dead tree's last health reading would mislead on a map


def test_survival_kpi_counts_recorded_deaths_and_ignores_removals_and_batches(api_for, team):
    m = api_for(team.manager)
    survival = lambda: next(k for k in m.get("/dashboard").json()["kpis"] if k["key"] == "survival")  # noqa: E731
    s0 = survival()
    assert s0["available"] is False and "individually tracked" in s0["reason"]
    trees = [make_asset(m, label=f"T{i}") for i in range(4)]
    batch = make_asset(m, label="B", kind="crop_batch", tracking_mode="population", estimated_count=10)
    record(m, trees[0]["id"], "dead")
    record(m, trees[1]["id"], "removed")  # a management decision: not counted either way
    record(m, batch["id"], "failed")  # batches are outside this figure
    s = survival()
    assert s["available"] is True and s["value"] == 66.7 and s["unit"] == "%"  # 2 alive of (2 alive + 1 dead)
    assert "2 alive of 3" in s["basis"] and "removed and replaced" in s["basis"]


def test_harvest_kpi_counts_assets_in_the_harvest_stages_in_an_agricultural_workspace(api_for, team):
    o = api_for(team.owner, team.agri_ws)
    harvest = lambda: next(k for k in o.get("/dashboard").json()["kpis"] if k["key"] == "harvest")  # noqa: E731
    assert harvest()["available"] is False
    a = make_asset(o, label="Block A", kind="crop_batch", tracking_mode="population", estimated_count=100)
    b = make_asset(o, label="Block B", kind="crop_batch", tracking_mode="population", estimated_count=100)
    assert harvest()["value"] == 0.0
    record(o, a["id"], "harvest")
    record(o, b["id"], "fruiting")
    h = harvest()
    assert h["value"] == 1.0 and "1 of 2 active assets" in h["basis"] and "not a forecast" in h["basis"]
    record(o, a["id"], "post_harvest")
    assert harvest()["value"] == 1.0


# ------------------------------------------------------------------ database guarantees (PostgreSQL only)


@pg
def test_lifecycle_events_are_append_only_in_the_database(api_for, team, world):
    w = api_for(team.worker)
    a = make_asset(w)
    record(w, a["id"], "growing")
    with world.db() as db:
        for statement in (
            "UPDATE lifecycle_events SET note = 'edited' WHERE asset_id = :id",
            "DELETE FROM lifecycle_events WHERE asset_id = :id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(statement), {"id": a["id"]})
            db.rollback()


@pg
def test_lifecycle_constraints_and_tenant_foreign_key(api_for, team, world):
    w = api_for(team.worker)
    a = make_asset(w)
    base = "INSERT INTO lifecycle_events (id, workspace_id, asset_id, stage, entered_at, source, correction, note, created_at) "
    ok = f"{base}VALUES (gen_random_uuid(), :ws, :a, %s, now(), 'manual', %s, %s, now())"
    cases = [
        (ok % ("'banana'", "false", "NULL"), "ck_lifecycle_events_stage"),
        (ok % ("'growing'", "true", "NULL"), "correction_has_reason"),
        (ok % ("'growing'", "true", "'short'"), "correction_has_reason"),
        (
            f"{base}VALUES (gen_random_uuid(), :ws, :a, 'growing', now(), 'robot', false, NULL, now())",
            "ck_lifecycle_events_source",
        ),
        (ok % ("'growing'", "false", "NULL"), None),  # a valid row is accepted
    ]
    with world.db() as db:
        for statement, constraint in cases:
            params = {"ws": team.ws, "a": a["id"]}
            if constraint is None:
                db.execute(text(statement), params)
                db.rollback()
                continue
            with pytest.raises(IntegrityError, match=constraint):
                db.execute(text(statement), params)
            db.rollback()
        with pytest.raises(IntegrityError, match="fk_lifecycle_events_asset"):  # another tenant's workspace id
            db.execute(text(ok % ("'growing'", "false", "NULL")), {"ws": team.other_ws, "a": a["id"]})
        db.rollback()


def test_back_dating_before_registration_needs_the_planting_date(api_for, team):
    """Without a planting date the first stage is dated when the asset was registered; an earlier change is refused
    with a message that says why (the fix is to give the planting date at registration)."""
    w = api_for(team.worker)
    a = make_asset(w)
    r = record(w, a["id"], "growing", entered_at=ago(days=10))
    assert r.status_code == 422 and r.json()["code"] == "entered_before_previous"
    dated = make_asset(w, label="Dated", planted_at="2020-01-01")
    assert record(w, dated["id"], "growing", entered_at=ago(days=10)).status_code == 201


# ------------------------------------------------------------------ real concurrency (PostgreSQL, separate connections)
#
# The usual `world` fixture runs every request on ONE shared connection inside an outer transaction (savepoints), so a
# row lock can neither contend nor be observed across requests there. These tests therefore build their own app whose
# requests use separate pooled connections that really commit. What they commit cannot be rolled back (and append-only
# tables refuse deletes), so they get a throwaway schema of their own, dropped afterwards: nothing they write can leak
# into the session schema that every other test shares (it once did: the scheduler then saw extra workspaces).


@pytest.fixture(scope="module")
def committed():
    import secrets
    from types import SimpleNamespace

    from alembic import command
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings, get_settings
    from app.core.db import build_engine, get_db
    from app.main import create_app
    from tests.conftest import JWT_SECRET, PG_MODE, postgis_url, seed_team
    from tests.pgsupport import SAFE_NAME, alembic_cfg, drop_test_schema

    if not PG_MODE:
        pytest.skip("PostgreSQL mode is not active")
    schema = f"gg_test_{secrets.token_hex(4)}"
    assert SAFE_NAME.match(schema)
    base = Settings(
        env="test", database_url=postgis_url, jwt_secret=JWT_SECRET, weather_provider="mock", _env_file=None
    )
    settings = base.model_copy(update={"db_schema": schema})
    admin = build_engine(base)
    engine = None
    try:
        command.upgrade(alembic_cfg(postgis_url, schema), "head")
        engine = build_engine(settings)
        team = seed_team(engine, settings)  # committed, in the private schema
        maker = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

        def _db():
            db = maker()
            try:
                yield db
            finally:
                db.close()

        app = create_app(settings)
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_settings] = lambda: settings
        base_path = f"/api/v1/workspaces/{team.ws}"
        headers = team.headers(team.worker)

        def post(path: str, body: dict):
            return TestClient(app).post(base_path + path, json=body, headers=headers)  # a client per call

        yield SimpleNamespace(team=team, maker=maker, post=post)
    finally:
        if engine is not None:
            engine.dispose()
        drop_test_schema(admin, schema)
        admin.dispose()


@pg
def test_a_stage_change_waits_for_the_row_lock_then_sees_what_was_committed_meanwhile(committed):
    """Another transaction holds the asset row. The request must WAIT (no stage check on stale data), and once the other
    transaction commits a move to 'growing' it must see that and refuse a second move to 'growing'."""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as Waiting

    from sqlalchemy import update

    asset = committed.post("/assets", {"label": "Locked", "kind": "tree"}).json()
    asset_id = UUID(asset["id"])
    holder = committed.maker()
    try:
        holder.execute(select(BiologicalAsset.id).where(BiologicalAsset.id == asset_id).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(committed.post, f"/assets/{asset_id}/lifecycle", {"stage": "growing"})
            with pytest.raises(Waiting):
                pending.result(
                    timeout=3
                )  # still blocked on the lock: without FOR UPDATE it would already have answered
            holder.execute(
                update(BiologicalAsset).where(BiologicalAsset.id == asset_id).values(current_stage="growing")
            )
            holder.commit()
            response = pending.result(timeout=60)
    finally:
        holder.rollback()
        holder.close()
    assert response.status_code == 409 and response.json()["code"] == "same_stage", response.text


@pg
def test_simultaneous_identical_changes_are_recorded_exactly_once(committed):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    asset = committed.post("/assets", {"label": "Raced", "kind": "tree"}).json()
    gate = Barrier(6)

    def go(_):
        gate.wait(timeout=30)
        return committed.post(f"/assets/{asset['id']}/lifecycle", {"stage": "growing"})

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(go, range(6)))
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409, 409], [r.text for r in responses]
    with committed.maker() as db:
        events = db.scalars(select(LifecycleEvent.stage).where(LifecycleEvent.asset_id == UUID(asset["id"]))).all()
    assert sorted(events) == ["growing", "planted"]  # one initial event, one change: never two 'growing'
