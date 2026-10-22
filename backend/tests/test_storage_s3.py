"""S3-compatible evidence storage: the adapter against a simulated S3 (moto, in process, no network and no credentials of
any real account), configuration validation, failure mapping, tenant isolation and the start-up checks.

Nothing here contacts a real bucket. Behaviour against a real provider (endpoint quirks, permissions, latency) is verified
only by `python -m app.tools.storage_check` run against that provider, which has NOT been done."""

from __future__ import annotations

import io
import sys
import uuid

import boto3
import pytest
from moto import mock_aws
from PIL import Image
from sqlalchemy import select, update

from app.core.config import Settings
from app.main import validate_storage_provider
from app.modules.evidence.models import Evidence
from app.modules.evidence.storage import (
    ObjectNotFound,
    S3ObjectStore,
    StorageError,
    UnknownStorageProvider,
    available_stores,
    build_store,
    s3_dependency_problem,
)
from app.tools import storage_check
from tests.helpers import make_asset

BUCKET = "gg-test-evidence"
BASE = dict(_env_file=None, env="test", jwt_secret="x" * 40, database_url="sqlite://")
S3 = dict(storage_provider="s3", storage_s3_bucket=BUCKET, storage_s3_region="eu-central-1")


@pytest.fixture(autouse=True)
def _aws(monkeypatch):
    # moto intercepts boto3; dummy values make sure no real credential or profile can ever be picked up by accident.
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "STORAGE_S3_BUCKET", "STORAGE_S3_PREFIX", "STORAGE_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")


@pytest.fixture
def bucket():
    with mock_aws():
        raw = boto3.client("s3", region_name="eu-central-1")
        raw.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
        yield raw


def make(**over) -> S3ObjectStore:
    return build_store(Settings(**{**BASE, **S3, **over}))  # type: ignore[return-value]


def keys(raw) -> list[str]:
    return [o["Key"] for o in raw.list_objects_v2(Bucket=BUCKET).get("Contents", [])]


# ------------------------------------------------------------------ the adapter


def test_round_trip_overwrite_delete_exists(bucket):
    store = make()
    store.put("ws/asset/ev.jpg", b"123", "image/jpeg")
    assert store.exists("ws/asset/ev.jpg") and store.get("ws/asset/ev.jpg") == b"123"
    assert bucket.head_object(Bucket=BUCKET, Key="ws/asset/ev.jpg")["ContentType"] == "image/jpeg"
    store.put("ws/asset/ev.jpg", b"4567", "image/jpeg")
    assert store.get("ws/asset/ev.jpg") == b"4567"
    store.delete("ws/asset/ev.jpg")
    store.delete("ws/asset/ev.jpg")  # idempotent
    assert not store.exists("ws/asset/ev.jpg") and keys(bucket) == []


def test_a_missing_object_is_not_found_not_a_generic_failure(bucket):
    store = make()
    with pytest.raises(ObjectNotFound):
        store.get("ws/asset/none.jpg")
    assert store.exists("ws/asset/none.jpg") is False


def test_the_prefix_is_applied_and_isolates_what_the_store_can_see(bucket):
    prefixed = make(storage_s3_prefix="staging/evidence")
    prefixed.put("ws/a/e.png", b"x", "image/png")
    assert keys(bucket) == ["staging/evidence/ws/a/e.png"]
    other = make()  # the same bucket with no prefix cannot see it under the logical key
    assert not other.exists("ws/a/e.png")


@pytest.mark.parametrize("key", ["../x", "a/../../x", "/etc/passwd", "a//b", "a\\b", "", ".hidden", "a/.."])
def test_unsafe_keys_are_refused_before_any_request(bucket, key):
    store = make()
    for op in (
        lambda: store.put(key, b"x", "image/png"),
        lambda: store.get(key),
        lambda: store.exists(key),
        lambda: store.delete(key),
    ):
        with pytest.raises(StorageError):
            op()
    assert keys(bucket) == []


