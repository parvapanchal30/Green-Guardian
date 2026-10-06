from __future__ import annotations

import time
import uuid

import pytest

from app.core.config import Settings, normalize_database_url
from app.core.ids import uuid7
from app.core.security import hash_password, new_refresh_token, verify_password
from app.modules.workspaces.capabilities import REGISTRY, effective_capabilities


def test_uuid7_is_valid_version7_and_time_ordered():
    ids = []
    for _ in range(5):
        ids.append(uuid7())
        time.sleep(0.002)
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert ids == sorted(ids, key=lambda u: u.int)
    assert len({uuid7() for _ in range(1000)}) == 1000


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite+pysqlite:///:memory:", "sqlite+pysqlite:///:memory:"),
    ],
)
def test_database_url_normalization(raw, expected):
    assert normalize_database_url(raw) == expected


def test_settings_guards():
    base = dict(_env_file=None)
    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret="short", **base)
    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret="x" * 40, weather_provider="mock", **base)
    with pytest.raises(ValueError):
        Settings(postgis_schema="extensions; DROP TABLE users", **base)
    assert Settings(env="production", jwt_secret="x" * 40, **base).weather_provider == "open_meteo"


def test_passwords_and_refresh_tokens():
    h = hash_password("a-long-enough-password")
    assert h.startswith("$argon2id$")
    assert verify_password("a-long-enough-password", h) and not verify_password("wrong", h)
    assert not verify_password("anything", None)
    a, b = new_refresh_token(), new_refresh_token()
    assert a.raw != b.raw and a.hash != a.raw and len(a.hash) == 64


def test_capability_overrides_can_only_disable():
    live = next(c for c in REGISTRY if c.available)
    unavailable = next(c for c in REGISTRY if not c.available)
    eff = {c.key: c for c in effective_capabilities({live.key: False, unavailable.key: True})}
    assert eff[live.key].available is False
    assert eff[unavailable.key].available is False  # an override can never enable an unbuilt feature
