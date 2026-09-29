"""Device identity model + encrypted TOTP secret.

Revision ID: 009_device_identity_and_totp
Revises: 008_reconcile_schema_with_models
Create Date: 2026-09-27

Devices
-------
The API contract, services, repositories and tests all describe a device as
``device_uuid`` (install-scoped identity chosen by the client), ``platform``,
``push_token``, ``app_version``, ``is_primary`` and ``last_seen_at`` — the ORM
model still carried an older shape (``fcm_token``, ``last_used_at``,
``device_name``, ``os_name``, ``os_version``), so device registration could not
work at all. This revision moves the table to the contract:

* ``fcm_token`` -> ``push_token`` and ``last_used_at`` -> ``last_seen_at``
  (in-place renames; data kept)
* new ``device_uuid`` (legacy rows: the row id, which is unique), ``platform``
  (native enum ``device_platform_enum``; legacy rows: from ``os_name`` when it says
  ios/web, otherwise ``android`` — the Android app was the only client) and
  ``is_primary`` (legacy rows: each user's oldest active device)
* ``UNIQUE (user_id, device_uuid)``; ``idx_devices_fcm_token`` ->
  ``idx_devices_push_token``
* dropped ``device_name`` / ``os_name`` / ``os_version``: never written or read
  by the application.

Users
-----
``users.mfa_secret`` (plaintext ``VARCHAR``, never used by the code) is replaced
by ``users.totp_secret_encrypted`` (AES-256-GCM, what ``AuthService`` and
``UserRepository.enable_mfa`` have always assumed). Existing values are
encrypted in place, not discarded.

Users also gain ``created_by_id`` (FK ``users.id``, ``ON DELETE SET NULL``): the
admin who created the account. The repository/service layer and tests have always
written and asserted it, but the column did not exist.

Idempotent like 008 (each step inspects the live schema first).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_device_identity_and_totp"
down_revision: Union[str, None] = "008_reconcile_schema_with_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _uniques(table: str) -> set[str]:
    return {u["name"] for u in sa.inspect(op.get_bind()).get_unique_constraints(table)}


def upgrade() -> None:
    # ── devices ──────────────────────────────────────────────────────────────
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'device_platform_enum') "
        "THEN CREATE TYPE device_platform_enum AS ENUM ('android', 'ios', 'web'); END IF; END $$;"
    )
    cols = _cols("devices")
    if "fcm_token" in cols and "push_token" not in cols:
        op.execute("ALTER TABLE devices RENAME COLUMN fcm_token TO push_token")
    if "last_used_at" in cols and "last_seen_at" not in cols:
        op.execute("ALTER TABLE devices RENAME COLUMN last_used_at TO last_seen_at")
    cols = _cols("devices")

    if "device_uuid" not in cols:
        op.execute("ALTER TABLE devices ADD COLUMN device_uuid VARCHAR(255)")
        op.execute("UPDATE devices SET device_uuid = id")
        op.execute("ALTER TABLE devices ALTER COLUMN device_uuid SET NOT NULL")
    if "platform" not in cols:
        op.execute("ALTER TABLE devices ADD COLUMN platform device_platform_enum")
        os_name = "lower(os_name)" if "os_name" in cols else "NULL"
        op.execute(
            f"UPDATE devices SET platform = (CASE WHEN {os_name} IN ('ios', 'web') "
            f"THEN {os_name} ELSE 'android' END)::device_platform_enum"
        )
        op.execute("ALTER TABLE devices ALTER COLUMN platform SET NOT NULL")
    if "is_primary" not in cols:
        op.execute("ALTER TABLE devices ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT false")
        op.execute(
            """
            UPDATE devices d SET is_primary = true
            WHERE d.is_active AND d.id = (
                SELECT x.id FROM devices x
                WHERE x.user_id = d.user_id AND x.is_active
                ORDER BY x.created_at ASC, x.id ASC LIMIT 1
            )
            """
        )
        op.execute("ALTER TABLE devices ALTER COLUMN is_primary DROP DEFAULT")

    for legacy in ("device_name", "os_name", "os_version"):
        if legacy in cols:
            op.drop_column("devices", legacy)

    if "uq_devices_user_device_uuid" not in _uniques("devices"):
        op.create_unique_constraint("uq_devices_user_device_uuid", "devices", ["user_id", "device_uuid"])
    if "idx_devices_fcm_token" in _indexes("devices"):
        op.drop_index("idx_devices_fcm_token", table_name="devices")
    if "idx_devices_push_token" not in _indexes("devices"):
        op.create_index("idx_devices_push_token", "devices", ["push_token"])

    # ── users.created_by_id ──────────────────────────────────────────────────
    if "created_by_id" not in _cols("users"):
        op.add_column("users", sa.Column("created_by_id", sa.String(36), nullable=True))
        op.create_foreign_key(
            "users_created_by_id_fkey", "users", "users", ["created_by_id"], ["id"], ondelete="SET NULL"
        )

    # ── users.totp_secret_encrypted ──────────────────────────────────────────
    ucols = _cols("users")
    if "totp_secret_encrypted" not in ucols:
        op.add_column("users", sa.Column("totp_secret_encrypted", sa.LargeBinary(), nullable=True))
    if "mfa_secret" in ucols:
        from app.core.security import encrypt_field  # same key/algorithm the app uses

        bind = op.get_bind()
        rows = bind.execute(sa.text("SELECT id, mfa_secret FROM users WHERE mfa_secret IS NOT NULL")).all()
        for user_id, secret in rows:
            bind.execute(
                sa.text("UPDATE users SET totp_secret_encrypted = :v WHERE id = :id"),
                {"v": encrypt_field(secret), "id": user_id},
            )
        op.drop_column("users", "mfa_secret")


def downgrade() -> None:
    """Restores the old *shape*; ``mfa_secret`` is not repopulated (it was encrypted)."""
    if "created_by_id" in _cols("users"):
        op.drop_constraint("users_created_by_id_fkey", "users", type_="foreignkey")
        op.drop_column("users", "created_by_id")
    op.add_column("users", sa.Column("mfa_secret", sa.String(255), nullable=True))
    op.drop_column("users", "totp_secret_encrypted")

    if "idx_devices_push_token" in _indexes("devices"):
        op.drop_index("idx_devices_push_token", table_name="devices")
    if "uq_devices_user_device_uuid" in _uniques("devices"):
        op.drop_constraint("uq_devices_user_device_uuid", "devices", type_="unique")
    op.add_column("devices", sa.Column("device_name", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("os_name", sa.String(50), nullable=True))
    op.add_column("devices", sa.Column("os_version", sa.String(50), nullable=True))
    for col in ("is_primary", "platform", "device_uuid"):
        op.drop_column("devices", col)
    op.execute("DROP TYPE IF EXISTS device_platform_enum")
    op.execute("ALTER TABLE devices RENAME COLUMN last_seen_at TO last_used_at")
    op.execute("ALTER TABLE devices RENAME COLUMN push_token TO fcm_token")
    op.create_index("idx_devices_fcm_token", "devices", ["fcm_token"])
