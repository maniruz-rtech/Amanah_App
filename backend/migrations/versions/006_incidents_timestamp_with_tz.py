"""Promote incidents timestamp columns to TIMESTAMP WITH TIME ZONE.

The ORM passes `datetime.now(UTC)` (timezone-aware) but the original
schema created `started_at`, `resolved_at`, and `canceled_at` as
``TIMESTAMP WITHOUT TIME ZONE``. asyncpg then raises ``DataError: can't
subtract offset-naive and offset-aware datetimes`` on the SOS-create
path.

The other timestamp columns on the same table (`created_at`,
`updated_at`, `deleted_at`) are already WITH TIME ZONE — this migration
brings the remaining three into alignment.

Idempotent: each ALTER is wrapped in a DO block that only runs when the
column is still timezone-less.

Revision ID: 006_incidents_timestamp_with_tz
Revises: 005_create_missing_pg_enums
Create Date: 2026-05-22
"""
from alembic import op


revision = "006_incidents_timestamp_with_tz"
down_revision = "005_create_missing_pg_enums"
branch_labels = None
depends_on = None


_COLUMNS = ("started_at", "resolved_at", "canceled_at")


def upgrade() -> None:
    for col in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'incidents'
                      AND column_name = '{col}'
                      AND data_type   = 'timestamp without time zone'
                ) THEN
                    ALTER TABLE incidents
                    ALTER COLUMN {col} TYPE TIMESTAMP WITH TIME ZONE
                    USING {col} AT TIME ZONE 'UTC';
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for col in _COLUMNS:
        op.execute(
            f"ALTER TABLE incidents ALTER COLUMN {col} TYPE TIMESTAMP WITHOUT TIME ZONE;"
        )
