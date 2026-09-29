"""Create Postgres enum types referenced by ORM models with create_type=False.

The ORM models reference ``ENUM(..., name="<x>_enum", create_type=False)``
which assumes the type already exists. The initial migration created
``incident_severity_enum`` and ``incident_status_enum`` and a few others
but left several missing. This migration creates the ones the SOS path
needs first, then everything else for completeness:

  - incident_type_enum
  - incident_severity_enum
  - incident_status_enum
  - assignment_status_enum
  - location_source_enum
  - incident_event_type_enum
  - notification_type_enum
  - delivery_status_enum
  - otp_channel_enum
  - otp_purpose_enum
  - approval_status_enum
  - approval_request_type_enum

Every CREATE TYPE is guarded by ``IF NOT EXISTS`` (via a DO block) so re-runs
on a partially-fixed DB are safe.

Revision ID: 005_create_missing_pg_enums
Revises: 004_add_incidents_deleted_at
Create Date: 2026-05-22
"""
from alembic import op


revision = "005_create_missing_pg_enums"
down_revision = "004_add_incidents_deleted_at"
branch_labels = None
depends_on = None


# (name, [values])
_ENUMS = [
    ("incident_type_enum",         ["sos", "medical", "safety", "other"]),
    ("incident_severity_enum",     ["low", "medium", "high", "critical"]),
    ("incident_status_enum",       ["draft", "active", "broadcasting", "accepted",
                                     "en_route", "arrived", "resolved", "canceled", "expired"]),
    ("assignment_status_enum",     ["pending", "accepted", "declined", "en_route",
                                     "arrived", "completed", "canceled"]),
    ("location_source_enum",       ["gps", "network", "manual", "last_known"]),
    ("incident_event_type_enum",   ["created", "status_updated", "location_updated",
                                     "responder_assigned", "responder_accepted",
                                     "responder_declined", "responder_en_route",
                                     "responder_arrived", "responder_completed",
                                     "escalated", "canceled", "resolved", "note_added"]),
    ("notification_type_enum",     ["responder_assignment", "incident_assigned",
                                     "trusted_contact_alert", "incident_update",
                                     "incident_resolution", "responder_accepted",
                                     "responder_arrived", "admin_alert",
                                     "password_reset", "account_activation", "system"]),
    ("delivery_status_enum",       ["pending", "sent", "delivered", "failed", "read"]),
    ("otp_channel_enum",           ["sms", "email"]),
    ("otp_purpose_enum",           ["phone_verification", "email_verification",
                                     "password_reset", "login_mfa"]),
    ("approval_status_enum",       ["pending", "approved", "rejected", "expired"]),
    ("approval_request_type_enum", ["user_activation", "password_reset", "role_change"]),
]


def upgrade() -> None:
    for name, values in _ENUMS:
        values_sql = ", ".join(f"'{v}'" for v in values)
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
                    CREATE TYPE {name} AS ENUM ({values_sql});
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for name, _ in reversed(_ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name};")