def test_provider_errors_become_storage_errors_without_leaking_credentials():
    with mock_aws():  # no bucket exists
        store = make(storage_s3_access_key_id="AKIASECRETKEYID1234", storage_s3_secret_access_key="topsecretvalue")
        for op in (
            lambda: store.put("a/b.jpg", b"x", "image/jpeg"),
            lambda: store.get("a/b.jpg"),
            lambda: store.delete("a/b.jpg"),
        ):
            with pytest.raises(StorageError) as e:
                op()
            assert not isinstance(e.value, ObjectNotFound)  # a missing BUCKET is an outage, not a missing image
            assert "AKIASECRETKEYID1234" not in str(e.value) and "topsecretvalue" not in str(e.value)


def test_an_object_larger_than_the_upload_limit_is_not_loaded_into_memory(bucket):
    store = make(storage_max_bytes=100)
    bucket.put_object(Bucket=BUCKET, Key="ws/a/big.jpg", Body=b"x" * 101)
    with pytest.raises(StorageError, match="larger than"):
        store.get("ws/a/big.jpg")
    bucket.put_object(Bucket=BUCKET, Key="ws/a/ok.jpg", Body=b"x" * 100)
    assert len(store.get("ws/a/ok.jpg")) == 100


def test_client_configuration(bucket):
    cfg = make().__dict__["_client"].meta.config
    assert cfg.s3["addressing_style"] == "auto" and cfg.connect_timeout == 10 and cfg.read_timeout == 10
    assert cfg.request_checksum_calculation == "when_required"  # several S3-compatible providers reject default CRCs
    custom = make(
        storage_s3_endpoint_url="https://s3.example.org/storage/v1/s3",
        storage_s3_timeout_s=3,
        storage_s3_max_attempts=2,
    )
    client = custom.__dict__["_client"]
    assert client.meta.endpoint_url == "https://s3.example.org/storage/v1/s3"
    assert client.meta.config.s3["addressing_style"] == "path"  # an explicit endpoint implies path-style
    assert client.meta.config.retries["total_max_attempts"] == 2 and client.meta.config.read_timeout == 3
    forced = make(storage_s3_endpoint_url="https://s3.example.org", storage_s3_path_style=False)
    assert forced.__dict__["_client"].meta.config.s3["addressing_style"] == "auto"


def test_explicit_credentials_are_used_and_never_printed():
    s = Settings(
        **BASE, **S3, storage_s3_access_key_id="AKIAEXAMPLE0000000", storage_s3_secret_access_key="s3cr3t-value"
    )
    assert (
        "s3cr3t-value" not in repr(s)
        and "AKIAEXAMPLE0000000" not in repr(s)
        and "s3cr3t-value" not in s.model_dump_json()
    )
    with mock_aws():
        client = make(
            storage_s3_access_key_id="AKIAEXAMPLE0000000", storage_s3_secret_access_key="s3cr3t-value"
        ).__dict__["_client"]
        assert client._request_signer._credentials.access_key == "AKIAEXAMPLE0000000"


# ------------------------------------------------------------------ configuration validation


@pytest.mark.parametrize(
    ("over", "fragment"),
    [
        ({"storage_s3_bucket": ""}, "STORAGE_S3_BUCKET"),
        ({"storage_s3_bucket": "Bad_Bucket"}, "STORAGE_S3_BUCKET"),
        ({"storage_s3_bucket": "a..b"}, "STORAGE_S3_BUCKET"),
        ({"storage_s3_region": ""}, "STORAGE_S3_REGION"),
        ({"storage_s3_endpoint_url": "http://s3.example.org"}, "https"),
        ({"storage_s3_endpoint_url": "https://u:p@s3.example.org"}, "without credentials"),
        ({"storage_s3_endpoint_url": "https://s3.example.org/?x=1"}, "without credentials"),
        ({"storage_s3_prefix": "../other"}, "STORAGE_S3_PREFIX"),
        ({"storage_s3_prefix": "/abs"}, "STORAGE_S3_PREFIX"),
        ({"storage_s3_prefix": "a//b"}, "STORAGE_S3_PREFIX"),
        ({"storage_s3_access_key_id": "only-the-id"}, "both"),
        ({"storage_s3_secret_access_key": "only-the-secret"}, "both"),
        ({"storage_s3_timeout_s": 0}, "TIMEOUT"),
        ({"storage_s3_max_attempts": 0}, "MAX_ATTEMPTS"),
        ({"storage_s3_max_attempts": 11}, "MAX_ATTEMPTS"),
    ],
)
def test_invalid_s3_configuration_is_refused(over, fragment):
    with pytest.raises(ValueError, match=fragment):
        Settings(**{**BASE, **S3, **over})


