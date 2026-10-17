"""Brute-force protection: thresholds, cooldown and recovery, resets, isolation, enumeration resistance, privacy."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.timeutil import utcnow
from app.modules.identity import throttle
from app.modules.identity.models import AuthThrottle

PASSWORD = "correct-horse-battery-1"
API = "/api/v1/auth"


class Clock:
    def __init__(self):
        self.now = utcnow()

    def advance(self, **kw):
        self.now += timedelta(**kw)

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(throttle, "utcnow", c)
    return c


@pytest.fixture
def limits(world):
    """Small, explicit limits so tests stay fast; restored afterwards."""
    s = world.settings
    saved = {k: getattr(s, k) for k in s.model_fields if k.startswith("auth_")}
    s.auth_login_max_failures_pair, s.auth_login_max_failures_account, s.auth_login_max_failures_ip = 5, 15, 30
    s.auth_failure_window_s, s.auth_lockout_s = 900, 600
    yield s
    for k, v in saved.items():
        setattr(s, k, v)


def as_ip(app, ip: str) -> TestClient:
    return TestClient(app, client=(ip, 50000))


def register(c, email="owner@example.com"):
    r = c.post(f"{API}/register", json={"email": email, "password": PASSWORD, "name": "Test User"})
    assert r.status_code == 201, r.text


def login(c, email, password=PASSWORD):
    return c.post(f"{API}/login", json={"email": email, "password": password})


def fail(c, email, n=1):
    return [login(c, email, "wrong-password-xyz").status_code for _ in range(n)]


def test_failures_below_the_limit_never_block_and_success_resets_the_count(client, clock, limits):
    register(client)
    assert fail(client, "owner@example.com", 4) == [401] * 4
    assert login(client, "owner@example.com").status_code == 200  # success clears the pair and account counters
    assert fail(client, "owner@example.com", 4) == [401] * 4  # a fresh allowance
    assert login(client, "owner@example.com").status_code == 200


def test_reaching_the_limit_locks_with_retry_after_even_for_the_right_password(client, clock, limits):
    register(client)
    assert fail(client, "owner@example.com", 5) == [401] * 5  # the attempt that crosses the line is still a normal 401
    r = login(client, "owner@example.com")  # the correct password, but locked
    assert r.status_code == 429
    body = r.json()
    assert body["code"] == "too_many_attempts" and 0 < body["retry_after_s"] <= 601
    assert r.headers["retry-after"] == str(body["retry_after_s"])
    assert body["request_id"] == r.headers["x-request-id"]
    assert login(client, "owner@example.com", "wrong-password-xyz").status_code == 429  # wrong ones are blocked too


def test_the_lock_expires_and_the_legitimate_user_recovers(client, clock, limits):
    register(client)
    fail(client, "owner@example.com", 5)
    assert login(client, "owner@example.com").status_code == 429
    clock.advance(seconds=599)
    assert login(client, "owner@example.com").status_code == 429  # still inside the cooldown
    clock.advance(seconds=5)
    assert login(client, "owner@example.com").status_code == 200  # recovered, no manual action needed
    # and the allowance is fresh again, not one-strike-and-locked
    assert fail(client, "owner@example.com", 4) == [401] * 4


def test_a_failed_attempt_after_recovery_starts_a_new_count(client, clock, limits):
    register(client)
    fail(client, "owner@example.com", 5)
    clock.advance(seconds=700)
    assert fail(client, "owner@example.com", 4) == [401] * 4  # 4 fresh failures: still not locked
    assert fail(client, "owner@example.com", 1) == [401]
    assert login(client, "owner@example.com").status_code == 429


def test_failures_outside_the_counting_window_do_not_accumulate(client, clock, limits):
    register(client)
    fail(client, "owner@example.com", 4)
    clock.advance(seconds=901)  # window passed
    assert fail(client, "owner@example.com", 4) == [401] * 4
    assert login(client, "owner@example.com").status_code == 200


def test_unknown_and_known_emails_are_indistinguishable(client, clock, limits):
    register(client)
    known = login(client, "owner@example.com", "wrong-password-xyz")
    unknown = login(client, "nobody@example.com", "wrong-password-xyz")
    assert known.status_code == unknown.status_code == 401
    strip = lambda r: {k: v for k, v in r.json().items() if k != "request_id"}  # noqa: E731
    assert strip(known) == strip(unknown)

    fail(client, "owner@example.com", 4)
    fail(client, "nobody@example.com", 4)  # one failure each was already recorded above
    a, b = login(client, "owner@example.com"), login(client, "nobody@example.com")
    assert a.status_code == b.status_code == 429
    assert strip(a).keys() == strip(b).keys() and strip(a)["code"] == strip(b)["code"]
    assert abs(a.json()["retry_after_s"] - b.json()["retry_after_s"]) <= 1


def test_an_attacker_cannot_lock_the_victim_out_from_another_address(client, app, clock, limits):
    register(client, "victim@example.com")
    attacker, victim = as_ip(app, "6.6.6.6"), as_ip(app, "203.0.113.7")
    fail(attacker, "victim@example.com", 5)
    assert login(attacker, "victim@example.com").status_code == 429  # the attacker's own pair is locked
    assert login(victim, "victim@example.com").status_code == 200  # the real owner, elsewhere, is not


def test_distributed_guessing_locks_the_account_everywhere(app, client, clock, limits):
    register(client, "victim@example.com")
    for ip in ("6.6.6.1", "6.6.6.2", "6.6.6.3"):  # 3 addresses x 5 failures = 15 = the account limit
        fail(as_ip(app, ip), "victim@example.com", 5)
    assert login(as_ip(app, "203.0.113.7"), "victim@example.com").status_code == 429  # even from a fresh address
    clock.advance(seconds=700)
    assert login(as_ip(app, "203.0.113.7"), "victim@example.com").status_code == 200


def test_password_spraying_from_one_address_locks_that_address(app, client, clock, limits):
    limits.auth_login_max_failures_ip = 6
    register(client, "someone@example.com")
    sprayer = as_ip(app, "6.6.6.6")
    for i in range(6):
        assert login(sprayer, f"user{i}@example.com", "wrong-password-xyz").status_code == 401
    assert login(sprayer, "someone@example.com").status_code == 429  # any email, from that address
    assert login(as_ip(app, "203.0.113.7"), "someone@example.com").status_code == 200  # others unaffected


def test_a_successful_login_does_not_clear_the_address_counter(app, client, clock, limits):
    limits.auth_login_max_failures_ip = 6
    register(client, "me@example.com")
    c = as_ip(app, "6.6.6.6")
    for i in range(5):
        login(c, f"user{i}@example.com", "wrong-password-xyz")
    assert login(c, "me@example.com").status_code == 200  # my own login works and must not launder the counter...
    login(c, "another@example.com", "wrong-password-xyz")  # ...so this 6th failure still locks the address
    assert login(c, "me@example.com").status_code == 429


def test_refresh_attempts_with_invalid_tokens_are_throttled_per_address(app, client, clock, limits):
    limits.auth_refresh_max_failures_ip = 4
    c = as_ip(app, "6.6.6.6")
    codes = [c.post(f"{API}/refresh", json={"refresh_token": f"not-a-real-token-{i}"}).status_code for i in range(5)]
    assert codes == [401, 401, 401, 401, 429]


def test_registration_attempts_are_limited_per_address(app, clock, limits):
    limits.auth_register_max_per_ip = 3
    c = as_ip(app, "6.6.6.6")
    codes = [
        c.post(f"{API}/register", json={"email": f"u{i}@example.com", "password": PASSWORD, "name": "U"}).status_code
        for i in range(5)
    ]
    assert codes == [201, 201, 201, 429, 429]
    assert (
        as_ip(app, "203.0.113.7")
        .post(f"{API}/register", json={"email": "other@example.com", "password": PASSWORD, "name": "O"})
        .status_code
        == 201
    )


def test_stored_keys_contain_no_plaintext_email(client, world, clock, limits):
    register(client, "private.person@example.com")
    fail(client, "private.person@example.com", 2)
    fail(client, "typo-attempt@example.com", 1)
    with world.db() as db:
        keys = [k for (k,) in db.execute(select(AuthThrottle.key))]
    assert keys and not any("@" in k or "private" in k or "typo" in k for k in keys)
    assert any(k.startswith("login:acct:") and len(k.split(":")[2]) == 64 for k in keys)  # sha256 hex


def test_throttle_rows_are_cleared_for_the_pair_and_account_but_the_ip_row_remains(client, world, clock, limits):
    register(client)
    fail(client, "owner@example.com", 2)
    assert login(client, "owner@example.com").status_code == 200
    with world.db() as db:
        keys = [k for (k,) in db.execute(select(AuthThrottle.key))]
    assert any(k.startswith("login:ip:") for k in keys)
    assert not any(k.startswith(("login:pair:", "login:acct:")) for k in keys)


def test_purge_removes_only_idle_unlocked_counters(client, world, clock, limits):
    register(client)
    fail(client, "owner@example.com", 5)  # locked
    fail(client, "a@example.com", 1)  # idle soon
    clock.advance(hours=25)
    with world.db() as db:
        removed = throttle.purge_expired(db, now=clock.now)  # the lock (600 s) has also expired by now
        remaining = db.scalars(select(AuthThrottle)).all()
    assert removed >= 1 and not [r for r in remaining if r.locked_until and r.locked_until > clock.now]


def test_existing_login_flow_still_issues_tokens(client, clock, limits):
    register(client)
    r = login(client, "owner@example.com")
    assert r.status_code == 200 and set(r.json()) >= {"access_token", "refresh_token"}
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200
