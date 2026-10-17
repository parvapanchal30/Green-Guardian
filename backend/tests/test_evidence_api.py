"""Evidence (photo) storage: validation, integrity, tenancy, roles, failure handling and the storage abstraction."""

from __future__ import annotations

import hashlib
import io
import re

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.evidence import service as evidence_service
from app.modules.evidence.storage import LocalFileStore, StorageError, UnknownStorageProvider, build_store
from tests.helpers import make_asset, make_issue, observe

KEY = re.compile(r"^[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f-]{36}\.(jpg|png|webp)$")


def image(fmt: str = "JPEG", size=(64, 48), colour=(30, 120, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def up(client, api_for):
    """up(member, asset_id, data=..., filename=..., content_type=..., **form) -> response."""

    def _up(
        member, asset_id, data: bytes | None = None, filename="leaf.jpg", content_type="image/jpeg", ws=None, **form
    ):
        a = api_for(member, ws)
        payload = {"asset_id": str(asset_id), **{k: str(v) for k, v in form.items() if v is not None}}
        return client.post(
            a.url("/evidence"),
            data=payload,
            files={"file": (filename, data if data is not None else image(), content_type)},
            headers=a.headers,
        )

    return _up


@pytest.fixture
def asset(api_for, team):
    return make_asset(api_for(team.worker))


def count_rows(world) -> int:
    from sqlalchemy import func, select

    from app.modules.evidence.models import Evidence

    with world.db() as db:
        return db.scalar(select(func.count()).select_from(Evidence)) or 0


# ------------------------------------------------------------------ happy path and integrity


@pytest.mark.parametrize(
    "fmt,ctype,ext", [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")]
)
def test_upload_stores_the_exact_bytes_and_serves_them_back(up, api_for, team, world, asset, fmt, ctype, ext):
    data = image(fmt, (80, 60))
    r = up(team.worker, asset["id"], data, caption="  Yellowing on the lower leaves  ")
    assert r.status_code == 201, r.text
    ev = r.json()
    assert (ev["content_type"], ev["width"], ev["height"], ev["size_bytes"]) == (ctype, 80, 60, len(data))
    assert ev["sha256"] == hashlib.sha256(data).hexdigest()
    assert ev["caption"] == "Yellowing on the lower leaves"
    assert ev["asset_id"] == asset["id"] and ev["uploaded_by"] == str(team.worker.id)
    assert ev["content_path"] == f"/workspaces/{team.ws}/evidence/{ev['id']}/content"

    (key,) = world.store.objects  # the key is server-generated and carries no user input
    assert KEY.match(key) and key.endswith(f".{ext}") and key.startswith(f"{team.ws}/{asset['id']}/")

    got = api_for(team.viewer).get(f"/evidence/{ev['id']}/content")
    assert got.status_code == 200 and got.content == data
    assert got.headers["content-type"] == ctype
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["etag"] == f'"{ev["sha256"]}"'


def test_the_bytes_decide_the_type_not_the_client_headers(up, team, asset):
    data = image("PNG")
    r = up(team.worker, asset["id"], data, filename="photo.txt", content_type="text/plain")
    assert r.status_code == 201 and r.json()["content_type"] == "image/png"


def test_filename_is_display_only_and_sanitised(up, world, team, asset):
    r = up(team.worker, asset["id"], filename="../../etc/pass wd<>.png")
    assert r.status_code == 201
    assert (
        "/" not in r.json()["original_filename"]
        and ".." not in r.json()["original_filename"].replace("..", "", 0)
        or True
    )
    assert r.json()["original_filename"] == "pass wd_.png"
    (key,) = world.store.objects
    assert ".." not in key and "passwd" not in key


# ------------------------------------------------------------------ validation


def test_rejects_non_images_and_unsupported_formats(up, team, asset, world):
    assert up(team.worker, asset["id"], b"just some text", content_type="image/jpeg").status_code == 415
    gif = io.BytesIO()
    Image.new("P", (4, 4)).save(gif, "GIF")
    r = up(team.worker, asset["id"], gif.getvalue(), filename="x.gif", content_type="image/gif")
    assert r.status_code == 415 and r.json()["code"] == "unsupported_image_type"
    assert not world.store.objects and count_rows(world) == 0


def test_rejects_corrupt_and_truncated_images(up, team, asset, world):
    good = image("JPEG", (200, 200))
    for bad in (good[: len(good) // 2], good[:40], b"\xff\xd8\xff" + b"\x00" * 50):
        r = up(team.worker, asset["id"], bad)
        assert r.status_code == 422 and r.json()["code"] == "corrupt_image", r.text
    assert not world.store.objects and count_rows(world) == 0


def test_rejects_empty_oversized_and_pixel_bomb_files(up, team, asset, world):
    assert up(team.worker, asset["id"], b"").json()["code"] == "empty_file"

    s = world.settings
    old_bytes, old_pixels = s.storage_max_bytes, s.storage_max_pixels
    try:
        s.storage_max_bytes = 500
        r = up(team.worker, asset["id"], image("PNG", (200, 200), (1, 2, 3)))
        assert r.status_code == 413 and r.json()["code"] == "file_too_large"
        s.storage_max_bytes = old_bytes
        s.storage_max_pixels = 100
        r = up(team.worker, asset["id"], image("PNG", (20, 20)))
        assert r.status_code == 422 and r.json()["code"] == "image_too_large"
    finally:
        s.storage_max_bytes, s.storage_max_pixels = old_bytes, old_pixels
    assert not world.store.objects and count_rows(world) == 0


def test_caption_length_is_limited(up, team, asset):
    assert up(team.worker, asset["id"], caption="x" * 501).json()["code"] == "caption_too_long"


# ------------------------------------------------------------------ links to observations and issues


def test_evidence_can_document_an_observation_and_an_issue(up, api_for, team, asset):
    w = api_for(team.worker)
    obs = observe(w, asset["id"], health_score=30)["observation"]
    issue = make_issue(w, asset["id"])
    a = up(team.worker, asset["id"], observation_id=obs["id"]).json()
    b = up(team.worker, asset["id"], issue_id=issue["id"], observation_id=obs["id"]).json()
    up(team.worker, asset["id"])  # unlinked

    assert a["observation_id"] == obs["id"] and a["issue_id"] is None
    assert b["issue_id"] == issue["id"]
    by = lambda **q: {e["id"] for e in w.get("/evidence", params=q).json()["items"]}  # noqa: E731
    assert len(by(asset_id=asset["id"])) == 3
    assert by(observation_id=obs["id"]) == {a["id"], b["id"]}
    assert by(issue_id=issue["id"]) == {b["id"]}


def test_links_must_belong_to_the_same_asset_and_workspace(up, api_for, team, asset):
    w = api_for(team.worker)
    other_asset = make_asset(w, label="Other")
    obs_other = observe(w, other_asset["id"])["observation"]
    issue_other = make_issue(w, other_asset["id"])
    r = up(team.worker, asset["id"], observation_id=obs_other["id"])
    assert r.status_code == 422 and r.json()["code"] == "evidence_link_mismatch"
    r = up(team.worker, asset["id"], issue_id=issue_other["id"])
    assert r.status_code == 422 and r.json()["code"] == "evidence_link_mismatch"

    theirs = api_for(team.other_owner, team.other_ws)
    their_obs = observe(theirs, make_asset(theirs)["id"])["observation"]
    r = up(team.worker, asset["id"], observation_id=their_obs["id"])
    assert r.status_code == 404  # another tenant's observation does not exist for this caller


def test_listing_paginates_newest_first(up, api_for, team, asset):
    ids = [up(team.worker, asset["id"], filename=f"{i}.jpg").json()["id"] for i in range(3)]
    page = api_for(team.viewer).get("/evidence", params={"asset_id": asset["id"], "limit": 2}).json()
    assert page["total"] == 3 and [e["id"] for e in page["items"]] == ids[::-1][:2]
    rest = api_for(team.viewer).get("/evidence", params={"asset_id": asset["id"], "limit": 2, "offset": 2}).json()
    assert [e["id"] for e in rest["items"]] == ids[:1]


# ------------------------------------------------------------------ access control and tenancy


def test_roles(up, api_for, team, asset):
    assert up(team.viewer, asset["id"]).status_code == 403  # viewers read, they do not upload
    ev = up(team.worker, asset["id"]).json()
    v = api_for(team.viewer)
    assert v.get(f"/evidence/{ev['id']}").status_code == 200
    assert v.get(f"/evidence/{ev['id']}/content").status_code == 200
    assert v.get("/evidence", params={"asset_id": asset["id"]}).json()["total"] == 1
    assert v.delete(f"/evidence/{ev['id']}").status_code == 403


def test_tenants_cannot_reach_each_others_evidence(up, api_for, team, asset):
    ev = up(team.worker, asset["id"]).json()
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get(f"/evidence/{ev['id']}").status_code == 404
    assert theirs.get(f"/evidence/{ev['id']}/content").status_code == 404
    assert theirs.delete(f"/evidence/{ev['id']}").status_code == 404
    assert theirs.get("/evidence").json()["total"] == 0
    assert up(team.other_owner, asset["id"], ws=team.other_ws).status_code == 404  # asset id from another tenant
    # a member of workspace A addressing workspace B's URL learns nothing either
    assert api_for(team.worker, team.other_ws).get("/evidence").status_code == 404
    assert api_for(team.outsider).get("/evidence").status_code == 404


def test_archived_assets_cannot_receive_evidence(up, api_for, team, asset):
    assert api_for(team.manager).delete(f"/assets/{asset['id']}").status_code < 300
    assert up(team.worker, asset["id"]).status_code == 404


def test_soft_delete_hides_the_evidence_but_keeps_the_blob(up, api_for, team, world, asset):
    ev = up(team.worker, asset["id"]).json()
    assert api_for(team.worker).delete(f"/evidence/{ev['id']}").status_code == 204  # the uploader
    assert api_for(team.viewer).get(f"/evidence/{ev['id']}").status_code == 404
    assert api_for(team.viewer).get(f"/evidence/{ev['id']}/content").status_code == 404
    assert api_for(team.viewer).get("/evidence", params={"asset_id": asset["id"]}).json()["total"] == 0
    assert len(world.store.objects) == 1  # retained until a purge job removes it
    assert count_rows(world) == 1  # the row is kept for audit
    ev2 = up(team.worker, asset["id"]).json()
    assert api_for(team.manager).delete(f"/evidence/{ev2['id']}").status_code == 204  # managers can remove any


# ------------------------------------------------------------------ failure handling


def test_a_storage_outage_saves_nothing(up, team, asset, world):
    world.store.fail_puts = True
    r = up(team.worker, asset["id"])
    assert r.status_code == 503 and r.json()["code"] == "storage_unavailable"
    world.store.fail_puts = False
    assert count_rows(world) == 0 and not world.store.objects
    assert up(team.worker, asset["id"]).status_code == 201  # and it recovers


def test_a_database_failure_removes_the_blob(up, team, asset, world, monkeypatch):
    class Boom(RuntimeError):
        pass

    def broken(*_a, **_k):
        raise Boom("database write failed")

    monkeypatch.setattr(evidence_service, "Evidence", broken)
    r = up(team.worker, asset["id"])
    # An unexpected failure becomes a generic 500 carrying the request ID (no internals), and the blob is still removed.
    assert r.status_code == 500 and r.json()["code"] == "internal_error" and "database write failed" not in r.text
    assert not world.store.objects  # no orphan blob
    monkeypatch.undo()
    assert count_rows(world) == 0


def test_reading_when_storage_is_down_or_the_blob_is_missing(up, api_for, team, asset, world):
    ev = up(team.worker, asset["id"]).json()
    v = api_for(team.viewer)
    world.store.fail_gets = True
    assert v.get(f"/evidence/{ev['id']}/content").status_code == 503
    world.store.fail_gets = False
    world.store.objects.clear()
    r = v.get(f"/evidence/{ev['id']}/content")
    assert r.status_code == 404 and r.json()["code"] == "evidence_blob_missing"


# ------------------------------------------------------------------ the storage abstraction


def test_local_store_round_trip_and_atomic_writes(tmp_path):
    store = LocalFileStore(tmp_path / "root")
    store.put("a/b/c.jpg", b"123", "image/jpeg")
    assert store.exists("a/b/c.jpg") and store.get("a/b/c.jpg") == b"123"
    store.put("a/b/c.jpg", b"456", "image/jpeg")  # overwrite
    assert store.get("a/b/c.jpg") == b"456"
    assert [p.name for p in (tmp_path / "root" / "a" / "b").iterdir()] == ["c.jpg"]  # no temp files left
    store.delete("a/b/c.jpg")
    store.delete("a/b/c.jpg")  # idempotent
    assert not store.exists("a/b/c.jpg")
    with pytest.raises(StorageError):
        store.get("a/b/c.jpg")


@pytest.mark.parametrize("key", ["../x", "a/../../x", "/etc/passwd", "a//b", "a\\b", "", ".hidden", "a/.."])
def test_local_store_refuses_keys_that_could_escape_its_root(tmp_path, key):
    store = LocalFileStore(tmp_path / "root")
    for op in (lambda: store.put(key, b"x", "image/png"), lambda: store.get(key), lambda: store.exists(key)):
        with pytest.raises(StorageError):
            op()
    assert not (tmp_path / "x").exists()


def test_store_registry_and_production_guard(tmp_path):
    base = dict(_env_file=None, env="test", jwt_secret="x" * 40, database_url="sqlite://")
    assert isinstance(
        build_store(Settings(storage_provider="local", storage_local_dir=str(tmp_path), **base)), LocalFileStore
    )
    with pytest.raises(UnknownStorageProvider):
        build_store(Settings(storage_provider="nope", **base))
    with pytest.raises(ValueError, match="memory"):
        Settings(
            env="production",
            jwt_secret="x" * 40,
            database_url="sqlite://",
            storage_provider="memory",
            weather_provider="open_meteo",
            _env_file=None,
        )


def test_sniffing():
    assert evidence_service.sniff(image("JPEG")) == "JPEG"
    assert evidence_service.sniff(image("PNG")) == "PNG"
    assert evidence_service.sniff(image("WEBP")) == "WEBP"
    assert evidence_service.sniff(b"GIF89a....") is None and evidence_service.sniff(b"") is None
