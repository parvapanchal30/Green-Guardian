"""Build a small, realistic DEMO database for looking at the product locally.

    python -m app.tools.demo_seed

It refuses to run unless DATABASE_URL is a local SQLite *demo* file, so it can never write to the Supabase development
database or any hosted database. It creates the schema with the real Alembic migrations, seeds a few species, then
populates two workspaces THROUGH THE REAL API (so everything shown went through the same rules, roles and audit trail as
production code): a campus green-cover workspace and a mixed-crop farm, with assets, observations, lifecycle changes,
a photo, issues, tasks, agent suggestions and harvests. Demo accounts get fresh random passwords, written to the demo
folder and printed once. Nothing here is real data.
"""

from __future__ import annotations

import io
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker, reset_engine_for_tests
from app.main import create_app
from app.models import Species, User

BACKEND = Path(__file__).resolve().parents[2]
API = "/api/v1"
SPECIES = [
    ("tree", "Neem"),
    ("tree", "Mango"),
    ("tree", "Banyan"),
    ("tree", "Gulmohar"),
    ("crop", "Tomato"),
    ("crop", "Wheat"),
    ("crop", "Okra"),
]


def ago(**kw) -> str:
    return (datetime.now(UTC) - timedelta(**kw)).isoformat()


class Person:
    def __init__(self, client: TestClient, email: str, name: str, password: str):
        self.client, self.email, self.name, self.password = client, email, name, password
        r = client.post(f"{API}/auth/register", json={"email": email, "password": password, "name": name})
        assert r.status_code == 201, r.text
        tokens = client.post(f"{API}/auth/login", json={"email": email, "password": password}).json()
        self.headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    def call(self, method: str, path: str, expect: int | tuple[int, ...] = (200, 201), **kw):
        r = self.client.request(method, f"{API}{path}", headers=self.headers, **kw)
        ok = (expect,) if isinstance(expect, int) else expect
        if r.status_code not in ok:
            raise SystemExit(f"demo seed failed: {method} {path} -> {r.status_code} {r.text[:300]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    def post(self, path, body=None, **kw):
        return self.call("POST", path, json=body, **kw)

    def get(self, path, **kw):
        return self.call("GET", path, **kw)


def photo(label: str, colour: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (640, 420), colour)
    ImageDraw.Draw(img).text((20, 20), f"DEMO PHOTO: {label}", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def check_target() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite") or "demo" not in url or ":memory:" in url:
        raise SystemExit(
            "refusing: DATABASE_URL must be a local SQLite demo file (for example sqlite+pysqlite:///var/demo/demo.db). "
            "This tool never writes to a hosted or development database."
        )
    return url


def migrate(url: str) -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def main() -> int:
    url = check_target()
    reset_engine_for_tests()
    build_engine(get_settings()).dispose()
    migrate(url)
    with get_sessionmaker()() as db:
        if db.scalar(select(func.count()).select_from(User)):
            raise SystemExit("this demo database already has users; run demo.bat --fresh to start again")
        for category, name in SPECIES:
            db.add(Species(workspace_id=None, category=category, common_name=name, attributes={"seed": True}))
        db.commit()

    app = create_app()
    client = TestClient(app)
    pw = {k: secrets.token_urlsafe(12) for k in ("owner", "worker", "viewer")}
    owner = Person(client, "demo.owner@example.com", "Asha (owner)", pw["owner"])
    worker = Person(client, "demo.worker@example.com", "Ravi (field worker)", pw["worker"])
    viewer = Person(client, "demo.viewer@example.com", "Meera (viewer)", pw["viewer"])

    # ------------------------------------------------------------------ workspace 1: Green Management
    campus = owner.post("/workspaces", {"name": "Riverside Campus Green Cover", "mode": "green_management"})["id"]
    w = f"/workspaces/{campus}"
    owner.post(f"{w}/members", {"email": worker.email, "role": "worker"})
    owner.post(f"{w}/members", {"email": viewer.email, "role": "viewer"})
    species = {s["common_name"]: s["id"] for s in owner.get(f"{w}/species?limit=100")["items"]}
    site = owner.post(
        f"{w}/locations", {"name": "Main campus", "kind": "site", "latitude": 19.1334, "longitude": 72.9133}
    )
    north = owner.post(
        f"{w}/locations",
        {"name": "North avenue", "kind": "zone", "parent_id": site["id"], "latitude": 19.1352, "longitude": 72.9140},
    )
    garden = owner.post(
        f"{w}/locations",
        {
            "name": "Botanical garden",
            "kind": "zone",
            "parent_id": site["id"],
            "latitude": 19.1311,
            "longitude": 72.9121,
        },
    )

    def tree(label, sp, loc, lat, lon, planted, stage=None, tag=None):
        body = {
            "label": label,
            "kind": "tree",
            "species_id": species[sp],
            "location_id": loc["id"],
            "latitude": lat,
            "longitude": lon,
            "planted_at": planted,
            "tag_code": tag,
        }
        if stage:
            body["stage"] = stage
        return owner.post(f"{w}/assets", {k: v for k, v in body.items() if v is not None})

    neem1 = tree("Neem #101", "Neem", north, 19.1353, 72.9138, "2019-07-10", "mature", "N-101")
    neem2 = tree("Neem #102", "Neem", north, 19.1355, 72.9143, "2019-07-10", "mature", "N-102")
    mango = tree("Mango #07", "Mango", garden, 19.1309, 72.9119, "2021-08-02", "growing", "M-007")
    banyan = tree("Banyan #01", "Banyan", garden, 19.1315, 72.9125, "2005-06-20", "maintained", "B-001")
    gulmohar = tree("Gulmohar #12", "Gulmohar", north, 19.1349, 72.9147, "2022-06-15", "growing", "G-012")
    sapling = tree("Neem sapling #201", "Neem", garden, 19.1313, 72.9129, "2026-08-20", None, "N-201")
    lost = tree("Gulmohar #09", "Gulmohar", north, 19.1347, 72.9135, "2020-07-01", "growing", "G-009")

    def observe(asset, score, days_ago, symptoms=None, notes=None, who=worker):
        body = {"asset_id": asset["id"], "health_score": score, "observed_at": ago(days=days_ago)}
        if symptoms:
            body["symptoms"] = symptoms
        if notes:
            body["notes"] = notes
        return who.post(f"{w}/observations", body)

    for d, s in ((60, 86), (45, 84), (30, 82), (14, 80), (3, 81)):
        observe(neem1, s, d)
    for d, s in ((50, 78), (35, 66), (20, 48), (9, 31)):
        observe(
            neem2,
            s,
            d,
            ["leaf_yellowing", "dieback"] if s < 50 else None,
            "Crown thinning on the north side" if s < 50 else None,
        )
    for d, s in ((40, 90), (12, 89)):
        observe(mango, s, d)
    observe(banyan, 74, 28, None, "Aerial roots need trimming near the path")
    observe(sapling, 92, 2, None, "Staked and watered after planting")
    observe(gulmohar, 83, 70)  # old reading: an inspection is due
    observe(lost, 22, 25, ["bark_cracking"], "Trunk split after the storm")
    owner.post(
        f"{w}/assets/{lost['id']}/lifecycle",
        {"stage": "dead", "note": "Confirmed dead after the storm; stump to be removed"},
    )
    owner.post(
        f"{w}/assets/{banyan['id']}/lifecycle", {"stage": "health_monitoring", "note": "Heritage tree: monthly checks"}
    )

    owner.post(
        f"{w}/evidence",
        data={"asset_id": neem2["id"], "caption": "Dieback on the north side"},
        files={"file": ("dieback.jpg", photo("Neem #102 dieback", (110, 70, 40)), "image/jpeg")},
    )
    issue = owner.post(
        f"{w}/issues",
        {
            "title": "Neem #102 crown dieback",
            "asset_id": neem2["id"],
            "category": "disease",
            "severity": "high",
            "description": "Progressive leaf yellowing and dieback over eight weeks.",
        },
    )
    owner.post(
        f"{w}/tasks",
        {
            "title": "Inspect Neem #102 and sample the bark",
            "type": "inspect",
            "issue_id": issue["id"],
            "priority": "p2",
            "assignee_id": worker_id(owner, w, worker.email),
            "due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    owner.post(
        f"{w}/tasks",
        {"title": "Remove the stump of Gulmohar #09", "type": "replace", "asset_id": lost["id"], "priority": "p3"},
    )
    owner.post(f"{w}/agent/run", {})  # the rule-based agent looks at everything above and suggests next steps

    # ------------------------------------------------------------------ workspace 2: Agricultural Production
    farm = owner.post("/workspaces", {"name": "Green Valley Farm", "mode": "agricultural_production"})["id"]
    f = f"/workspaces/{farm}"
    owner.post(f"{f}/members", {"email": worker.email, "role": "worker"})
    farm_site = owner.post(
        f"{f}/locations", {"name": "Valley fields", "kind": "site", "latitude": 18.5204, "longitude": 73.8567}
    )
    species_f = {s["common_name"]: s["id"] for s in owner.get(f"{f}/species?limit=100")["items"]}

    def batch(label, sp, count, stage, planted, lat, lon):
        return owner.post(
            f"{f}/assets",
            {
                "label": label,
                "kind": "crop_batch",
                "tracking_mode": "population",
                "estimated_count": count,
                "species_id": species_f[sp],
                "location_id": farm_site["id"],
                "latitude": lat,
                "longitude": lon,
                "planted_at": planted,
                "stage": stage,
            },
        )

    tomato = batch(
        "Tomato block A",
        "Tomato",
        1200,
        "fruiting",
        (datetime.now(UTC) - timedelta(days=95)).date().isoformat(),
        18.5206,
        73.8561,
    )
    wheat = batch(
        "Wheat field 3",
        "Wheat",
        40000,
        "vegetative",
        (datetime.now(UTC) - timedelta(days=60)).date().isoformat(),
        18.5198,
        73.8575,
    )
    okra = batch(
        "Okra block B",
        "Okra",
        800,
        "harvest",
        (datetime.now(UTC) - timedelta(days=70)).date().isoformat(),
        18.5211,
        73.8570,
    )
    failed = batch(
        "Okra block C",
        "Okra",
        600,
        "germination",
        (datetime.now(UTC) - timedelta(days=25)).date().isoformat(),
        18.5215,
        73.8579,
    )
    for d, s in ((30, 88), (14, 85), (4, 79)):
        worker.post(f"{f}/observations", {"asset_id": tomato["id"], "health_score": s, "observed_at": ago(days=d)})
    worker.post(f"{f}/observations", {"asset_id": wheat["id"], "health_score": 91, "observed_at": ago(days=6)})
    worker.post(
        f"{f}/observations",
        {"asset_id": failed["id"], "health_score": 20, "symptoms": ["damping_off"], "observed_at": ago(days=5)},
    )
    owner.post(
        f"{f}/assets/{failed['id']}/lifecycle", {"stage": "failed", "note": "Damping-off across the whole block"}
    )
    for qty, unit, days, grade in ((140, "kg", 21, "A"), (165, "kg", 14, "A"), (180, "kg", 7, "B"), (60, "kg", 2, "A")):
        worker.post(
            f"{f}/assets/{okra['id']}/harvests",
            {"quantity": qty, "unit": unit, "harvested_at": ago(days=days), "grade": grade},
        )
    tomato_first = worker.post(
        f"{f}/assets/{tomato['id']}/harvests",
        {"quantity": 0.35, "unit": "t", "harvested_at": ago(days=9), "note": "First picking"},
    )
    owner.post(
        f"{f}/assets/{tomato['id']}/harvests/{tomato_first['history'][0]['id']}/correct",
        {"quantity": 0.32, "unit": "t", "note": "Re-weighed on the calibrated scale"},
    )
    owner.post(f"{f}/agent/run", {})

    out = BACKEND / "var" / "demo" / "DEMO_LOGIN.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "GreenGuardian local DEMO accounts (throwaway data in backend/var/demo; nothing here is real)",
        "",
        f"Owner   {owner.email}   {pw['owner']}   (everything: both workspaces)",
        f"Worker  {worker.email}   {pw['worker']}   (can record; cannot decide or correct)",
        f"Viewer  {viewer.email}   {pw['viewer']}   (read only; campus workspace)",
        "",
        "Workspaces: 'Riverside Campus Green Cover' (Green Management), 'Green Valley Farm' (Agricultural Production)",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf8")
    print("\n".join(lines))
    return 0


def worker_id(owner: Person, ws_path: str, email: str) -> str:
    members = owner.get(f"{ws_path}/members")
    return next(m["user_id"] for m in members if m["email"] == email)


if __name__ == "__main__":
    sys.exit(main())
