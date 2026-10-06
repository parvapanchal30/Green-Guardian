"""Verify the configured database meets GreenGuardian's requirements.

    python -m app.tools.check_db

Prints server/PostGIS versions and exits non-zero if something is missing (docs/DATABASE_SETUP.md).
Never prints the connection string or credentials.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import build_engine

MIN_PG_MAJOR = 15


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("FAIL  DATABASE_URL is not set (copy backend/.env.example to backend/.env)")
        return 2
    problems: list[str] = []
    engine = build_engine(settings)
    try:
        with engine.connect() as c:
            if engine.dialect.name != "postgresql":
                print(f"FAIL  dialect is {engine.dialect.name}; PostgreSQL is required")
                return 2
            major = int(c.execute(text("SHOW server_version_num")).scalar() or 0) // 10000
            print(f"OK    PostgreSQL major version {major}")
            if major < MIN_PG_MAJOR:
                problems.append(f"PostgreSQL {major} < {MIN_PG_MAJOR}")
            avail = c.execute(
                text("SELECT default_version, installed_version FROM pg_available_extensions WHERE name='postgis'")
            ).first()
            if not avail:
                problems.append("PostGIS is not available on this server")
            elif avail[1] is None:
                problems.append(
                    "PostGIS is available but not installed: run `alembic upgrade head` "
                    f"or CREATE EXTENSION postgis WITH SCHEMA {settings.postgis_schema}"
                )
            else:
                ver = c.execute(text("SELECT postgis_version()")).scalar()
                schema = c.execute(
                    text(
                        "SELECT n.nspname FROM pg_extension e JOIN pg_namespace n "
                        "ON n.oid = e.extnamespace WHERE e.extname='postgis'"
                    )
                ).scalar()
                print(f"OK    PostGIS {ver} installed in schema '{schema}'")
                if schema == "public":
                    problems.append("PostGIS is installed in 'public'; use a dedicated schema (see DATABASE_SETUP.md)")
            print(f"OK    search_path = {c.execute(text('SHOW search_path')).scalar()}")
            print(f"OK    pool mode = {settings.db_pool_mode}")
    except Exception as e:  # noqa: BLE001 - report any connectivity failure plainly
        print(f"FAIL  cannot connect: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
        print("      Hint: Supabase direct connections are IPv6-only on the free tier; use the session pooler URL.")
        return 2
    finally:
        engine.dispose()
    for p in problems:
        print(f"FAIL  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
