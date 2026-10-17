#!/usr/bin/env bash
# Prove that a backup can actually be restored, in an isolated SCRATCH database, never the live one.
# (docs/BACKUP_RECOVERY.md)
#
#   RESTORE_ADMIN_URL='postgresql://postgres:password@localhost:5432' ops/restore-test.sh backups/gg-db-<stamp>.dump
#
# RESTORE_ADMIN_URL is a superuser URL of a scratch PostgreSQL+PostGIS server WITHOUT a database name. The script
# creates `gg_restore_test_*`, installs PostGIS into the `extensions` schema (as the migrations do on hosted
# providers), restores, compares the result with the manifest written at backup time, and drops the scratch database
# (KEEP=1 keeps it for inspection). It only ever drops a database whose name it created itself.
#
# Exit codes: 0 verified, 1 verification failed, 2 bad usage or refused target, 3 refused: same server as the source.
set -euo pipefail

DUMP="${1:?usage: restore-test.sh <backup .dump file>}"
: "${RESTORE_ADMIN_URL:?set RESTORE_ADMIN_URL (superuser URL of a scratch server, no database name)}"
MANIFEST="${DUMP%.dump}.manifest"
[ -f "$DUMP" ] || { echo "no such dump: $DUMP" >&2; exit 2; }
[ -f "$MANIFEST" ] || { echo "no manifest next to the dump: $MANIFEST" >&2; exit 2; }
case "$DUMP" in *.age) echo "decrypt the backup first (age -d)" >&2; exit 2;; esac

TARGET_DB="${TARGET_DB:-gg_restore_test_$(date -u +%Y%m%d%H%M%S)_$$}"
if ! [[ "$TARGET_DB" =~ ^gg_restore_test_[a-z0-9_]+$ ]]; then
  echo "REFUSED: TARGET_DB must look like gg_restore_test_<something> (got '$TARGET_DB')" >&2
  exit 2
fi

# Refuse to restore onto the very server the backup came from unless the operator says it is a deliberate scratch copy.
host_of() { printf '%s' "$1" | sed -E 's#^[a-z+]+://([^@/]*@)?([^/:?]+)(:([0-9]+))?.*#\2:\4#'; }
if [ -n "${BACKUP_DATABASE_URL:-}" ] && [ "$(host_of "$BACKUP_DATABASE_URL")" = "$(host_of "$RESTORE_ADMIN_URL")" ] \
   && [ "${ALLOW_SAME_SERVER:-0}" != "1" ]; then
  echo "REFUSED: RESTORE_ADMIN_URL points at the same server as BACKUP_DATABASE_URL. Restore tests belong on a scratch server (set ALLOW_SAME_SERVER=1 only if this server is itself disposable)." >&2
  exit 3
fi

ADMIN="${RESTORE_ADMIN_URL%/}/postgres"
TARGET="${RESTORE_ADMIN_URL%/}/$TARGET_DB"
psqlq() { psql "$1" --no-psqlrc -X -At -v ON_ERROR_STOP=1 -c "$2"; }
mval() { awk -F'\t' -v k="$1" '$1==k {print $2}' "$MANIFEST"; }

SCHEMA="$(mval schema)"
cleanup() {
  if [ "${KEEP:-0}" = "1" ]; then echo "kept scratch database $TARGET_DB"; return; fi
  psqlq "$ADMIN" "DROP DATABASE IF EXISTS \"$TARGET_DB\"" >/dev/null 2>&1 || true
}
trap cleanup EXIT

fail=0
check() { # check <label> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "  PASS  $1 ($3)"; else echo "  FAIL  $1: expected $2, got $3"; fail=1; fi
}

echo "1) checksum"
actual_sha=$( (sha256sum "$DUMP" 2>/dev/null || shasum -a 256 "$DUMP") | cut -d' ' -f1)
check "dump file matches the manifest checksum" "$(mval sha256)" "$actual_sha"

echo "2) restore into scratch database $TARGET_DB"
psqlq "$ADMIN" "CREATE DATABASE \"$TARGET_DB\" TEMPLATE template0" >/dev/null
psqlq "$TARGET" "CREATE SCHEMA extensions; CREATE EXTENSION postgis SCHEMA extensions" >/dev/null
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$TARGET" "$DUMP"
echo "  restored"

echo "3) verify against the manifest"
check "migration revision" "$(mval alembic_revision)" "$(psqlq "$TARGET" "select version_num from \"$SCHEMA\".alembic_version")"
while IFS=$'\t' read -r key val; do
  case "$key" in
    table:*) t="${key#table:}"; check "rows in $t" "$val" "$(psqlq "$TARGET" "select count(*) from \"$SCHEMA\".\"$t\"")";;
  esac
done < "$MANIFEST"
check "generated PostGIS centroids (locations)" "$(mval centroids_locations)" "$(psqlq "$TARGET" "select count(*) from \"$SCHEMA\".locations where centroid is not null")"
check "generated PostGIS centroids (assets)" "$(mval centroids_assets)" "$(psqlq "$TARGET" "select count(*) from \"$SCHEMA\".biological_assets where centroid is not null")"

echo "4) verify the security and integrity features survived"
tables=$(psqlq "$TARGET" "select count(*) from pg_tables where schemaname='$SCHEMA'")
check "row-level security enabled on every table" "$tables" "$(psqlq "$TARGET" "select count(*) from pg_tables where schemaname='$SCHEMA' and rowsecurity")"
check "audit trail trigger present" "1" "$(psqlq "$TARGET" "select count(*) from pg_trigger where tgname='trg_audit_events_append_only' and not tgisinternal")"
check "append-only triggers on history tables" "3" "$(psqlq "$TARGET" "select count(*) from pg_trigger where tgname in ('trg_observations_append_only','trg_issue_status_history_append_only','trg_task_status_history_append_only') and not tgisinternal")"
check "PostGIS spatial indexes present" "2" "$(psqlq "$TARGET" "select count(*) from pg_indexes where schemaname='$SCHEMA' and indexname in ('ix_locations_centroid_gist','ix_biological_assets_centroid_gist')")"
check "spatial query works on restored data" "ok" "$(psqlq "$TARGET" "select case when count(*) >= 0 then 'ok' end from \"$SCHEMA\".biological_assets where centroid is not null and extensions.ST_DWithin(centroid, extensions.ST_SetSRID(extensions.ST_MakePoint(0,0),4326), 360)")"

if [ "$fail" -eq 0 ]; then echo "RESULT: restore verified"; else echo "RESULT: VERIFICATION FAILED" >&2; exit 1; fi
