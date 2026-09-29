"""Add deleted_at column to incidents (SoftDeleteMixin drift fix).

The Incident ORM model inherits from ``SoftDeleteMixin`` which adds a
``deleted_at`` column. The original ``001_initial_schema.py`` migration
omits the column on ``incidents``, causing every INSERT on the table to
fail with ``UndefinedColumnError: column "deleted_at" of relation
"incidents" does not exist`` (the SOS path).

This migration adds it idempotently (DO block with IF NOT EXISTS predicate)
so re-applying on an already-fixed DB is a no-op.

Revision ID: 004_add_incidents_deleted_at
Revises: 003_add_missing_updated_at
Create Date: 2026-05-22
"""
from alembic import op


revision = "004_add_incidents_deleted_at"
down_revision = "003_add_missing_updated_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'incidents' AND column_name = 'deleted_at'
            ) THEN
                ALTER TABLE incidents
                ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE NULL;
                CREATE INDEX IF NOT EXISTS ix_incidents_deleted_at
                  ON incidents (deleted_at);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_deleted_at", table_name="incidents")
    op.drop_column("incidents", "deleted_at")
