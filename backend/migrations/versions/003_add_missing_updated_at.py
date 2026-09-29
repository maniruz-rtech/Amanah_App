"""Add updated_at column to remaining schema-drift tables.

The ORM ``Base`` declares ``updated_at`` for every model, but the original
``001_initial_schema.py`` omitted the column on three tables:
  - audit_logs
  - incident_events
  - otp_requests

The drift surfaces as ``UndefinedColumnError`` on the first INSERT into
each of those tables. This revision closes the gap. Idempotent — uses an
``IF NOT EXISTS`` predicate so re-applying on a fixed DB is a no-op.

Revision ID: 003_add_missing_updated_at
Revises: 002_refresh_tokens_updated_at
Create Date: 2026-05-21
"""
from alembic import op


revision = "003_add_missing_updated_at"
down_revision = "002_refresh_tokens_updated_at"
branch_labels = None
depends_on = None

# Tables that should have `updated_at` per the ORM Base but were missed in 001.
_TABLES = ("audit_logs", "incident_events", "otp_requests")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = 'updated_at'
                ) THEN
                    ALTER TABLE {table}
                    ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE
                    NOT NULL DEFAULT NOW();
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "updated_at")
