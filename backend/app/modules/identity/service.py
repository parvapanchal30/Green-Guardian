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

from .models import RefreshTokenRow, User
from .schemas import MeUpdate, TokenPair


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register(db: Session, *, email: str, password: str, name: str) -> User:
    user = User(email=normalize_email(email), password_hash=hash_password(password), name=name.strip())
    db.add(user)
    try:
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
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    ok = verify_password(password, user.password_hash if user else None)
    if not user or not ok or not user.is_active:
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    user.last_login_at = utcnow()
    pair = _issue_tokens(db, user, settings)
    db.commit()
    return pair


def refresh(db: Session, *, refresh_token: str, settings: Settings) -> TokenPair:
    row = db.scalar(select(RefreshTokenRow).where(RefreshTokenRow.token_hash == hash_refresh(refresh_token)))
    if row is None:
        raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
    now = utcnow()
    if row.revoked_at is not None:
        # A rotated token was presented again: assume theft and end every session of this user.
        db.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.user_id == row.user_id, RefreshTokenRow.revoked_at.is_(None))
            .values(revoked_at=now)
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
    if data.name is not None:
        user.name = data.name.strip()
    if "phone" in data.model_fields_set:
        user.phone = data.phone
    db.commit()
    return user
