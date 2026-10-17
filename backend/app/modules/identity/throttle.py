"""Brute-force protection for authentication endpoints (database-backed counters).

Each protected action defines a list of `Rule`s (a counter key, a limit, a window and a lockout). A caller is blocked
if ANY of its keys is currently locked. Reaching a limit sets `locked_until`; when that passes, the counter starts
fresh, so legitimate users recover automatically. Counters live in `auth_throttle` so they survive restarts and are
shared by every API replica.

Privacy and enumeration: keys derive from the *submitted* email (hashed) and the client address, so an unknown email is
throttled exactly like a real one. Plaintext emails are never stored in this table.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import TooManyRequests
from app.core.request_context import current_client_ip
from app.core.timeutil import as_utc, utcnow

from .models import AuthThrottle


@dataclass(frozen=True)
class Rule:
    key: str
    limit: int
    window_s: int
    lockout_s: int


def _hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def email_ref(email: str) -> str:
    """A short, non-reversible reference to a submitted email for audit and logs (never the address itself)."""
    return _hash(email)[:16]


def _ip() -> str:
    return current_client_ip() or "unknown"


# ---- rule sets -------------------------------------------------------------------------------------------------


def login_rules(settings: Settings, email: str) -> list[Rule]:
    h, ip = _hash(email), _ip()
    w, lock = settings.auth_failure_window_s, settings.auth_lockout_s
    return [
        Rule(f"login:pair:{h}:{ip}", settings.auth_login_max_failures_pair, w, lock),
        Rule(f"login:acct:{h}", settings.auth_login_max_failures_account, w, lock),
        Rule(f"login:ip:{ip}", settings.auth_login_max_failures_ip, w, lock),
    ]


def login_success_keys(rules: list[Rule]) -> list[str]:
    """What a successful login clears: the pair and the account, never the IP counter (no laundering a spraying IP)."""
    return [r.key for r in rules if ":ip:" not in r.key]


def refresh_rules(settings: Settings) -> list[Rule]:
    return [
        Rule(
            f"refresh:ip:{_ip()}",
            settings.auth_refresh_max_failures_ip,
            settings.auth_failure_window_s,
            settings.auth_lockout_s,
        )
    ]


def register_rules(settings: Settings) -> list[Rule]:
    return [
        Rule(
            f"register:ip:{_ip()}",
            settings.auth_register_max_per_ip,
            settings.auth_register_window_s,
            settings.auth_lockout_s,
        )
    ]


# ---- engine ----------------------------------------------------------------------------------------------------


def _fresh(row: AuthThrottle, now: datetime) -> None:
    row.failures, row.locked_until, row.window_started_at, row.updated_at = 0, None, now, now


def _load(db: Session, key: str, now: datetime, *, create: bool, lock: bool = False) -> AuthThrottle | None:
    q = select(AuthThrottle).where(AuthThrottle.key == key)
    if lock:
        q = q.with_for_update()
    row = db.scalar(q)
    if row is None and create:
        row = AuthThrottle(key=key, failures=0, window_started_at=now, updated_at=now)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:  # another request created it first
            db.rollback()
            row = db.scalar(select(AuthThrottle).where(AuthThrottle.key == key).with_for_update())
    return row


def retry_after(db: Session, rules: list[Rule], now: datetime | None = None) -> int:
    """Seconds until every currently-locked key of `rules` is free (0 if none is locked)."""
    now = now or utcnow()
    remaining = 0
    for rule in rules:
        row = _load(db, rule.key, now, create=False)
        if row and row.locked_until and as_utc(row.locked_until) > now:
            remaining = max(remaining, int((as_utc(row.locked_until) - now).total_seconds()) + 1)
    return remaining


def check(db: Session, rules: list[Rule], now: datetime | None = None) -> None:
    """Raise 429 (with Retry-After) if any key is locked. Call BEFORE verifying credentials."""
    seconds = retry_after(db, rules, now)
    if seconds:
        raise TooManyRequests(
            "Too many attempts. Try again later.",
            code="too_many_attempts",
            extra={"retry_after_s": seconds},
            headers={"Retry-After": str(seconds)},
        )


def record_failure(db: Session, rules: list[Rule], now: datetime | None = None) -> list[str]:
    """Count one failure on every rule and commit. Returns the keys that became locked by this failure."""
    now = now or utcnow()
    newly_locked: list[str] = []
    for rule in rules:
        row = _load(db, rule.key, now, create=True, lock=True)
        assert row is not None
        if row.locked_until and as_utc(row.locked_until) <= now:
            _fresh(row, now)  # the lockout has passed: start over
        elif now - as_utc(row.window_started_at) > timedelta(seconds=rule.window_s) and not row.locked_until:
            _fresh(row, now)  # the counting window has passed
        row.failures += 1
        row.updated_at = now
        if row.failures >= rule.limit and not row.locked_until:
            row.locked_until = now + timedelta(seconds=rule.lockout_s)
            newly_locked.append(rule.key)
    db.commit()
    return newly_locked


def reset(db: Session, keys: list[str]) -> None:
    """Forget the counters (after a successful login). Does not commit; the caller's transaction does."""
    for key in keys:
        row = db.scalar(select(AuthThrottle).where(AuthThrottle.key == key))
        if row is not None:
            db.delete(row)


def purge_expired(db: Session, older_than_s: int = 86_400, now: datetime | None = None) -> int:
    """Housekeeping: drop idle, unlocked counters. (A scheduled job will call this once the worker exists.)"""
    now = now or utcnow()
    cutoff = now - timedelta(seconds=older_than_s)
    rows = db.scalars(select(AuthThrottle).where(AuthThrottle.updated_at < cutoff)).all()
    n = 0
    for row in rows:
        if not row.locked_until or as_utc(row.locked_until) <= now:
            db.delete(row)
            n += 1
    db.commit()
    return n
