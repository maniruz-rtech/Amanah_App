"""Add last_h3_cell_district / last_h3_cell_block / last_seen_at to users.

Populated by the periodic presence ping. The DISTRICT cell powers the
``GET /api/v1/users/nearby`` query that the Android Home tab consumes.

Idempotent: each ADD COLUMN is guarded by ``IF NOT EXISTS``.

Revision ID: 007_users_h3_columns
Revises: 006_incidents_timestamp_with_tz
Create Date: 2026-05-22
"""
from alembic import op


revision = "007_users_h3_columns"
down_revision = "006_incidents_timestamp_with_tz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'last_h3_cell_district'
            ) THEN
                ALTER TABLE users ADD COLUMN last_h3_cell_district VARCHAR(16);
                CREATE INDEX IF NOT EXISTS idx_users_last_h3_cell_district
                    ON users (last_h3_cell_district);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'last_h3_cell_block'
            ) THEN
                ALTER TABLE users ADD COLUMN last_h3_cell_block VARCHAR(16);
                CREATE INDEX IF NOT EXISTS idx_users_last_h3_cell_block
                    ON users (last_h3_cell_block);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'last_seen_at'
            ) THEN
                ALTER TABLE users ADD COLUMN last_seen_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index("idx_users_last_h3_cell_block",    table_name="users")
    op.drop_index("idx_users_last_h3_cell_district", table_name="users")
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "last_h3_cell_block")
    op.drop_column("users", "last_h3_cell_district")
