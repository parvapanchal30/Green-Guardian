#!/usr/bin/env bash
# Logical backup of the GreenGuardian application schema (docs/BACKUP_RECOVERY.md).
#
#   BACKUP_DATABASE_URL='postgresql://user:password@host:5432/dbname' ops/backup.sh
#
# Produces, in $BACKUP_DIR (default ./backups, which is git-ignored):
#   gg-db-<UTC timestamp>.dump       pg_dump custom format, application schema only (no ownership, no grants)
#   gg-db-<UTC timestamp>.manifest   what the dump should contain: row count per table, migration revision, checksum
#   evidence-<timestamp>.tgz         (only if EVIDENCE_DIR is set) the stored photos
# Optional: BACKUP_AGE_RECIPIENT=<age public key> encrypts every artefact with `age` and removes the plaintext.
#
# Safety: the connection string is read from the environment only (never a file in Git); the script refuses to write
# into a Git work tree unless the directory is ignored; files are created with mode 600.
set -euo pipefail

: "${BACKUP_DATABASE_URL:?set BACKUP_DATABASE_URL (a libpq connection URL; keep it out of Git)}"
APP_SCHEMA="${APP_SCHEMA:-greenguardian}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
case "$APP_SCHEMA" in *[!a-z0-9_]*|"") echo "APP_SCHEMA must be a simple lowercase identifier" >&2; exit 2;; esac

umask 077
mkdir -p "$BACKUP_DIR"

# Never write backups where `git add .` could pick them up.
if git -C "$BACKUP_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if ! git -C "$BACKUP_DIR" check-ignore -q --no-index "$BACKUP_DIR/.probe" 2>/dev/null \
     && ! (cd "$BACKUP_DIR" && git check-ignore -q --no-index ./.probe) 2>/dev/null; then
    echo "REFUSED: $BACKUP_DIR is inside a Git work tree and is not git-ignored. Use a directory outside the repository." >&2
    exit 3
  fi
fi

q() { psql "$BACKUP_DATABASE_URL" --no-psqlrc -X -At -v ON_ERROR_STOP=1 -c "$1"; }

# pg_dump must be at least as new as the server, otherwise it refuses (or silently omits newer features).
server_major=$(( $(q "show server_version_num") / 10000 ))
client_major=$(pg_dump --version | sed -E 's/[^0-9]*([0-9]+).*/\1/')
if [ "$client_major" -lt "$server_major" ]; then
  echo "REFUSED: pg_dump is version $client_major but the server is $server_major. Install the PostgreSQL $server_major client tools." >&2
  exit 4
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="$BACKUP_DIR/gg-db-$STAMP.dump"
MANIFEST="$BACKUP_DIR/gg-db-$STAMP.manifest"

echo "dumping schema '$APP_SCHEMA' (server $server_major, pg_dump $client_major) ..."
pg_dump "$BACKUP_DATABASE_URL" --format=custom --compress=9 --no-owner --no-privileges \
        --schema="$APP_SCHEMA" --file="$DUMP"

# The manifest is computed from the live database right after the dump, so a restore can be checked against it.
sha=$(sha256sum "$DUMP" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$DUMP" | cut -d' ' -f1)
{
  echo "# GreenGuardian backup manifest"
  echo "created_utc	$STAMP"
  echo "schema	$APP_SCHEMA"
  echo "server_major	$server_major"
  echo "dump_file	$(basename "$DUMP")"
  echo "sha256	$sha"
  echo "alembic_revision	$(q "select version_num from \"$APP_SCHEMA\".alembic_version")"
  echo "centroids_locations	$(q "select count(*) from \"$APP_SCHEMA\".locations where centroid is not null")"
  echo "centroids_assets	$(q "select count(*) from \"$APP_SCHEMA\".biological_assets where centroid is not null")"
  for t in $(q "select table_name from information_schema.tables where table_schema='$APP_SCHEMA' and table_type='BASE TABLE' order by 1"); do
    echo "table:$t	$(q "select count(*) from \"$APP_SCHEMA\".\"$t\"")"
  done
} > "$MANIFEST"

if [ -n "${EVIDENCE_DIR:-}" ] && [ -d "$EVIDENCE_DIR" ]; then
  tar -czf "$BACKUP_DIR/evidence-$STAMP.tgz" -C "$EVIDENCE_DIR" .
  echo "evidence_archive	evidence-$STAMP.tgz" >> "$MANIFEST"
fi

if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
  command -v age >/dev/null || { echo "BACKUP_AGE_RECIPIENT is set but 'age' is not installed" >&2; exit 5; }
  for f in "$DUMP" "$BACKUP_DIR"/evidence-"$STAMP".tgz; do
    [ -f "$f" ] || continue
    age -r "$BACKUP_AGE_RECIPIENT" -o "$f.age" "$f" && rm -f "$f"
  done
  echo "encrypted with age; plaintext removed (decrypt with: age -d -i <identity> -o <file> <file>.age)"
else
  echo "WARNING: this backup is NOT encrypted. Keep it on an encrypted disk or set BACKUP_AGE_RECIPIENT." >&2
fi

echo "OK  $MANIFEST"
