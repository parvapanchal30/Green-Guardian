#!/usr/bin/env python3
"""Grandfather-father-son retention for backups made by ops/backup.sh.

Keeps the newest backup of each of the last N days, N ISO weeks and N months (default 7 / 4 / 3) and removes the rest,
together with each removed backup's manifest and evidence archive. DRY RUN unless --apply is given; it only ever
touches files named gg-db-<UTC timestamp>.* / evidence-<timestamp>.tgz[.age] inside the directory you point it at.

    python ops/prune_backups.py --dir /secure/backups            # show what would be removed
    python ops/prune_backups.py --dir /secure/backups --apply    # remove it
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

NAME = re.compile(r"^(?P<kind>gg-db|evidence)-(?P<stamp>\d{8}T\d{6}Z)\.(?P<ext>dump|manifest|tgz)(\.age)?$")


def parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def backups(directory: Path) -> dict[str, list[Path]]:
    """stamp -> every artefact of that backup."""
    groups: dict[str, list[Path]] = {}
    for p in directory.iterdir():
        m = NAME.match(p.name)
        if m and p.is_file():
            groups.setdefault(m["stamp"], []).append(p)
    return groups


def choose_keep(stamps: list[str], daily: int, weekly: int, monthly: int) -> set[str]:
    """Newest backup per day/ISO week/month, for the most recent `daily`/`weekly`/`monthly` distinct periods."""
    keep: set[str] = set()
    ordered = sorted(stamps, reverse=True)  # newest first
    for count, key in (
        (daily, lambda d: d.date().isoformat()),
        (weekly, lambda d: "%d-W%02d" % d.isocalendar()[:2]),
        (monthly, lambda d: d.strftime("%Y-%m")),
    ):
        seen: list[str] = []
        for s in ordered:
            k = key(parse_stamp(s))
            if k not in seen:
                seen.append(k)
                if len(seen) <= count:
                    keep.add(s)  # newest of this period (ordered is newest first)
    return keep


def prune(directory: Path, daily: int = 7, weekly: int = 4, monthly: int = 3, apply: bool = False) -> tuple[list[str], list[Path]]:
    groups = backups(directory)
    keep = choose_keep(list(groups), daily, weekly, monthly)
    removed: list[Path] = []
    for stamp in sorted(groups):
        if stamp in keep:
            continue
        for p in groups[stamp]:
            removed.append(p)
            if apply:
                p.unlink()
    return sorted(keep), removed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--daily", type=int, default=7)
    ap.add_argument("--weekly", type=int, default=4)
    ap.add_argument("--monthly", type=int, default=3)
    ap.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    a = ap.parse_args()
    keep, removed = prune(a.dir, a.daily, a.weekly, a.monthly, a.apply)
    print(f"keeping {len(keep)} backup(s): {', '.join(keep) or '-'}")
    for p in removed:
        print(("removed " if a.apply else "would remove ") + p.name)
    if not a.apply and removed:
        print("(dry run: pass --apply to delete)")


if __name__ == "__main__":
    main()
