"""Backup retention (ops/prune_backups.py): grandfather-father-son keeping, dry run by default, never touches other files."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "prune_backups", Path(__file__).resolve().parents[2] / "ops" / "prune_backups.py"
)
prune_mod = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(prune_mod)

BASE = datetime(2026, 10, 18, 3, 0, 0, tzinfo=UTC)


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def make(directory: Path, when: datetime, evidence: bool = False, encrypted: bool = False) -> str:
    s = stamp(when)
    (directory / f"gg-db-{s}.dump{'.age' if encrypted else ''}").write_bytes(b"d")
    (directory / f"gg-db-{s}.manifest").write_text("m")
    if evidence:
        (directory / f"evidence-{s}.tgz{'.age' if encrypted else ''}").write_bytes(b"e")
    return s


def test_keeps_the_newest_per_day_week_and_month_and_drops_the_rest(tmp_path):
    stamps = [make(tmp_path, BASE - timedelta(days=d)) for d in range(0, 120)]  # one backup a day for ~4 months
    keep, removed = prune_mod.prune(tmp_path, daily=7, weekly=4, monthly=3, apply=True)
    newest7 = {stamp(BASE - timedelta(days=d)) for d in range(7)}
    assert newest7 <= set(keep)  # the last 7 days are all kept
    assert len(keep) < 20 and len(removed) > 0
    remaining = {p.name for p in tmp_path.iterdir()}
    for s in keep:
        assert f"gg-db-{s}.dump" in remaining and f"gg-db-{s}.manifest" in remaining
    gone = set(stamps) - set(keep)
    assert gone and all(f"gg-db-{s}.dump" not in remaining and f"gg-db-{s}.manifest" not in remaining for s in gone)


def test_two_backups_on_the_same_day_keep_only_the_newest_in_that_period():
    keep = prune_mod.choose_keep(
        ["20261018T030000Z", "20261018T150000Z", "20261017T030000Z"], daily=7, weekly=1, monthly=1
    )
    assert "20261018T150000Z" in keep and "20261018T030000Z" not in keep  # the later one represents the day
    assert "20261017T030000Z" in keep  # a different day


def test_a_dry_run_deletes_nothing(tmp_path):
    for d in range(30):
        make(tmp_path, BASE - timedelta(days=d))
    before = sorted(p.name for p in tmp_path.iterdir())
    keep, removed = prune_mod.prune(tmp_path, apply=False)
    assert removed and sorted(p.name for p in tmp_path.iterdir()) == before


def test_removing_a_backup_removes_its_evidence_archive_and_encrypted_files_too(tmp_path):
    old = make(tmp_path, BASE - timedelta(days=200), evidence=True, encrypted=True)
    make(tmp_path, BASE)
    prune_mod.prune(tmp_path, daily=1, weekly=1, monthly=1, apply=True)
    names = {p.name for p in tmp_path.iterdir()}
    assert not any(old in n for n in names)
    assert any(stamp(BASE) in n for n in names)


def test_unrelated_files_are_never_touched(tmp_path):
    (tmp_path / "notes.txt").write_text("keep me")
    (tmp_path / "gg-db-notatimestamp.dump").write_text("keep me too")
    (tmp_path / "other-20200101T000000Z.dump").write_text("not ours")
    make(tmp_path, BASE - timedelta(days=400))
    make(tmp_path, BASE)
    prune_mod.prune(tmp_path, daily=1, weekly=1, monthly=1, apply=True)
    assert (tmp_path / "notes.txt").exists() and (tmp_path / "gg-db-notatimestamp.dump").exists()
    assert (tmp_path / "other-20200101T000000Z.dump").exists()


@pytest.mark.parametrize("count", [0, 1, 2])
def test_few_backups_are_all_kept(tmp_path, count):
    for d in range(count):
        make(tmp_path, BASE - timedelta(days=d * 40))
    keep, removed = prune_mod.prune(tmp_path, apply=True)
    assert len(keep) == count and removed == []
