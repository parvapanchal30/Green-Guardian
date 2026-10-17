"""audit retention guard: allow the retention purge (and nothing else) to delete old audit records

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-18

The audit table's trigger used the shared `gg_forbid_mutation()` function, which rejects every UPDATE and DELETE and
therefore makes retention impossible. This revision gives the audit table its own guard:

  * UPDATE is always rejected.
  * DELETE is rejected unless the transaction set `gg.audit_purge = on` (only the retention job does) AND the row is
    older than 30 days. The 30-day floor lives in the database on purpose: a bug or a mistyped retention setting in the
    application cannot remove recent history. (Must match MIN_RETENTION_DAYS in app/modules/audit/retention.py.)

This protects against bugs and accidents, not against a database administrator, who can always alter the trigger.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

FUNCTION = "gg_audit_guard"


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_pg():
        return
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
          IF TG_OP = 'DELETE'
             AND coalesce(current_setting('gg.audit_purge', true), '') = 'on'
             AND OLD.occurred_at < now() - interval '30 days' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'append-only table %.%: % is not allowed (only the retention purge may delete records older than 30 days)',
            TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'integrity_constraint_violation';
        END
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {FUNCTION}() FROM PUBLIC")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events")
    op.execute(
        f"CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
        f"FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()"
    )


def downgrade() -> None:
    if not _is_pg():
        return
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_append_only ON audit_events")
    op.execute(
        "CREATE TRIGGER trg_audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION gg_forbid_mutation()"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")
