"""Declarative base and portable column helpers (PostgreSQL in production, SQLite in fast tests)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, MetaData, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from .ids import uuid7
from .timeutil import as_utc, utcnow

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UtcDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python, on every database.

    PostgreSQL keeps the zone (timestamptz); SQLite (the local demo and the fast tests) stores the value without one and
    hands back a naive datetime, which the API would send without an offset and a browser would read as LOCAL time.
    Normalising here, once, means every model column, ORM object and Core query result is UTC-aware."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return as_utc(value) if isinstance(value, datetime) else value

    def process_result_value(self, value, dialect):
        return as_utc(value) if isinstance(value, datetime) else value


# JSONB on PostgreSQL, generic JSON elsewhere.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow, nullable=False)
