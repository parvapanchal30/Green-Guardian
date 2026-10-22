"""Orphan-blob reconciliation: classification, conservative deletion, safety brakes, races, audit and tenant safety.

Runs against all three stores (in-memory, local disk, simulated S3). Simulated S3 is NOT proof of behaviour on a real
provider, and nothing here touches a real bucket."""

from __future__ import annotations

import io
import json
import os
import uuid
from datetime import timedelta

import boto3
import pytest
from moto import mock_aws
from PIL import Image
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.timeutil import utcnow
from app.modules.audit.models import AuditEvent
from app.modules.evidence import reconcile
from app.modules.evidence.models import Evidence
from app.modules.evidence.storage import (
    LocalFileStore,
    MemoryObjectStore,
    StorageError,
    build_store,
    get_object_store,
)
from app.tools import evidence_reconcile
from tests.helpers import make_asset

DAYS2 = timedelta(days=2)


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (10, 100, 30)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(params=["memory", "local", "s3"])
def store(request, tmp_path, monkeypatch):
    if request.param == "memory":
        yield MemoryObjectStore()
    elif request.param == "local":
        yield LocalFileStore(tmp_path / "blobs")
    else:
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
        with mock_aws():
            boto3.client("s3", region_name="eu-central-1").create_bucket(
                Bucket="gg-recon", CreateBucketConfiguration={"LocationConstraint": "eu-central-1"}
            )
            yield build_store(
                Settings(
                    _env_file=None,
                    env="test",
                    jwt_secret="x" * 40,
                    database_url="sqlite://",
                    storage_provider="s3",
                    storage_s3_bucket="gg-recon",
                    storage_s3_region="eu-central-1",
                    storage_s3_prefix="evidence",
                )
            )


@pytest.fixture
def env(store, world, client, api_for, team):
    world.app.dependency_overrides[get_object_store] = lambda: store
    asset = make_asset(api_for(team.worker))

    class Env:
        def __init__(self):
            self.store = store

        def upload(self) -> dict:
            a = api_for(team.worker)
            r = client.post(
                a.url("/evidence"),
                data={"asset_id": str(asset["id"])},
                files={"file": ("l.jpg", jpeg(), "image/jpeg")},
                headers=a.headers,
            )
            assert r.status_code == 201, r.text
            return r.json()

        def orphan(self, ws=None) -> str:
            key = f"{ws or team.ws}/{uuid.uuid4()}/{uuid.uuid4()}.jpg"
            store.put(key, b"orphaned-bytes", "image/jpeg")
            return key

        def keys(self) -> set[str]:
            return {o.key for o in store.list()}

        def run(self, **kw):
            with world.maker() as db:
                return reconcile.reconcile(db, store, now=utcnow() + DAYS2, **kw)

    return Env()


# ------------------------------------------------------------------ the store listing


def test_every_store_lists_its_objects_with_size_and_a_utc_time(store):
    store.put("a/b/c.jpg", b"12345", "image/jpeg")
    (o,) = list(store.list())
    assert (o.key, o.size_bytes) == ("a/b/c.jpg", 5) and o.modified.utcoffset() == timedelta(0)
    assert abs(utcnow() - o.modified) < timedelta(minutes=5)


def test_local_store_listing_skips_uploads_in_flight(tmp_path):
    s = LocalFileStore(tmp_path / "r")
    s.put("a/b.jpg", b"1", "image/jpeg")
    (tmp_path / "r" / "a" / ".upload-xyz").write_bytes(b"partial")
    assert [o.key for o in s.list()] == ["a/b.jpg"]


# ------------------------------------------------------------------ classification


def test_dry_run_reports_but_never_deletes(env):
    ev = env.upload()
    orphan = env.orphan()
    r = env.run()
    assert (r.orphans, r.referenced, r.deleted) == (1, 1, 0) and r.orphan_examples == [orphan]
    assert r.as_dict()["dry_run"] is True and orphan in env.keys() and ev["id"]