def test_valid_s3_configuration_and_the_s3_settings_are_ignored_for_other_providers():
    ok = Settings(
        **BASE,
        **S3,
        storage_s3_endpoint_url="https://abc.supabase.example/storage/v1/s3",
        storage_s3_prefix="staging/evidence",
    )
    assert ok.storage_provider == "s3"
    assert Settings(**BASE, storage_provider="local", storage_s3_bucket="Not A Bucket").storage_provider == "local"
    # plain http is a development convenience for a local MinIO, never allowed in production
    assert Settings(**{**BASE, **S3}, storage_s3_endpoint_url="http://localhost:9000").storage_s3_endpoint_url
    with pytest.raises(ValueError, match="https"):
        Settings(
            **{**BASE, **S3, "env": "production"},
            storage_s3_endpoint_url="http://localhost:9000",
            cors_origins=["https://app.example.org"],
            weather_provider="open_meteo",
        )


def test_s3_is_registered_and_the_start_up_check_catches_a_missing_client_library(monkeypatch):
    assert "s3" in available_stores()
    assert s3_dependency_problem() is None
    validate_storage_provider(Settings(**BASE, **S3))
    monkeypatch.setitem(sys.modules, "boto3", None)  # makes `import boto3` raise ImportError
    assert "'s3' extra" in (s3_dependency_problem() or "")
    with pytest.raises(UnknownStorageProvider, match="s3"):
        validate_storage_provider(Settings(**BASE, **S3))
    with pytest.raises(StorageError, match="s3"):
        S3ObjectStore.from_settings(Settings(**BASE, **S3))


# ------------------------------------------------------------------ through the API: tenancy and failure behaviour


def image() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (30, 120, 40)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def s3_world(world, bucket):
    """The real API with the S3 adapter (simulated S3) in place of the in-memory test store."""
    from app.modules.evidence.storage import get_object_store

    world.app.dependency_overrides[get_object_store] = lambda: make()
    return world


@pytest.fixture
def asset(api_for, team):
    return make_asset(api_for(team.worker))


def upload(client, api_for, member, asset_id, ws=None):
    a = api_for(member, ws)
    return client.post(
        a.url("/evidence"),
        data={"asset_id": str(asset_id)},
        files={"file": ("leaf.jpg", image(), "image/jpeg")},
        headers=a.headers,
    )


def test_evidence_round_trips_through_the_api_and_the_bucket_holds_workspace_prefixed_keys(
    s3_world, bucket, client, api_for, team, asset
):
    r = upload(client, api_for, team.worker, asset["id"])
    assert r.status_code == 201, r.text
    ev = r.json()
    (key,) = keys(bucket)
    assert key.startswith(f"{team.ws}/{asset['id']}/")  # the first segment is the owning workspace
    got = api_for(team.viewer).get(f"/evidence/{ev['id']}/content")
    assert got.status_code == 200 and got.content == image() and got.headers["content-type"] == "image/jpeg"


def test_another_tenant_gets_404_for_content_that_exists_in_the_bucket(s3_world, bucket, client, api_for, team, asset):
    ev = upload(client, api_for, team.worker, asset["id"]).json()
    theirs = api_for(team.other_owner, team.other_ws)
    assert theirs.get(f"/evidence/{ev['id']}/content").status_code == 404
    assert api_for(team.worker, team.other_ws).get(f"/evidence/{ev['id']}/content").status_code == 404
    assert len(keys(bucket)) == 1  # nothing was touched


