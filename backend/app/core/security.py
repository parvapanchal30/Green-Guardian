"""Password hashing (argon2id) and tokens. First-party JWT behind this small interface (ADR-010)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import Settings
from .errors import Unauthorized
from .timeutil import utcnow

_hasher = PasswordHasher()
# Verified when the account does not exist so login timing does not reveal valid emails.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, settings: Settings) -> tuple[str, int]:
    now = utcnow()
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": now + ttl, "typ": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(ttl.total_seconds())


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    try:
        data = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["exp", "sub"]}
        )
        if data.get("typ") != "access":
            raise Unauthorized("Wrong token type", code="invalid_token")
        return uuid.UUID(data["sub"])
    except jwt.ExpiredSignatureError as e:
        raise Unauthorized("Access token expired", code="token_expired") from e
    except (jwt.PyJWTError, ValueError) as e:
        raise Unauthorized("Invalid access token", code="invalid_token") from e


@dataclass(frozen=True)
class RefreshToken:
    raw: str
    hash: str


def hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> RefreshToken:
    raw = secrets.token_urlsafe(48)
    return RefreshToken(raw=raw, hash=hash_refresh(raw))
