"""Every timestamp the API sends carries its offset (UTC), on SQLite as well as PostgreSQL.

SQLite (the local demo and these fast tests) stores timestamps without a zone; without UtcDateTime the API sent them
naive (`2026-10-23T12:52:00`) and browsers showed them as LOCAL time, hours off from the ones that had an offset."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from app.modules.observations.models import Observation
from tests.helpers import ago, make_asset, make_issue, observe


def _aware(value: str) -> bool:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None


def test_api_timestamps_carry_an_offset(api_for, team):
    m = api_for(team.manager)
    tree = make_asset(m)
    observe(m, tree["id"], observed_at=ago(hours=2))
    issue = make_issue(m, tree["id"])
    detail = m.get(f"/issues/{issue['id']}").json()
    stamps = [detail["opened_at"], detail["updated_at"], *(h["at"] for h in detail["history"])]
    stamps += [e["at"] for e in m.get(f"/assets/{tree['id']}/timeline").json()]
    stamps += [o["observed_at"] for o in m.get("/observations", params={"asset_id": tree["id"]}).json()["items"]]
    assert stamps and all(_aware(s) for s in stamps), stamps


def test_orm_objects_and_core_query_results_are_utc_aware(api_for, team, world):
    m = api_for(team.manager)
    tree = make_asset(m)
    observe(m, tree["id"])
    asset_id = uuid.UUID(tree["id"])
    with world.db() as db:
        obs = db.scalars(select(Observation).where(Observation.asset_id == asset_id)).first()
        latest = db.scalar(select(func.max(Observation.observed_at)).where(Observation.asset_id == asset_id))
    assert obs is not None and obs.observed_at.utcoffset() is not None and obs.created_at.utcoffset() is not None
    assert latest is not None and latest.utcoffset() is not None
