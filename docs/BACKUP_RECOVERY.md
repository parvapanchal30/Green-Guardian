# Backup and Recovery

A practical, tested procedure for the actual database provider. Read section 1 first: it changes what you must do.

## 1. The situation today (important)
- The development database is a **Supabase project on the Free plan**. Supabase's automatic daily backups and point-in-time recovery are **not included in the Free plan**, so *there is currently no provider-side backup at all*. Free projects are also paused after a period of inactivity. **Our own logical backups (below) are the only protection of the data.** (Checked 2026-10-18 through the Supabase connector: organization plan `free`. Re-check if you upgrade; a paid plan adds provider backups, which complement but do not replace these.)
- The GitHub repository is **public**. Backups contain personal and operational data. They must **never** be committed, attached to a GitHub Actions run, or stored as workflow artifacts (artifacts of public repositories can be downloaded by other GitHub users). `ops/backup.sh` refuses to write inside the repository unless the directory is git-ignored.
- What the development database holds today is test data. The procedure is written for the day it holds real data, and it is cheap to start now.

## 2. What is backed up, and what is not
| Item | Backed up by | Notes |
|---|---|---|
| Application schema `greenguardian` (all tables, indexes, constraints, triggers, RLS settings, generated PostGIS columns' definitions, data) | `ops/backup.sh` (`pg_dump --format=custom --schema=greenguardian`) | the whole application state |
| Evidence photos | `ops/backup.sh` with `EVIDENCE_DIR` set (tar.gz), or your object store's own versioning/replication | not in the database |
| Migrations, code, docs | Git | |
| Secrets (`JWT_SECRET`, `DATABASE_URL`) | your secret store / password manager | never in a backup; losing `JWT_SECRET` only signs everyone out |
| PostGIS extension and `spatial_ref_sys` | **not dumped**: provider-managed; recreated by `CREATE EXTENSION postgis SCHEMA extensions` | the restore script does this |
| Other schemas (Supabase `auth`, `storage`, ...) | not backed up | GreenGuardian does not use them |

## 3. Objectives
| | Target | How |
|---|---|---|
| Recovery point (data you can lose) | 24 hours | a backup every day, plus one immediately before every migration |
| Recovery time (how long to be back) | about 2 hours | restore into a new database, repoint `DATABASE_URL`, verify |
| Frequency | daily + before each release/migration | cron or Task Scheduler (section 5) |
| Retention | 7 daily, 4 weekly, 3 monthly | `ops/prune_backups.py` (dry run by default) |
| Restore rehearsal | after the first backup, then monthly and after any migration that changes tables | `ops/restore-test.sh` |
Tighten the targets (hourly backups, longer retention) when real users depend on the data; the audit retention setting (`AUDIT_RETENTION_DAYS`, default 730) does not purge backups, so old audit records persist in older backups until those backups are pruned: take that into account for any legal retention requirement.

## 4. One-time setup on a machine that takes backups
1. **PostgreSQL 17 client tools** (`pg_dump`, `pg_restore`, `psql`). The dump tool must be the same major version as the server or newer (the script refuses otherwise). Supabase runs PostgreSQL 17. On Windows the lightest route is the EnterpriseDB "binaries" zip for PostgreSQL 17 (download from enterprisedb.com, extract, add its `bin` directory to `PATH`); the full installer or `winget install PostgreSQL.PostgreSQL.17` also works. On Linux install `postgresql-client-17` from the PostgreSQL apt repository. *This is not installed on the development machine yet, so the first real backup of Supabase has not been taken.*
2. **Connection string**: use the Supabase **Session pooler** string (port 5432) or the direct connection, **not** the transaction pooler (port 6543: `pg_dump` does not work through it). The role must bypass row-level security (every table has RLS enabled with no policies, so a role without `BYPASSRLS` would dump empty tables); the Supabase `postgres` role does.
3. **Where backups go**: a directory **outside the repository** on an encrypted disk (BitLocker/FileVault/LUKS), mode 700, and a second copy on a different device or a private cloud bucket. Optional file-level encryption: install `age`, generate a key pair, keep the *private* key offline, and set `BACKUP_AGE_RECIPIENT` to the public key.
4. **Secrets handling**: keep the URL in an environment variable set by your scheduler or a file readable only by you (mode 600) and outside the repository. Never paste it into a command line that is logged, a shell history file, a ticket or chat.

## 5. Taking a backup
```bash
export BACKUP_DATABASE_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres'
export BACKUP_DIR=/secure/greenguardian-backups          # outside the repository
export EVIDENCE_DIR=/path/to/backend/var/storage          # optional: also archive the photos
# export BACKUP_AGE_RECIPIENT=age1...                      # optional: encrypt
bash ops/backup.sh
python ops/prune_backups.py --dir "$BACKUP_DIR"            # dry run: shows what retention would remove
python ops/prune_backups.py --dir "$BACKUP_DIR" --apply    # do it
```
Output per backup: `gg-db-<UTC stamp>.dump` (the data), `gg-db-<UTC stamp>.manifest` (row count of every table, migration revision, centroid counts, SHA-256 of the dump), optionally `evidence-<stamp>.tgz`. The manifest is what makes a restore *verifiable* instead of merely "it ran".

Scheduling: Linux `0 2 * * * /path/wrapper.sh` where the wrapper exports the variables and runs the two commands; Windows Task Scheduler daily at 02:00 running `bash ops/backup.sh` through Git Bash with the environment set in the task. Alert if no new `.manifest` appeared in 26 hours.

## 6. Proving a backup restores (do this before you need it)
Restore into a **scratch** PostgreSQL+PostGIS server, never the live database:
```bash
# a throwaway local server, for example:  docker run --rm -d -p 55432:5432 -e POSTGRES_PASSWORD=scratch postgis/postgis:17-3.5
export RESTORE_ADMIN_URL='postgresql://postgres:scratch@localhost:55432'     # superuser URL, no database name
bash ops/restore-test.sh /secure/greenguardian-backups/gg-db-<stamp>.dump    # decrypt first if it ends in .age
```
The script (1) checks the dump's checksum, (2) creates `gg_restore_test_*` from `template0`, installs PostGIS into the `extensions` schema, (3) restores, (4) compares migration revision, every table's row count and the generated PostGIS centroids with the manifest, (5) confirms RLS is on for every table, the audit and history append-only triggers exist, the two GiST indexes exist and a spatial query works, then (6) drops the scratch database. Exit code 0 = verified.

Safeguards, each proven by a test that must fail (CI job `backup-restore`): it refuses any target name that is not `gg_restore_test_*` (so it can never drop `postgres` or your real database); it refuses a server that is the same as `BACKUP_DATABASE_URL` unless `ALLOW_SAME_SERVER=1`; a tampered manifest or a corrupted dump fails verification; `ops/backup.sh` refuses a destination inside the repository that is not git-ignored and a `pg_dump` older than the server.

## 7. Disaster recovery (the live database is lost or damaged)
1. Stop writes: stop the API and worker, or put the site in maintenance.
2. Pick the newest backup whose restore test passed (not just the newest file). Decrypt it if needed.
3. Create the target: a new Supabase project (or any PostgreSQL 15+ with PostGIS). In its SQL editor run `CREATE SCHEMA extensions; CREATE EXTENSION postgis SCHEMA extensions;`.
4. Restore: `pg_restore --no-owner --no-privileges --exit-on-error --dbname "<new database URL>" gg-db-<stamp>.dump`.
5. Verify: `cd backend && DATABASE_URL=<new> alembic current` (expect the manifest's revision), `alembic check`, `python -m app.tools.check_db` (expect `RLS enabled on N/N`), and compare table counts with the manifest.
6. Restore the evidence files: `tar -xzf evidence-<stamp>.tgz -C <storage dir>`.
7. Repoint: set `DATABASE_URL` in the secret store to the new database, restart the API and worker, run the smoke checks (sign in, open an asset with a photo, map).
8. Record what happened, the data-loss window (time of the backup vs the incident) and what was done to prevent a repeat.
`--no-privileges` means grants are not restored: on a hosted provider make sure the provider's API roles (`anon`, `authenticated`) have no privileges on the application schema (`check_db` reports it, and migration 0002 documents the SQL).
**Recovering one table or a few rows** without touching the rest: restore into a scratch database (section 6 with `KEEP=1`), then copy the rows across with `psql \copy` or `INSERT ... SELECT`; do not restore over the live table.

## 8. PostGIS-specific points
- Generated columns: `centroid` is a *generated stored* column computed from latitude and longitude. `pg_dump` stores the definition, not the values, and the restore recomputes them. The restore test compares the number of non-null centroids with the manifest to prove this worked.
- The extension must exist **before** `pg_restore` (it provides the `geometry` type and `ST_*` functions), in the same schema name (`extensions`) the dump refers to. The restore script does this; for a manual restore follow step 3 above.
- Version differences: restoring into the same or a newer PostGIS minor version is safe. A different PostGIS **major** version needs `SELECT postgis_extensions_upgrade();` and a review; test it in a scratch database first. The source is PostGIS 3.3 (Supabase), CI uses 3.5.
- `spatial_ref_sys` belongs to the extension and is not part of the dump.

## 9. Security of backups
Encrypt at rest (disk encryption plus optional `age`), restrict access to the people who can already read production data, keep at least one copy off the machine that produced it, never put credentials or dumps in Git, tickets or chat, delete expired backups with the prune script (retention is part of your privacy obligations), and treat a lost backup like a data breach. Backups include password hashes (argon2id), refresh-token hashes and audit records.

## 10. What is verified
| Claim | Evidence |
|---|---|
| `backup.sh` produces a dump and manifest; `restore-test.sh` restores into a scratch PostGIS database and verifies counts, migration revision, RLS, triggers, indexes, centroids and a spatial query; tampering, corruption and unsafe targets are rejected; the dump has mode 600; no scratch database is left behind | CI job `backup-restore` (PostgreSQL 17 server and client tools) |
| Backup retention keeps the newest backup per day/week/month and never touches other files | `backend/tests/test_ops_prune_backups.py` |
| **Not verified**: a backup of the real Supabase database (the PostgreSQL 17 client tools are not installed on the development machine; do step 4 and run section 5 once), restore into a new Supabase project, age encryption (script path untested), scheduling |  |
