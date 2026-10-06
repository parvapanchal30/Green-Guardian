"""Verify the configured database meets GreenGuardian's requirements.

    python -m app.tools.check_db

Prints server/PostGIS versions and exits non-zero if something is missing (docs/DATABASE_SETUP.md).
Never prints the connection string or credentials.
"""

from __future__ import annotations

import socket
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.db import build_engine

MIN_PG_MAJOR = 15


def probe_network(host: str, port: int, timeout: float = 5.0) -> dict[str, str]:
    """Per address family: 'ok' | 'no-address' | 'timeout' | 'refused/other'. Pure reachability, no auth."""
    result: dict[str, str] = {}
    for fam, label in ((socket.AF_INET, "IPv4"), (socket.AF_INET6, "IPv6")):
        try:
            addr = socket.getaddrinfo(host, port, fam, socket.SOCK_STREAM)[0][4]
        except socket.gaierror:
            result[label] = "no-address"
            continue
        s = socket.socket(fam)
        s.settimeout(timeout)
        try:
            s.connect(addr)
            result[label] = "ok"
        except TimeoutError:
            result[label] = "timeout"
        except OSError as e:
            result[label] = f"refused/other ({type(e).__name__})"
        finally:
            s.close()
    return result


def diagnose_network(net: dict[str, str]) -> str | None:
    """A human-readable cause if no address family is reachable; None if something works."""
    if any(v == "ok" for v in net.values()):
        return None
    v4, v6 = net.get("IPv4"), net.get("IPv6")
    if v4 == "no-address" and v6 == "no-address":
        return "The database host name does not resolve (DNS). Check the host in DATABASE_URL."
    if v4 == "no-address":
        return (
            "The host only has an IPv6 address and this network cannot reach it (typical for Supabase's direct "
            "connection on the free tier). Use the Session pooler connection string (IPv4) in DATABASE_URL."
        )
    return "The database host is not reachable from this network (firewall, VPN or wrong port?)."


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("FAIL  DATABASE_URL is not set (copy backend/.env.example to backend/.env)")
        return 2
    url = make_url(settings.database_url)
    if url.get_backend_name() == "postgresql" and url.host:
        net = probe_network(url.host, url.port or 5432)
        print("INFO  network reachability: " + ", ".join(f"{k}={v}" for k, v in net.items()))
        cause = diagnose_network(net)
        if cause:
            print(f"FAIL  {cause}")
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
            print(f"OK    application schema = {settings.db_schema}")
            leaked = c.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                    "AND table_name = ANY(:names)"
                ),
                {"names": ["users", "workspaces", "memberships", "organizations", "refresh_tokens"]},
            ).all()
            if leaked:
                problems.append(
                    "application tables found in 'public' (exposed by Supabase's Data API): "
                    + ", ".join(r[0] for r in leaked)
                )
            rls = c.execute(
                text(
                    "SELECT count(*) FILTER (WHERE c.relrowsecurity), count(*), "
                    "count(*) FILTER (WHERE pg_get_userbyid(c.relowner) = current_user) "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relkind IN ('r','p')"
                ),
                {"s": settings.db_schema},
            ).one()
            bypass = bool(c.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar())
            print(f"OK    RLS enabled on {rls[0]}/{rls[1]} application tables; role owns {rls[2]}; BYPASSRLS={bypass}")
            if rls[1] and rls[0] < rls[1]:
                problems.append(f"{rls[1] - rls[0]} application table(s) without RLS (see app/core/rls.py)")
            if rls[1] and rls[2] < rls[1] and not bypass:
                problems.append("this role neither owns the tables nor has BYPASSRLS: RLS (no policies) hides all rows")
            # Client->server leg (libpq). pg_stat_ssl would show the pooler->database hop instead.
            tls = bool(c.connection.dbapi_connection.pgconn.ssl_in_use)  # type: ignore[union-attr]
            print(f"{'OK   ' if tls else 'WARN '} TLS on client connection = {tls}")
            print(f"OK    pool mode = {settings.db_pool_mode}")
    except Exception as e:  # noqa: BLE001 - report any connectivity failure plainly
        first = str(e).splitlines()[0][:200]
        print(f"FAIL  cannot connect: {type(e).__name__}: {first}")
        if "password authentication failed" in str(e):
            print("      Hint: check the password (remove [brackets], URL-encode special characters).")
        return 2
    finally:
        engine.dispose()
    for p in problems:
        print(f"FAIL  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