def test_a_row_pointing_into_another_workspaces_key_space_is_never_served(
    s3_world, bucket, client, api_for, team, asset
):
    """Defence in depth: even if a row's storage_key were corrupted to name another tenant's object, the API refuses."""
    ev = upload(client, api_for, team.worker, asset["id"]).json()
    foreign = f"{team.other_ws}/{asset['id']}/secret.jpg"
    bucket.put_object(Bucket=BUCKET, Key=foreign, Body=b"another tenant's photo")
    with s3_world.maker() as db:
        db.execute(update(Evidence).where(Evidence.id == uuid.UUID(ev["id"])).values(storage_key=foreign))
        db.commit()
        assert db.scalar(select(Evidence.storage_key).where(Evidence.id == uuid.UUID(ev["id"]))) == foreign
    r = api_for(team.worker).get(f"/evidence/{ev['id']}/content")
    assert r.status_code == 404 and b"another tenant" not in r.content


def test_a_provider_outage_saves_nothing_and_reads_return_503(s3_world, bucket, client, api_for, team, asset):
    ok = upload(client, api_for, team.worker, asset["id"]).json()
    raw = boto3.client("s3", region_name="eu-central-1")
    raw.delete_object(Bucket=BUCKET, Key=raw.list_objects_v2(Bucket=BUCKET)["Contents"][0]["Key"])
    raw.delete_bucket(Bucket=BUCKET)
    assert upload(client, api_for, team.worker, asset["id"]).status_code == 503
    assert api_for(team.worker).get(f"/evidence/{ok['id']}/content").status_code == 503


# ------------------------------------------------------------------ operator probe


def test_storage_check_tool_passes_against_a_working_bucket_and_fails_clearly_otherwise(bucket, capsys):
    settings = Settings(**BASE, **S3)
    assert storage_check.run(settings) == 0
    assert keys(bucket) == []  # the probe object is removed
    out = capsys.readouterr().out
    assert "OK" in out and "put" in out and "get" in out and "delete" in out
    raw = boto3.client("s3", region_name="eu-central-1")
    raw.delete_bucket(Bucket=BUCKET)
    assert storage_check.run(settings) == 1
    assert "FAILED" in capsys.readouterr().out


def test_storage_check_refuses_other_providers_and_never_prints_secrets(capsys):
    assert storage_check.run(Settings(**BASE, storage_provider="local")) == 2
    with mock_aws():
        s = Settings(
            **BASE,
            **S3,
            storage_s3_access_key_id="AKIAPROBEKEY000000",
            storage_s3_secret_access_key="probe-secret-0000",
        )
        storage_check.run(s)
    assert "AKIAPROBEKEY000000" not in capsys.readouterr().out


# ------------------------------------------------------------------ logging hygiene


def test_debug_application_logging_does_not_put_the_access_key_id_in_logs(bucket, caplog):
    import logging

    from app.core.logging import configure_logging

    configure_logging("DEBUG")
    try:
        with caplog.at_level(logging.DEBUG):
            store = make(storage_s3_access_key_id="AKIADEBUGKEY000000", storage_s3_secret_access_key="debugsecret000")
            store.put("ws/a/e.jpg", b"PHOTOBYTES-MARKER", "image/jpeg")
            store.get("ws/a/e.jpg")
        text = caplog.text
        assert "AKIADEBUGKEY000000" not in text and "debugsecret000" not in text and "PHOTOBYTES-MARKER" not in text
    finally:
        configure_logging("INFO")


def test_the_response_connection_is_released_even_when_the_object_is_too_large(bucket):
    store = make(storage_max_bytes=10)
    bucket.put_object(Bucket=BUCKET, Key="ws/a/big.jpg", Body=b"x" * 11)
    closed = []
    client = store.__dict__["_client"]
    original = client.get_object

    def spy(**kw):
        obj = original(**kw)
        real_close = obj["Body"].close
        obj["Body"].close = lambda: (closed.append(True), real_close())[1]
        return obj

    client.get_object = spy
    with pytest.raises(StorageError):
        store.get("ws/a/big.jpg")
    assert closed == [True]
