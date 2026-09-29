"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')

    # Create organizations table
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('settings', postgresql.JSONB, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_organizations_name', 'organizations', ['name'])

    # Create regions table
    op.create_table(
        'regions',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('organization_id', sa.String(32), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('timezone', sa.String(50), default='UTC', nullable=False),
        sa.Column('settings', postgresql.JSONB, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_regions_organization_id', 'regions', ['organization_id'])
    op.create_index('ix_regions_name', 'regions', ['name'])

    # Create roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('permissions', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('organization_id', sa.String(32), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('region_id', sa.String(32), sa.ForeignKey('regions.id'), nullable=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('phone_encrypted', sa.LargeBinary, nullable=False),
        sa.Column('phone_hash', sa.String(64), nullable=False),
        sa.Column('email_encrypted', sa.LargeBinary, nullable=True),
        sa.Column('email_hash', sa.String(64), nullable=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name_encrypted', sa.LargeBinary, nullable=True),
        sa.Column('display_name', sa.String(100), nullable=True),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean, default=False, nullable=False),
        sa.Column('mfa_secret', sa.String(32), nullable=True),
        sa.Column('mfa_backup_codes', postgresql.JSONB, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('is_verified', sa.Boolean, default=False, nullable=False),
        sa.Column('is_suspended', sa.Boolean, default=False, nullable=False),
        sa.Column('suspension_reason', sa.Text, nullable=True),
        sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer, default=0, nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_users_organization_id', 'users', ['organization_id'])
    op.create_index('ix_users_region_id', 'users', ['region_id'])
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_phone_hash', 'users', ['phone_hash'])
    op.create_index('ix_users_email_hash', 'users', ['email_hash'])

    # Create user_roles table
    op.create_table(
        'user_roles',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role_id', sa.String(32), sa.ForeignKey('roles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('assigned_by_id', sa.String(32), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'role_id', name='uq_user_role'),
    )
    op.create_index('ix_user_roles_user_id', 'user_roles', ['user_id'])
    op.create_index('ix_user_roles_role_id', 'user_roles', ['role_id'])

    # Create devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fcm_token', sa.String(512), nullable=False),
        sa.Column('device_name', sa.String(255), nullable=True),
        sa.Column('os_name', sa.String(50), nullable=True),
        sa.Column('os_version', sa.String(50), nullable=True),
        sa.Column('app_version', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_devices_user_id', 'devices', ['user_id'])
    op.create_index('ix_devices_fcm_token', 'devices', ['fcm_token'])

    # Create trusted_contacts table
    op.create_table(
        'trusted_contacts',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone_encrypted', sa.LargeBinary, nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=True),
        sa.Column('priority', sa.Integer, default=1, nullable=False),
        sa.Column('is_verified', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_trusted_contacts_user_id', 'trusted_contacts', ['user_id'])

    # Create responder_status table
    op.create_table(
        'responder_status',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('is_available', sa.Boolean, default=False, nullable=False),
        sa.Column('last_lat', sa.Float, nullable=True),
        sa.Column('last_lng', sa.Float, nullable=True),
        sa.Column('location', Geography(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('last_location_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('battery_level', sa.Integer, nullable=True),
        sa.Column('active_incident_count', sa.Integer, default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_responder_status_user_id', 'responder_status', ['user_id'])
    op.create_index('ix_responder_status_location', 'responder_status', ['location'], postgresql_using='gist')

    # Create incidents table
    op.create_table(
        'incidents',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('organization_id', sa.String(32), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('region_id', sa.String(32), sa.ForeignKey('regions.id'), nullable=False),
        sa.Column('created_by_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('incident_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('silent_mode', sa.Boolean, default=False, nullable=False),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_note', sa.Text, nullable=True),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_incidents_organization_id', 'incidents', ['organization_id'])
    op.create_index('ix_incidents_region_id', 'incidents', ['region_id'])
    op.create_index('ix_incidents_created_by_id', 'incidents', ['created_by_id'])
    op.create_index('ix_incidents_status', 'incidents', ['status'])
    op.create_index('ix_incidents_created_at', 'incidents', ['created_at'])

    # Create emergency_locations table
    op.create_table(
        'emergency_locations',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('incident_id', sa.String(32), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('lat', sa.Float, nullable=False),
        sa.Column('lng', sa.Float, nullable=False),
        sa.Column('accuracy_m', sa.Integer, nullable=True),
        sa.Column('location', Geography(geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('battery_level', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_emergency_locations_incident_id', 'emergency_locations', ['incident_id'])
    op.create_index('ix_emergency_locations_location', 'emergency_locations', ['location'], postgresql_using='gist')
    op.create_index('ix_emergency_locations_captured_at', 'emergency_locations', ['captured_at'])

    # Create incident_assignments table
    op.create_table(
        'incident_assignments',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('incident_id', sa.String(32), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('responder_id', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decline_reason', sa.Text, nullable=True),
        sa.Column('eta_minutes', sa.Integer, nullable=True),
        sa.Column('distance_m', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_incident_assignments_incident_id', 'incident_assignments', ['incident_id'])
    op.create_index('ix_incident_assignments_responder_id', 'incident_assignments', ['responder_id'])
    op.create_index('ix_incident_assignments_status', 'incident_assignments', ['status'])

    # Create incident_events table
    op.create_table(
        'incident_events',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('incident_id', sa.String(32), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_payload', postgresql.JSONB, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_incident_events_incident_id', 'incident_events', ['incident_id'])
    op.create_index('ix_incident_events_event_type', 'incident_events', ['event_type'])

    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('incident_id', sa.String(32), sa.ForeignKey('incidents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('delivery_status', sa.String(20), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fcm_message_id', sa.String(255), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('retry_count', sa.Integer, default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_delivery_status', 'notifications', ['delivery_status'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])

    # Create otp_requests table
    op.create_table(
        'otp_requests',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('purpose', sa.String(30), nullable=False),
        sa.Column('destination_hash', sa.String(64), nullable=False),
        sa.Column('otp_hash', sa.String(64), nullable=False),
        sa.Column('attempt_count', sa.Integer, default=0, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_otp_requests_destination_hash', 'otp_requests', ['destination_hash'])
    op.create_index('ix_otp_requests_expires_at', 'otp_requests', ['expires_at'])

    # Create password_reset_requests table
    op.create_table(
        'password_reset_requests',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('phone_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('admin_approval_status', sa.String(20), nullable=False),
        sa.Column('approved_by_id', sa.String(32), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_password_reset_requests_user_id', 'password_reset_requests', ['user_id'])
    op.create_index('ix_password_reset_requests_status', 'password_reset_requests', ['admin_approval_status'])

    # Create refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_id', sa.String(32), sa.ForeignKey('devices.id', ondelete='SET NULL'), nullable=True),
        sa.Column('jti', sa.String(64), unique=True, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean, default=False, nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by_jti', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_index('ix_refresh_tokens_jti', 'refresh_tokens', ['jti'], unique=True)
    op.create_index('ix_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'])

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('actor_user_id', sa.String(32), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(32), nullable=True),
        sa.Column('device_id', sa.String(32), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('request_id', sa.String(64), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('success', sa.Boolean, default=True, nullable=False),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_audit_logs_actor_user_id', 'audit_logs', ['actor_user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # Insert default roles
    op.execute("""
        INSERT INTO roles (id, name, description, permissions) VALUES
        ('role_member', 'member', 'Basic community member', '["trigger_sos", "update_profile", "manage_contacts"]'),
        ('role_responder', 'responder', 'Verified community responder', '["trigger_sos", "update_profile", "manage_contacts", "respond_to_incidents", "update_availability"]'),
        ('role_regional_admin', 'regional_admin', 'Regional administrator', '["trigger_sos", "update_profile", "manage_contacts", "respond_to_incidents", "update_availability", "view_incidents", "manage_users", "approve_password_resets", "view_audit_logs"]'),
        ('role_super_admin', 'super_admin', 'Super administrator', '["trigger_sos", "update_profile", "manage_contacts", "respond_to_incidents", "update_availability", "view_incidents", "manage_incidents", "manage_users", "manage_responders", "approve_password_resets", "view_audit_logs", "manage_all_regions", "manage_system"]')
    """)


def downgrade() -> None:
    # Drop all tables in reverse order
    op.drop_table('audit_logs')
    op.drop_table('refresh_tokens')
    op.drop_table('password_reset_requests')
    op.drop_table('otp_requests')
    op.drop_table('notifications')
    op.drop_table('incident_events')
    op.drop_table('incident_assignments')
    op.drop_table('emergency_locations')
    op.drop_table('incidents')
    op.drop_table('responder_status')
    op.drop_table('trusted_contacts')
    op.drop_table('devices')
    op.drop_table('user_roles')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('regions')
    op.drop_table('organizations')