def test_delete_removes_only_old_unreferenced_recognised_objects(env, store):
    kept = env.upload()
    orphan = env.orphan()
    odd = "somebody-elses/file.jpg"
    store.put(odd, b"not ours", "image/jpeg")
    r = env.run(delete=True, max_orphan_fraction=1.0)
    assert (r.deleted, r.referenced, r.unrecognised) == (1, 1, 1) and r.unrecognised_examples == [odd]
    remaining = env.keys()
    assert orphan not in remaining and odd in remaining and len(remaining) == 2 and kept["id"]


def test_recent_objects_are_left_alone(env, world):
    orphan = env.orphan()
    with world.maker() as db:  # "now" is the real now: the object is seconds old
        r = reconcile.reconcile(db, env.store, delete=True, now=utcnow(), min_age=timedelta(hours=24))
    assert (r.too_recent, r.orphans, r.deleted) == (1, 0, 0) and orphan in env.keys()


def test_soft_deleted_evidence_keeps_its_blob(env, api_for, team):
    ev = env.upload()
    assert api_for(team.worker).delete(f"/evidence/{ev['id']}").status_code == 204
    r = env.run(delete=True, max_orphan_fraction=1.0)
    assert (r.referenced, r.orphans, r.deleted) == (1, 0, 0) and len(env.keys()) == 1


def test_the_run_is_idempotent(env):
    env.upload()
    env.orphan()
    first = env.run(delete=True, max_orphan_fraction=1.0)
    second = env.run(delete=True, max_orphan_fraction=1.0)
    assert first.deleted == 1 and (second.deleted, second.orphans, second.referenced) == (0, 0, 1)


def test_missing_blobs_are_reported_not_repaired(env, store):
    ev = env.upload()
    (key,) = env.keys()
    store.delete(key)
    r = env.run()
    assert r.missing_blobs == 1 and r.missing_examples == [f"{uuid.UUID(ev['id'])}:{key}"]


# ------------------------------------------------------------------ safety rules


def test_min_age_cannot_be_lowered_below_an_hour(env):
    with pytest.raises(ValueError, match="one hour"):
        env.run(min_age=timedelta(minutes=59))


def test_refuses_when_the_database_has_no_evidence_at_all(env):
    env.orphan()
    with pytest.raises(reconcile.RefusedToDelete, match="wrong database"):
        env.run(delete=True)
    assert len(env.keys()) == 1


def test_refuses_when_too_large_a_share_looks_orphaned(env):
    env.upload()
    for _ in range(6):
        env.orphan()
    with pytest.raises(reconcile.RefusedToDelete, match="more than 20%"):
        env.run(delete=True)
    assert len(env.keys()) == 7
    assert env.run(delete=True, max_orphan_fraction=1.0).deleted == 6  # an explicit, informed override


def test_a_run_deletes_at_most_max_delete(env):
    env.upload()
    for _ in range(4):
        env.orphan()
    r = env.run(delete=True, max_delete=2, max_orphan_fraction=1.0)
    assert (r.orphans, r.deleted) == (4, 2) and len(env.keys()) == 3


def test_a_row_committed_after_the_listing_wins_the_race(env, store, world):
    """The reference is re-checked right before each delete: an upload that commits between listing and deleting is kept."""
    env.upload()
    key = env.orphan()
    asset_row = make_row_for(world, key)
    calls = {"n": 0}

    def referenced_then_appears(db, keys):
        calls["n"] += 1
        if calls["n"] == 2:  # first call = the scan; second = the pre-delete re-check, after the "other upload" commits
            db.add(asset_row)
            db.commit()
        return reconcile._referenced(db, keys)

    with world.maker() as db:
        r = reconcile.reconcile(
            db,
            store,
            delete=True,
            now=utcnow() + DAYS2,
            max_orphan_fraction=1.0,
            _referenced_fn=referenced_then_appears,
        )
    assert (r.deleted, r.skipped_now_referenced) == (0, 1) and key in env.keys()


