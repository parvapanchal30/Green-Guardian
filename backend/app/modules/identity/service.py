from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import Conflict, NotFound, Unauthorized
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh,
    new_refresh_token,
    verify_password,
)
from app.core.timeutil import as_utc, utcnow
from app.modules.audit import service as audit

from . import throttle
from .models import RefreshTokenRow, User
from .schemas import MeUpdate, TokenPair


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register(db: Session, *, email: str, password: str, name: str, settings: Settings) -> User:
    rules = throttle.register_rules(settings)
    throttle.check(db, rules)
    throttle.record_failure(db, rules)  # every attempt counts, successful or not: this limits mass sign-ups
    user = User(email=normalize_email(email), password_hash=hash_password(password), name=name.strip())
    db.add(user)
    try:
        db.flush()
        audit.record(db, action="auth.register", actor_id=user.id, target_type="user", target_id=user.id)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise Conflict("An account with this email already exists", code="email_taken") from e
    return user


def _issue_tokens(db: Session, user: User, settings: Settings) -> TokenPair:
    access, ttl = create_access_token(user.id, settings)
    rt = new_refresh_token()
    now = utcnow()
    db.add(
        RefreshTokenRow(
            user_id=user.id,
            token_hash=rt.hash,
            created_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    return TokenPair(access_token=access, refresh_token=rt.raw, expires_in=ttl)


def login(db: Session, *, email: str, password: str, settings: Settings) -> TokenPair:
    rules = throttle.login_rules(settings, email)
    throttle.check(db, rules)  # before any credential check: a locked caller learns nothing and costs no hashing
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    ok = verify_password(password, user.password_hash if user else None)
    if not user or not ok or not user.is_active:
        # Same event for an unknown email and a wrong password (no enumeration); only a short hash is kept.
        audit.record(
            db,
            action="auth.login.failure",
            outcome="failure",
            details={"email_ref": throttle.email_ref(email), "reason": "invalid_credentials"},
        )
        locked = throttle.record_failure(db, rules)  # commits the failure counters and the audit row together
        if locked:
            audit.record(
                db,
                action="auth.login.locked",
                outcome="denied",
                details={"email_ref": throttle.email_ref(email), "scopes": [k.split(":")[1] for k in locked]},
            )
            db.commit()
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    throttle.reset(db, throttle.login_success_keys(rules))
    user.last_login_at = utcnow()
    pair = _issue_tokens(db, user, settings)
    audit.record(db, action="auth.login.success", actor_id=user.id, target_type="user", target_id=user.id)
    db.commit()
    return pair


def refresh(db: Session, *, refresh_token: str, settings: Settings) -> TokenPair:
    rules = throttle.refresh_rules(settings)
    throttle.check(db, rules)
    row = db.scalar(select(RefreshTokenRow).where(RefreshTokenRow.token_hash == hash_refresh(refresh_token)))
    if row is None:
        throttle.record_failure(db, rules)
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    now = utcnow()
    if row.revoked_at is not None:
        # A rotated token was presented again: assume theft and end every session of this user.
        db.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.user_id == row.user_id, RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        audit.record(
            db,
            action="auth.refresh.reuse_detected",
            actor_id=row.user_id,
            target_type="user",
            target_id=row.user_id,
            outcome="denied",
            details={"effect": "all sessions revoked"},
        )
        db.commit()
        raise Unauthorized("Refresh token was already used", code="refresh_token_reuse")
    if as_utc(row.expires_at) <= now:
        raise Unauthorized("Refresh token expired", code="refresh_token_expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account disabled", code="invalid_refresh_token")
    row.revoked_at = now
    pair = _issue_tokens(db, user, settings)
    db.commit()
    return pair


def logout(db: Session, *, refresh_token: str) -> None:
    row = db.scalar(select(RefreshTokenRow).where(RefreshTokenRow.token_hash == hash_refresh(refresh_token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        audit.record(db, action="auth.logout", actor_id=row.user_id, target_type="user", target_id=row.user_id)
        db.commit()


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account not found or disabled", code="invalid_token")
    return user


def get_user_by_email(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        raise NotFound("No user with that email", code="user_not_found")
    return user


def update_me(db: Session, user: User, data: MeUpdate) -> User:
    fields = sorted(data.model_fields_set & {"name", "phone"})  # which fields, never the values (phone is personal)
    if data.name is not None:
        user.name = data.name.strip()
    if "phone" in data.model_fields_set:
        user.phone = data.phone
    audit.record(
        db, action="user.update", actor_id=user.id, target_type="user", target_id=user.id, details={"fields": fields}
    )
    db.commit()
    return user
