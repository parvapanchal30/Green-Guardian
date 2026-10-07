"""Opt-in profiler (GG_PROFILE=1). Not a correctness test: it prints where request time goes on the database in use.

    GG_PROFILE=1 TEST_DATABASE_URL=... pytest tests/test_profile.py -s

For each API request it reports wall time, number of SQL statements (savepoint bookkeeping counted separately, because
production sessions do not use savepoints), time spent waiting on the database, and repeated statement shapes that
suggest an N+1 pattern. It also measures the raw round-trip time of `SELECT 1` so statements x RTT can be compared with
what was actually observed.
"""

from __future__ import annotations

import os
import re
import statistics
import time
from collections import Counter

import pytest
from sqlalchemy import event, text

from tests.conftest import PG_MODE
from tests.helpers import ago

pytestmark = pytest.mark.skipif(os.getenv("GG_PROFILE") != "1", reason="set GG_PROFILE=1 to run the profiler")


def _shape(sql: str) -> str:
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"'[^']*'", "?", sql)
    sql = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b", "?", sql)
    sql = re.sub(r"IN \([^)]*\)", "IN (?)", sql)
    return sql[:160]


class Recorder:
    def __init__(self, engine):
        self.rows: list[tuple[str, float]] = []
        self._t0 = 0.0

        @event.listens_for(engine, "before_cursor_execute")
        def _before(conn, cursor, statement, params, context, executemany):
            self._t0 = time.perf_counter()

        @event.listens_for(engine, "after_cursor_execute")
        def _after(conn, cursor, statement, params, context, executemany):
            self.rows.append((statement, time.perf_counter() - self._t0))

    def reset(self):
        self.rows.clear()


def test_profile_the_operational_loop(world, api_for, team):
    engine = world.maker.kw["bind"]
    rec = Recorder(engine)
    mgr, worker = api_for(team.manager), api_for(team.worker)

    # raw round trip of the link in use
    with world.db() as db:
        samples = []
        for _ in range(12):
            t = time.perf_counter()
            db.execute(text("SELECT 1")).scalar()
            samples.append((time.perf_counter() - t) * 1000)
    rtt = statistics.median(samples)

    report: list[dict] = []

    def timed(label, fn):
        rec.reset()
        t = time.perf_counter()
        r = fn()
        wall = (time.perf_counter() - t) * 1000
        stmts = [s for s, _ in rec.rows]
        bookkeeping = sum(1 for s in stmts if s.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK TO")))
        db_ms = sum(d for _, d in rec.rows) * 1000
        shapes = Counter(_shape(s) for s in stmts if not s.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK TO")))
        repeated = {k: v for k, v in shapes.items() if v >= 3}
        report.append(dict(label=label, wall=wall, n=len(stmts), book=bookkeeping, db=db_ms, repeated=repeated))
        return r

    def json(r):
        assert r.status_code < 300, (r.status_code, r.text[:200])
        return r.json()

    zone = timed("POST /locations", lambda: json(mgr.post("/locations", {"name": "Z", "kind": "zone"})))
    asset = timed(
        "POST /assets",
        lambda: json(worker.post("/assets", {"label": "Neem", "kind": "tree", "location_id": zone["id"]})),
    )
    timed(
        "POST /observations (healthy, back-dated)",
        lambda: json(
            worker.post("/observations", {"asset_id": asset["id"], "health_score": 86, "observed_at": ago(days=8)})
        ),
    )
    worry = timed(
        "POST /observations (critical -> rule fires)",
        lambda: json(
            worker.post("/observations", {"asset_id": asset["id"], "health_score": 28, "symptoms": ["leaf_drop"]})
        ),
    )
    rec_id = worry["recommendations"][0]["id"]
    accepted = timed(
        "POST /recommendations/{id}/accept", lambda: json(mgr.post(f"/recommendations/{rec_id}/accept", {}))
    )
    iid = accepted["accepted_entity_id"]
    timed("GET /issues/{id}", lambda: json(mgr.get(f"/issues/{iid}")))
    timed(
        "POST /issues/{id}/transitions",
        lambda: json(mgr.post(f"/issues/{iid}/transitions", {"to_state": "investigating"})),
    )
    task = timed(
        "POST /tasks",
        lambda: json(
            mgr.post("/tasks", {"title": "Treat", "type": "treat", "issue_id": iid, "assignee_id": str(team.worker.id)})
        ),
    )
    timed(
        "POST /tasks/{id}/transitions (start)",
        lambda: json(worker.post(f"/tasks/{task['id']}/transitions", {"to_status": "in_progress"})),
    )
    timed(
        "POST /tasks/{id}/transitions (done + follow-up)",
        lambda: json(
            worker.post(f"/tasks/{task['id']}/transitions", {"to_status": "done", "observation": {"health_score": 70}})
        ),
    )
    timed(
        "POST /issues/{id}/transitions (resolve)",
        lambda: json(
            mgr.post(
                f"/issues/{iid}/transitions",
                {"to_state": "resolved", "resolution": {"outcome": "fixed", "notes": "ok"}},
            )
        ),
    )
    timed("GET /assets/{id}", lambda: json(mgr.get(f"/assets/{asset['id']}")))
    timed("GET /assets (list)", lambda: json(mgr.get("/assets")))
    timed("GET /issues (list)", lambda: json(mgr.get("/issues")))
    timed("GET /tasks (list)", lambda: json(mgr.get("/tasks")))
    timed("GET /assets/{id}/timeline", lambda: json(mgr.get(f"/assets/{asset['id']}/timeline")))
    timed("POST /agent/run", lambda: json(mgr.post("/agent/run")))

    total_wall = sum(r["wall"] for r in report)
    total_n = sum(r["n"] for r in report)
    total_book = sum(r["book"] for r in report)
    total_db = sum(r["db"] for r in report)
    print(f"\n=== PROFILE ({'PostgreSQL' if PG_MODE else 'SQLite'}) ===  SELECT 1 round trip: median {rtt:.0f} ms")
    print(f"{'request':52} {'wall ms':>8} {'stmts':>6} {'(sp)':>5} {'db ms':>8} {'app ms':>7}")
    for r in report:
        print(f"{r['label']:52} {r['wall']:8.0f} {r['n']:6d} {r['book']:5d} {r['db']:8.0f} {r['wall'] - r['db']:7.0f}")
    print(f"{'TOTAL':52} {total_wall:8.0f} {total_n:6d} {total_book:5d} {total_db:8.0f} {total_wall - total_db:7.0f}")
    print(
        f"\nrequests: {len(report)} | statements: {total_n} ({total_book} savepoint bookkeeping) | "
        f"expected from statements x RTT: {total_n * rtt:.0f} ms | observed: {total_wall:.0f} ms"
    )
    print(f"share of wall time spent waiting on the database: {100 * total_db / total_wall:.0f}%")
    n1 = [(r["label"], k, v) for r in report for k, v in r["repeated"].items()]
    print("repeated statement shapes (>=3x in one request):", n1 or "none")
