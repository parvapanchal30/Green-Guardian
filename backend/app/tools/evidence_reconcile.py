"""Find (and optionally remove) orphan evidence blobs: objects in the store that no database row points to.

    python -m app.tools.evidence_reconcile                  # DRY RUN (default): report only, nothing is deleted
    python -m app.tools.evidence_reconcile --delete         # delete orphans older than --min-age-hours, under the safety rules
    python -m app.tools.evidence_reconcile --workspace <id> # restrict to one workspace's keys
    python -m app.tools.evidence_reconcile --json           # machine-readable report

Uses the configured STORAGE_PROVIDER and DATABASE_URL, exactly as the API does, so point both at the SAME environment.
Read the rules in app/modules/evidence/reconcile.py first. Exit codes: 0 done, 2 a safety rule refused the deletion
(nothing deleted), 1 other failure. Not run by the worker: a destructive job is started deliberately, never implicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable
from datetime import timedelta

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.evidence import reconcile
from app.modules.evidence.storage import ObjectStore, StorageError, build_store


def main(
    argv: list[str] | None = None, *, store: ObjectStore | None = None, sessions: Callable[[], Session] | None = None
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--delete", action="store_true", help="actually delete (default is a dry run)")
    parser.add_argument("--min-age-hours", type=float, default=reconcile.DEFAULT_MIN_AGE.total_seconds() / 3600)
    parser.add_argument("--max-delete", type=int, default=reconcile.DEFAULT_MAX_DELETE)
    parser.add_argument("--max-orphan-fraction", type=float, default=reconcile.DEFAULT_MAX_ORPHAN_FRACTION)
    parser.add_argument("--workspace", type=uuid.UUID, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    store = store or build_store(get_settings())
    try:
        with (sessions or get_sessionmaker())() as db:
            report = reconcile.reconcile(
                db,
                store,
                delete=args.delete,
                min_age=timedelta(hours=args.min_age_hours),
                max_delete=args.max_delete,
                max_orphan_fraction=args.max_orphan_fraction,
                workspace_id=args.workspace,
            )
    except reconcile.RefusedToDelete as exc:
        print(f"REFUSED: {exc}\nNothing was deleted.", file=sys.stderr)
        return 2
    except (StorageError, ValueError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        for key, value in report.as_dict().items():
            if isinstance(value, list):
                print(f"{key}: {len(value)} shown" + "".join(f"\n    {v}" for v in value))
            else:
                print(f"{key}: {value}")
        if not args.delete and report.orphans:
            print("\nDry run: re-run with --delete to remove the orphans listed above.")
    return 0


if __name__ == "__main__":
    # The report is the program's output; log lines must not mix into it (so `--json | jq` works).
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(sys.stderr))
    sys.exit(main())
