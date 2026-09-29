"""Add updated_at column to refresh_tokens

The ORM ``RefreshToken`` model inherits from ``Base`` which includes both
``created_at`` and ``updated_at`` (server_default + onupdate), but the
original migration ``001_initial_schema.py`` only created ``created_at``
on ``refresh_tokens``. The INSERT from ``AuthService.login`` therefore
fails with ``UndefinedColumnError: column "updated_at" of relation
"refresh_tokens" does not exist``.

This revision corrects that drift. Idempotent — uses IF NOT EXISTS via a
DO block so re-applying on a fixed DB is a no-op.

Revision ID: 002_refresh_tokens_updated_at
Revises: 001_initial
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa


revision = "002_refresh_tokens_updated_at"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'refresh_tokens' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE refresh_tokens
                ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE
                NOT NULL DEFAULT NOW();
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "updated_at")
