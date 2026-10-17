"""Periodic housekeeping: audit retention and idle throttle counters.

    python -m app.tools.housekeeping            # do it
    python -m app.tools.housekeeping --dry-run  # report what would be removed

Safe to run repeatedly (idempotent). The scheduled worker (Stage C) calls the same functions.
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.audit import retention
from app.modules.identity import throttle


def run(dry_run: bool = False) -> dict:
    settings = get_settings()
    with get_sessionmaker()() as db:
        audit = retention.purge_expired(db, settings.audit_retention_days, dry_run=dry_run)
        idle = 0 if dry_run else throttle.purge_expired(db)
    return {
        "audit_retention_days": settings.audit_retention_days,
        "audit_cutoff": audit.cutoff.isoformat() if audit.cutoff else None,
        "audit_matched": audit.matched,
        "audit_deleted": audit.deleted,
        "throttle_rows_removed": idle,
        "dry_run": dry_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    result = run(parser.parse_args().dry_run)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
