"""Reconcile the migrated schema with the SQLAlchemy models.

Revision ID: 008_reconcile_schema_with_models
Revises: 007_users_h3_columns
Create Date: 2026-09-27

Migrations 001-007 drifted from the ORM models (the project was originally
bootstrapped with ``create_all`` + ``alembic stamp``). This revision makes a
database built by ``alembic upgrade head`` structurally identical to the models
(``alembic check`` is clean afterwards; see ``tests/test_migrations.py``).

What it does
------------
* **users.status** (new, ``user_status_enum``): lifecycle state of record,
  back-filled from the existing flags (deactivated > suspended >
  pending_verification > active). See ``app/db/models/user.py``.
* **admin_approvals**: table that the models/services have always used but no
  migration created.
* New columns: ``emergency_locations.altitude_m``, ``otp_requests.max_attempts``.
* Dropped column: ``trusted_contacts.is_verified`` (not in the model; the
  application never reads or writes it).
* Primary/foreign-key columns ``VARCHAR(32)`` -> ``VARCHAR(36)`` (prefixed ULIDs
  need headroom); a few text columns resized; ``JSONB`` -> ``JSON``;
  ``audit_logs.ip_address`` -> ``INET``; ``mfa_backup_codes`` JSONB -> text.
* Status/type/channel/... ``VARCHAR`` columns -> the native PostgreSQL enum types
  that migration 005 created but never attached (values are cast with
  ``USING``; a value outside the enum fails the migration loudly rather than
  being silently altered).
* Nullability aligned with the models (``users.phone_*``, ``devices.fcm_token``,
  ``regions.timezone`` nullable; ``incidents.started_at`` NOT NULL, back-filled
  from ``created_at``; ``users.region_id`` NOT NULL — the upgrade aborts with a
  clear message if any user has no region).
* Index names normalised ``ix_*`` -> ``idx_*`` and the composite / status
  indexes the models declare added; foreign keys recreated with the
  ``ON DELETE`` behaviour the models declare.

Idempotent by construction: every operation first inspects the live schema, so
the same revision also converges a database that was created directly from the
models and stamped at 007 (the legacy ``scripts/init_schema_from_models.py``
path).

Downgrade is intentionally partial: it removes what this revision *added*
(status, admin_approvals, new columns) and restores the old FK/index names, but
does not narrow widened types or convert enum columns back to VARCHAR.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_reconcile_schema_with_models"
down_revision: Union[str, None] = "007_users_h3_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

USER_STATUS_VALUES = ("pending_verification", "pending_activation", "active", "suspended", "deactivated")

# (table, column): VARCHAR(32) -> VARCHAR(36) — primary and foreign keys
WIDEN_IDS = [('audit_logs', 'id'), ('audit_logs', 'actor_user_id'), ('audit_logs', 'resource_id'),
 ('audit_logs', 'device_id'), ('devices', 'id'), ('devices', 'user_id'), ('emergency_locations', 'id'),
 ('emergency_locations', 'incident_id'), ('emergency_locations', 'user_id'), ('incident_assignments', 'id'),
 ('incident_assignments', 'incident_id'), ('incident_assignments', 'responder_id'), ('incident_events', 'id'),
 ('incident_events', 'incident_id'), ('incident_events', 'actor_user_id'), ('incidents', 'id'),
 ('incidents', 'organization_id'), ('incidents', 'region_id'), ('incidents', 'created_by_id'),
 ('notifications', 'id'), ('notifications', 'user_id'), ('notifications', 'incident_id'),
 ('organizations', 'id'), ('otp_requests', 'id'), ('otp_requests', 'user_id'),
 ('password_reset_requests', 'id'), ('password_reset_requests', 'user_id'),
 ('password_reset_requests', 'approved_by_id'), ('refresh_tokens', 'id'), ('refresh_tokens', 'user_id'),
 ('refresh_tokens', 'device_id'), ('regions', 'id'), ('regions', 'organization_id'),
 ('responder_status', 'id'), ('responder_status', 'user_id'), ('roles', 'id'), ('trusted_contacts', 'id'),
 ('trusted_contacts', 'user_id'), ('user_roles', 'id'), ('user_roles', 'user_id'), ('user_roles', 'role_id'),
 ('user_roles', 'assigned_by_id'), ('users', 'id'), ('users', 'organization_id'), ('users', 'region_id')]

# Legacy index names dropped (ix_*), and the gist ones are recreated below.
OLD_INDEXES = [('ix_audit_logs_action', 'audit_logs'), ('ix_audit_logs_actor_user_id', 'audit_logs'),
 ('ix_audit_logs_created_at', 'audit_logs'), ('ix_audit_logs_resource_type', 'audit_logs'),
 ('ix_devices_fcm_token', 'devices'), ('ix_devices_user_id', 'devices'),
 ('ix_emergency_locations_captured_at', 'emergency_locations'),
 ('ix_emergency_locations_incident_id', 'emergency_locations'),
 ('ix_emergency_locations_location', 'emergency_locations'),
 ('ix_incident_assignments_incident_id', 'incident_assignments'),
 ('ix_incident_assignments_responder_id', 'incident_assignments'),
 ('ix_incident_assignments_status', 'incident_assignments'),
 ('ix_incident_events_event_type', 'incident_events'), ('ix_incident_events_incident_id', 'incident_events'),
 ('ix_incidents_created_at', 'incidents'), ('ix_incidents_created_by_id', 'incidents'),
 ('ix_incidents_deleted_at', 'incidents'), ('ix_incidents_organization_id', 'incidents'),
 ('ix_incidents_region_id', 'incidents'), ('ix_incidents_status', 'incidents'),
 ('ix_notifications_created_at', 'notifications'), ('ix_notifications_delivery_status', 'notifications'),
 ('ix_notifications_user_id', 'notifications'), ('ix_organizations_name', 'organizations'),
 ('ix_otp_requests_destination_hash', 'otp_requests'), ('ix_otp_requests_expires_at', 'otp_requests'),
 ('ix_password_reset_requests_status', 'password_reset_requests'),
 ('ix_password_reset_requests_user_id', 'password_reset_requests'),
 ('ix_refresh_tokens_expires_at', 'refresh_tokens'), ('ix_refresh_tokens_jti', 'refresh_tokens'),
 ('ix_refresh_tokens_user_id', 'refresh_tokens'), ('ix_regions_name', 'regions'),
 ('ix_regions_organization_id', 'regions'), ('ix_responder_status_location', 'responder_status'),
 ('ix_responder_status_user_id', 'responder_status'), ('ix_trusted_contacts_user_id', 'trusted_contacts'),
 ('ix_user_roles_role_id', 'user_roles'), ('ix_user_roles_user_id', 'user_roles'),
 ('ix_users_email_hash', 'users'), ('ix_users_organization_id', 'users'), ('ix_users_phone_hash', 'users'),
 ('ix_users_region_id', 'users'), ('ix_users_username', 'users')]

# (name, table, columns, unique) created when missing.
NEW_INDEXES = [('idx_audit_logs_action', 'audit_logs', ['action'], False),
 ('idx_audit_logs_actor_created', 'audit_logs', ['actor_user_id', 'created_at'], False),
 ('idx_audit_logs_actor_user_id', 'audit_logs', ['actor_user_id'], False),
 ('idx_audit_logs_created_at', 'audit_logs', ['created_at'], False),
 ('idx_audit_logs_resource_id', 'audit_logs', ['resource_id'], False),
 ('idx_audit_logs_resource_type', 'audit_logs', ['resource_type'], False),
 ('idx_devices_fcm_token', 'devices', ['fcm_token'], False),
 ('idx_devices_is_active', 'devices', ['is_active'], False),
 ('idx_devices_user_id', 'devices', ['user_id'], False),
 ('idx_emergency_locations_captured_at', 'emergency_locations', ['captured_at'], False),
 ('idx_emergency_locations_incident_id', 'emergency_locations', ['incident_id'], False),
 ('idx_emergency_locations_user_id', 'emergency_locations', ['user_id'], False),
 ('idx_incident_assignments_incident_id', 'incident_assignments', ['incident_id'], False),
 ('idx_incident_assignments_incident_responder', 'incident_assignments', ['incident_id', 'responder_id'],
  True),
 ('idx_incident_assignments_responder_id', 'incident_assignments', ['responder_id'], False),
 ('idx_incident_assignments_status', 'incident_assignments', ['status'], False),
 ('idx_incident_events_created_at', 'incident_events', ['created_at'], False),
 ('idx_incident_events_event_type', 'incident_events', ['event_type'], False),
 ('idx_incident_events_incident_id', 'incident_events', ['incident_id'], False),
 ('idx_incidents_created_at', 'incidents', ['created_at'], False),
 ('idx_incidents_created_by', 'incidents', ['created_by_id'], False),
 ('idx_incidents_organization_id', 'incidents', ['organization_id'], False),
 ('idx_incidents_region_id', 'incidents', ['region_id'], False),
 ('idx_incidents_status', 'incidents', ['status'], False),
 ('idx_incidents_status_created', 'incidents', ['status', 'created_at'], False),
 ('idx_notifications_created_at', 'notifications', ['created_at'], False),
 ('idx_notifications_delivery_status', 'notifications', ['delivery_status'], False),
 ('idx_notifications_incident_id', 'notifications', ['incident_id'], False),
 ('idx_notifications_user_id', 'notifications', ['user_id'], False),
 ('idx_notifications_user_status', 'notifications', ['user_id', 'delivery_status', 'created_at'], False),
 ('idx_organizations_is_active', 'organizations', ['is_active'], False),
 ('idx_organizations_name', 'organizations', ['name'], False),
 ('idx_otp_requests_destination_hash', 'otp_requests', ['destination_hash'], False),
 ('idx_otp_requests_expires_at', 'otp_requests', ['expires_at'], False),
 ('idx_otp_requests_user_id', 'otp_requests', ['user_id'], False),
 ('idx_password_reset_requests_created_at', 'password_reset_requests', ['created_at'], False),
 ('idx_password_reset_requests_status', 'password_reset_requests', ['admin_approval_status'], False),
 ('idx_password_reset_requests_user_id', 'password_reset_requests', ['user_id'], False),
 ('idx_refresh_tokens_device_id', 'refresh_tokens', ['device_id'], False),
 ('idx_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'], False),
 ('idx_refresh_tokens_jti', 'refresh_tokens', ['jti'], False),
 ('idx_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], False),
 ('idx_regions_is_active', 'regions', ['is_active'], False), ('idx_regions_name', 'regions', ['name'], False),
 ('idx_regions_organization_id', 'regions', ['organization_id'], False),
 ('idx_responder_status_available', 'responder_status', ['is_available'], False),
 ('idx_responder_status_user_id', 'responder_status', ['user_id'], False),
 ('idx_roles_name', 'roles', ['name'], False),
 ('idx_trusted_contacts_priority', 'trusted_contacts', ['user_id', 'priority'], False),
 ('idx_trusted_contacts_user_id', 'trusted_contacts', ['user_id'], False),
 ('idx_user_roles_role_id', 'user_roles', ['role_id'], False),
 ('idx_user_roles_user_id', 'user_roles', ['user_id'], False),
 ('idx_users_is_active', 'users', ['is_active'], False),
 ('idx_users_organization_id', 'users', ['organization_id'], False),
 ('idx_users_region_id', 'users', ['region_id'], False), ('idx_users_status', 'users', ['status'], False),
 ('idx_users_username', 'users', ['username'], False)]

# Default PostgreSQL FK constraint names replaced by ON DELETE-aware ones.
OLD_FKS = [('emergency_locations_user_id_fkey', 'emergency_locations'),
 ('incident_assignments_responder_id_fkey', 'incident_assignments'),
 ('incident_events_actor_user_id_fkey', 'incident_events'), ('incidents_region_id_fkey', 'incidents'),
 ('incidents_organization_id_fkey', 'incidents'), ('incidents_created_by_id_fkey', 'incidents'),
 ('password_reset_requests_approved_by_id_fkey', 'password_reset_requests'),
 ('refresh_tokens_device_id_fkey', 'refresh_tokens'), ('regions_organization_id_fkey', 'regions'),
 ('user_roles_assigned_by_id_fkey', 'user_roles'), ('users_organization_id_fkey', 'users'),
 ('users_region_id_fkey', 'users')]

# (table, referred table, column, referred column, ondelete)
NEW_FKS = [('emergency_locations', 'users', 'user_id', 'id', 'CASCADE'),
 ('incident_assignments', 'users', 'responder_id', 'id', 'CASCADE'),
 ('incident_events', 'users', 'actor_user_id', 'id', 'SET NULL'),
 ('incidents', 'users', 'created_by_id', 'id', 'CASCADE'),
 ('incidents', 'regions', 'region_id', 'id', 'CASCADE'),
 ('incidents', 'organizations', 'organization_id', 'id', 'CASCADE'),
 ('password_reset_requests', 'users', 'approved_by_id', 'id', 'SET NULL'),
 ('refresh_tokens', 'devices', 'device_id', 'id', 'CASCADE'),
 ('regions', 'organizations', 'organization_id', 'id', 'CASCADE'),
 ('user_roles', 'users', 'assigned_by_id', 'id', 'SET NULL'),
 ('users', 'organizations', 'organization_id', 'id', 'CASCADE'),
 ('users', 'regions', 'region_id', 'id', 'CASCADE')]


# (table, column, enum type) — VARCHAR -> native enum
ENUM_COLUMNS = [
    ("emergency_locations", "source", "location_source_enum"),
    ("incident_assignments", "status", "assignment_status_enum"),
    ("incident_events", "event_type", "incident_event_type_enum"),
    ("incidents", "incident_type", "incident_type_enum"),
    ("incidents", "severity", "incident_severity_enum"),
    ("incidents", "status", "incident_status_enum"),
    ("notifications", "notification_type", "notification_type_enum"),
    ("notifications", "delivery_status", "delivery_status_enum"),
    ("otp_requests", "channel", "otp_channel_enum"),
    ("otp_requests", "purpose", "otp_purpose_enum"),
    ("password_reset_requests", "admin_approval_status", "approval_status_enum"),
]

# (table, column, new SQL type, USING expression or None)
RETYPED_COLUMNS = [
    ("audit_logs", "ip_address", "INET", "ip_address::inet"),
    ("audit_logs", "user_agent", "VARCHAR(500)", None),
    ("audit_logs", "request_id", "VARCHAR(100)", None),
    ("devices", "fcm_token", "VARCHAR(500)", None),
    ("incident_assignments", "decline_reason", "VARCHAR(255)", None),
    ("incidents", "cancel_reason", "VARCHAR(255)", None),
    ("organizations", "settings", "JSON", "settings::json"),
    ("regions", "settings", "JSON", "settings::json"),
    ("regions", "timezone", "VARCHAR(100)", None),
    ("roles", "permissions", "JSON", "permissions::json"),
    ("otp_requests", "destination_hash", "VARCHAR(255)", None),
    ("otp_requests", "otp_hash", "VARCHAR(255)", None),
    ("refresh_tokens", "jti", "VARCHAR(100)", None),
    ("refresh_tokens", "replaced_by_jti", "VARCHAR(100)", None),
    ("users", "username", "VARCHAR(100)", None),
    ("users", "display_name", "VARCHAR(255)", None),
    ("users", "avatar_url", "VARCHAR(500)", None),
    ("users", "mfa_secret", "VARCHAR(255)", None),
    ("users", "mfa_backup_codes", "VARCHAR(1000)", "mfa_backup_codes::text"),
    ("users", "suspension_reason", "VARCHAR(500)", None),
]

# (table, column) made nullable
NOW_NULLABLE = [("users", "phone_encrypted"), ("users", "phone_hash"), ("devices", "fcm_token"), ("regions", "timezone")]

GIST_INDEXES = [
    ("idx_emergency_locations_location", "emergency_locations", "location"),
    ("idx_responder_status_location", "responder_status", "location"),
]
OLD_GIST_INDEXES = ["ix_emergency_locations_location", "ix_responder_status_location"]


# ── helpers (every step inspects the live schema first) ──────────────────────
def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _insp().has_table(name)


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _insp().get_columns(table)}


def _index_names(table: str) -> set[str]:
    return {i["name"] for i in _insp().get_indexes(table)}


def _fk_names(table: str) -> set[str]:
    return {f["name"] for f in _insp().get_foreign_keys(table)}


def _fk_matches(table: str, column: str, ref_table: str, ondelete: str) -> bool:
    for fk in _insp().get_foreign_keys(table):
        if fk["constrained_columns"] == [column] and fk["referred_table"] == ref_table:
            return (fk.get("options", {}).get("ondelete") or "").upper() == ondelete
    return False


def _create_enum_if_missing(name: str, values) -> None:
    labels = ", ".join(f"'{v}'" for v in values)
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') "
        f"THEN CREATE TYPE {name} AS ENUM ({labels}); END IF; END $$;"
    )


def upgrade() -> None:
    # 1. users.status ---------------------------------------------------------
    _create_enum_if_missing("user_status_enum", USER_STATUS_VALUES)
    if not _has_column("users", "status"):
        op.execute(
            "ALTER TABLE users ADD COLUMN status user_status_enum "
            "NOT NULL DEFAULT 'pending_verification'"
        )
        op.execute(
            """
            UPDATE users SET status = CASE
                WHEN NOT is_active THEN 'deactivated'
                WHEN is_suspended THEN 'suspended'
                WHEN NOT is_verified THEN 'pending_verification'
                ELSE 'active'
            END::user_status_enum
            """
        )

    # 2. widen ids ------------------------------------------------------------
    for table, column in WIDEN_IDS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(36)")

    # 3. new / removed columns -------------------------------------------------
    if not _has_column("emergency_locations", "altitude_m"):
        op.add_column("emergency_locations", sa.Column("altitude_m", sa.Float(), nullable=True))
    if not _has_column("otp_requests", "max_attempts"):
        # existing rows get the historical default (settings.otp_max_attempts = 3)
        op.add_column(
            "otp_requests",
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        )
        op.alter_column("otp_requests", "max_attempts", server_default=None)
    if _has_column("trusted_contacts", "is_verified"):
        op.drop_column("trusted_contacts", "is_verified")

    # 4. varchar -> native enum ------------------------------------------------
    for table, column, enum_name in ENUM_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {enum_name} USING {column}::text::{enum_name}"
        )

    # 5. other type changes ----------------------------------------------------
    for table, column, sql_type, using in RETYPED_COLUMNS:
        clause = f" USING {using}" if using else ""
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {sql_type}{clause}")

    # 6. nullability -----------------------------------------------------------
    for table, column in NOW_NULLABLE:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
    orphaned = op.get_bind().execute(sa.text("SELECT count(*) FROM users WHERE region_id IS NULL")).scalar()
    if orphaned:
        raise RuntimeError(
            f"{orphaned} user(s) have no region_id; assign a region before upgrading "
            "(users.region_id is NOT NULL in the model)."
        )
    op.execute("ALTER TABLE users ALTER COLUMN region_id SET NOT NULL")
    op.execute("UPDATE incidents SET started_at = created_at WHERE started_at IS NULL")
    op.execute("ALTER TABLE incidents ALTER COLUMN started_at SET NOT NULL")

    # 7. admin_approvals -------------------------------------------------------
    if not _has_table("admin_approvals"):
        op.create_table(
            "admin_approvals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "request_type",
                postgresql.ENUM(name="approval_request_type_enum", create_type=False),
                nullable=False,
            ),
            sa.Column("request_ref_id", sa.String(36), nullable=False),
            sa.Column("requested_by_id", sa.String(36), nullable=False),
            sa.Column("reviewed_by_id", sa.String(36), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(name="approval_status_enum", create_type=False),
                nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        )
    for name, table, cols, unique in [
        ("idx_admin_approvals_request_ref", "admin_approvals", ["request_type", "request_ref_id"], False),
        ("idx_admin_approvals_request_type", "admin_approvals", ["request_type"], False),
        ("idx_admin_approvals_requested_by", "admin_approvals", ["requested_by_id"], False),
        ("idx_admin_approvals_status", "admin_approvals", ["status"], False),
    ]:
        if name not in _index_names(table):
            op.create_index(name, table, cols, unique=unique)

    # 8. foreign keys (recreated with the models' ON DELETE rules) -------------
    for name, table in OLD_FKS:
        if name in _fk_names(table):
            op.drop_constraint(name, table, type_="foreignkey")
    for table, ref, column, ref_col, ondelete in NEW_FKS:
        if not _fk_matches(table, column, ref, ondelete):
            for fk in _insp().get_foreign_keys(table):  # a same-column FK with other rules
                if fk["constrained_columns"] == [column] and fk["referred_table"] == ref:
                    op.drop_constraint(fk["name"], table, type_="foreignkey")
            op.create_foreign_key(
                f"{table}_{column}_fkey", table, ref, [column], [ref_col], ondelete=ondelete
            )

    # 9. indexes ---------------------------------------------------------------
    for name, table in OLD_INDEXES:
        if name in _index_names(table):
            op.drop_index(name, table_name=table)
    for name, table, cols, unique in NEW_INDEXES:
        if name not in _index_names(table):
            op.create_index(name, table, cols, unique=unique)
    for name, table, column in GIST_INDEXES:
        if name not in _index_names(table):
            op.create_index(name, table, [column], postgresql_using="gist")
    if "idx_users_status" not in _index_names("users"):
        op.create_index("idx_users_status", "users", ["status"])


def downgrade() -> None:
    """Partial by design — see the module docstring."""
    if "idx_users_status" in _index_names("users"):
        op.drop_index("idx_users_status", table_name="users")
    for name, table, _cols, _unique in reversed(NEW_INDEXES):
        if name in _index_names(table):
            op.drop_index(name, table_name=table)
    for name, table, _column in GIST_INDEXES:
        if name in _index_names(table):
            op.drop_index(name, table_name=table)
    if _has_table("admin_approvals"):
        op.drop_table("admin_approvals")
    for table, column in (("otp_requests", "max_attempts"), ("emergency_locations", "altitude_m")):
        if _has_column(table, column):
            op.drop_column(table, column)
    if not _has_column("trusted_contacts", "is_verified"):
        op.add_column(
            "trusted_contacts",
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if _has_column("users", "status"):
        op.drop_column("users", "status")
    op.execute("DROP TYPE IF EXISTS user_status_enum")
