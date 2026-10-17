#!/usr/bin/env bash
# CI proof of the backup/restore procedure (see .github/workflows/ci.yml, job `backup-restore`).
# Needs: a PostGIS server on localhost:5432 (superuser `postgres`, trust auth), PostgreSQL client tools of the same
# major version, and the backend installed (pip install -e backend). Run from the repository root.
#
# 1. migrate a fresh database to head and load a fixture   2. back it up with ops/backup.sh
# 3. restore into a scratch database and verify            4. prove the safeguards and the verification can FAIL
set -euo pipefail

SERVER="postgresql://postgres@localhost:5432"
OUT="${RUNNER_TEMP:-/tmp}/gg-backups"
rm -rf "$OUT"; mkdir -p "$OUT"

echo "== 1. fresh source database, migrated and loaded"
psql "$SERVER/postgres" -v ON_ERROR_STOP=1 -c "CREATE DATABASE gg_backup_src TEMPLATE template0"
export DATABASE_URL="$SERVER/gg_backup_src" DB_SSLMODE=disable POSTGIS_SCHEMA=extensions ENV=test
(cd backend && alembic upgrade head && python -m app.tools.backup_fixture)

echo "== 2. back it up"
export BACKUP_DATABASE_URL="$SERVER/gg_backup_src" BACKUP_DIR="$OUT"
bash ops/backup.sh
DUMP=$(ls "$OUT"/gg-db-*.dump)
MANIFEST="${DUMP%.dump}.manifest"
echo "-- manifest:"; cat "$MANIFEST"
perm=$(stat -c %a "$DUMP"); [ "$perm" = "600" ] || { echo "dump permissions are $perm, expected 600"; exit 1; }

echo "== 3. restore into a scratch database and verify"
export RESTORE_ADMIN_URL="$SERVER" ALLOW_SAME_SERVER=1
bash ops/restore-test.sh "$DUMP"

echo "== 4. the safeguards and the verification can fail"
expect_exit() { # expect_exit <code> <description> <command...>
  want="$1"; desc="$2"; shift 2
  set +e; "$@" >/dev/null 2>&1; got=$?; set -e
  [ "$got" -eq "$want" ] || { echo "FAIL: $desc (exit $got, expected $want)"; exit 1; }
  echo "  PASS  $desc (exit $got)"
}
# a tampered manifest (one count changed) must be detected
cp "$DUMP" "$OUT/tampered.dump"; sed 's/^table:observations\t.*/table:observations\t999/' "$MANIFEST" > "$OUT/tampered.manifest"
sha=$(sha256sum "$DUMP" | cut -d' ' -f1); sed -i "s/^sha256\t.*/sha256\t$sha/" "$OUT/tampered.manifest"
expect_exit 1 "a manifest that disagrees with the restored data fails verification" bash ops/restore-test.sh "$OUT/tampered.dump"
# a corrupted dump must be detected (checksum)
cp "$DUMP" "$OUT/corrupt.dump"; cp "$MANIFEST" "$OUT/corrupt.manifest"; printf 'x' >> "$OUT/corrupt.dump"
expect_exit 1 "a corrupted dump fails the checksum" bash ops/restore-test.sh "$OUT/corrupt.dump"
# the restore may never target a database that is not a scratch name
TARGET_DB=postgres expect_exit 2 "restoring into 'postgres' is refused" bash ops/restore-test.sh "$DUMP"
TARGET_DB=gg_backup_src expect_exit 2 "restoring into the source database is refused" bash ops/restore-test.sh "$DUMP"
# restoring onto the same server as the backup source is refused unless explicitly allowed
ALLOW_SAME_SERVER=0 expect_exit 3 "same-server restore is refused by default" bash ops/restore-test.sh "$DUMP"
# backup refuses a destination inside a Git work tree that is not ignored
mkdir -p ./untracked-backup-dir
BACKUP_DIR=./untracked-backup-dir expect_exit 3 "backup refuses a non-ignored directory inside the repository" bash ops/backup.sh
rmdir ./untracked-backup-dir

echo "== 5. no scratch databases left behind"
left=$(psql "$SERVER/postgres" -At -c "select count(*) from pg_database where datname like 'gg_restore_test_%'")
[ "$left" = "0" ] || { echo "leftover scratch databases: $left"; exit 1; }
echo "ALL BACKUP/RESTORE CHECKS PASSED"