def make_row_for(world, key):
    """An evidence row for `key`, cloned from an existing one (same workspace and asset)."""
    with world.maker() as db:
        src = db.scalars(select(Evidence).limit(1)).one()
        ws, asset = src.workspace_id, src.asset_id
        return Evidence(
            workspace_id=ws,
            asset_id=asset,
            uploaded_by=src.uploaded_by,
            storage_key=key,
            content_type="image/jpeg",
            size_bytes=14,
            sha256="0" * 64,
            width=1,
            height=1,
        )


# ------------------------------------------------------------------ tenancy and audit


def test_workspace_filter_never_touches_other_workspaces(env, team):
    env.upload()
    mine = env.orphan()
    theirs = env.orphan(ws=team.other_ws)
    r = env.run(delete=True, workspace_id=uuid.UUID(str(team.ws)), max_orphan_fraction=1.0)
    assert r.deleted == 1 and mine not in env.keys() and theirs in env.keys()


def test_each_deletion_is_audited_in_the_owning_workspace(env, world, team):
    env.upload()
    key = env.orphan()
    env.run(delete=True, max_orphan_fraction=1.0)
    with world.maker() as db:
        (ev,) = db.scalars(select(AuditEvent).where(AuditEvent.action == "evidence.orphan_blob.purged")).all()
    assert str(ev.workspace_id) == str(team.ws) and ev.actor_id is None and ev.target_type == "storage_object"
    assert ev.details["key"] == key and ev.details["size_bytes"] == len(b"orphaned-bytes")


def test_a_blob_of_a_vanished_workspace_is_deleted_without_an_audit_row(env, world):
    env.upload()
    ghost = env.orphan(ws=uuid.uuid4())
    r = env.run(delete=True, max_orphan_fraction=1.0)
    assert r.deleted == 1 and ghost not in env.keys()
    with world.maker() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "evidence.orphan_blob.purged")
            )
            == 0
        )


def test_a_failing_delete_is_skipped_and_the_run_continues(env, store, monkeypatch):
    env.upload()
    first, second = env.orphan(), env.orphan()
    real = store.delete

    def flaky(key):
        if key == first:
            raise StorageError("provider hiccup")
        real(key)

    monkeypatch.setattr(store, "delete", flaky)
    r = env.run(delete=True, max_orphan_fraction=1.0)
    assert r.deleted == 1 and first in env.keys() and second not in env.keys()


# ------------------------------------------------------------------ the command


def test_cli_dry_run_then_delete_and_refusal_exit_codes(env, store, world, capsys):
    env.upload()
    key = env.orphan()
    # the CLI uses the real clock, so backdate through the stores that allow it; others are covered by reconcile()
    if isinstance(store, MemoryObjectStore):
        store.modified[key] = utcnow() - DAYS2
    elif isinstance(store, LocalFileStore):
        old = (utcnow() - DAYS2).timestamp()
        os.utime(store.root / key, (old, old))
    else:
        pytest.skip("simulated S3 cannot backdate LastModified; the reconcile() tests cover it with an injected clock")
    assert evidence_reconcile.main(["--json", "--max-orphan-fraction", "1"], store=store, sessions=world.maker) == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{" + chr(10)) :])  # the indented report follows any one-line log output
    assert report["orphans"] == 1 and key in env.keys()
    assert evidence_reconcile.main(["--delete", "--max-orphan-fraction", "1"], store=store, sessions=world.maker) == 0
    assert key not in env.keys()
    assert (
        evidence_reconcile.main(["--min-age-hours", "0.5"], store=store, sessions=world.maker) == 1
    )  # below the floor
    assert "one hour" in capsys.readouterr().err


def test_cli_exits_2_when_a_safety_rule_refuses(env, store, world, capsys):
    key = env.orphan()
    if isinstance(store, MemoryObjectStore):
        store.modified[key] = utcnow() - DAYS2
    elif isinstance(store, LocalFileStore):
        old = (utcnow() - DAYS2).timestamp()
        os.utime(store.root / key, (old, old))
    else:
        pytest.skip("simulated S3 cannot backdate LastModified")
    assert (
        evidence_reconcile.main(["--delete"], store=store, sessions=world.maker) == 2
    )  # no evidence rows at all: wrong database
    assert "REFUSED" in capsys.readouterr().err and key in env.keys()
