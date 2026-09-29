"""
Admin operation schemas.
"""

from datetime import datetime

from pydantic import Field

from app.db.enums import ApprovalStatus
from app.schemas.common import BaseSchema, TimestampMixin


# ─────────────────────────────────────────────────────────────────────────────
# Password Reset Approvals
# ─────────────────────────────────────────────────────────────────────────────


class PasswordResetApprovalItem(BaseSchema, TimestampMixin):
    """Password reset request for admin review."""

    id: str
    user_id: str
    username: str
    full_name: str
    requested_at: datetime
    phone_verified_at: datetime | None
    email_verified_at: datetime | None
    admin_approval_status: ApprovalStatus
    expires_at: datetime


class ApprovePasswordResetRequest(BaseSchema):
    """Approve password reset."""

    note: str | None = Field(default=None, max_length=500)


class RejectPasswordResetRequest(BaseSchema):
    """Reject password reset."""

    note: str = Field(min_length=1, max_length=500)


class PasswordResetApprovalResponse(BaseSchema):
    """Password reset approval response."""

    success: bool = True
    request_id: str
    status: ApprovalStatus
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Audit Logs
# ─────────────────────────────────────────────────────────────────────────────


class AuditLogItem(BaseSchema):
    """Audit log item."""

    id: str
    actor_user_id: str | None
    actor_username: str | None
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    description: str | None
    success: bool
    created_at: datetime
    metadata: dict | None = None


class AuditLogFilter(BaseSchema):
    """Audit log filter parameters."""

    actor_user_id: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Region and Organization
# ─────────────────────────────────────────────────────────────────────────────


class RegionResponse(BaseSchema, TimestampMixin):
    """Region response."""

    id: str
    name: str
    code: str
    organization_id: str
    parent_region_id: str | None
    status: str


class OrganizationResponse(BaseSchema, TimestampMixin):
    """Organization response."""

    id: str
    name: str
    code: str
    status: str


# ─────────────────────────────────────────────────────────────────────────────
# User Management
# ─────────────────────────────────────────────────────────────────────────────


class UserAdminResponse(BaseSchema, TimestampMixin):
    """Admin view of user details."""

    id: str
    full_name: str
    username: str
    phone_masked: str | None = None
    email_masked: str | None = None
    organization_id: str | None
    region_id: str | None
    roles: list[str] = []
    is_active: bool
    is_verified: bool
    is_suspended: bool
    status: str
    created_by_id: str | None = None

    class Config:
        from_attributes = True


class UserCreateRequest(BaseSchema):
    """Request to create a new user."""

    full_name: str = Field(min_length=2, max_length=100)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    region_id: str
    roles: list[str] = Field(default_factory=lambda: ["member"])


class UserSuspendRequest(BaseSchema):
    """Request to suspend a user."""

    reason: str = Field(min_length=5, max_length=500)


# ─────────────────────────────────────────────────────────────────────────────
# Incident Administration
# ─────────────────────────────────────────────────────────────────────────────


class IncidentAdminResponse(BaseSchema, TimestampMixin):
    """Admin view of incident details."""

    id: str
    organization_id: str
    region_id: str
    created_by_id: str
    created_by_username: str | None = None
    incident_type: str
    severity: str
    status: str
    silent_mode: bool = False
    note: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    canceled_at: datetime | None = None
    cancel_reason: str | None = None
    responder_count: int = 0

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Password Reset Administration
# ─────────────────────────────────────────────────────────────────────────────


class PasswordResetRequestResponse(BaseSchema):
    """Password reset request for admin review."""

    id: str
    user_id: str
    username: str | None = None
    full_name: str | None = None
    requested_at: datetime
    phone_verified_at: datetime | None = None
    email_verified_at: datetime | None = None
    admin_approval_status: str
    approved_by_id: str | None = None
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None

    class Config:
        from_attributes = True


class PasswordResetApproval(BaseSchema):
    """Approve or reject password reset."""

    approved: bool
    note: str | None = Field(default=None, max_length=500)
    rejection_reason: str | None = Field(default=None, max_length=500)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log Administration
# ─────────────────────────────────────────────────────────────────────────────


class AuditLogResponse(BaseSchema):
    """Audit log entry response."""

    id: str
    actor_user_id: str | None = None
    actor_username: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    description: str | None = None
    success: bool = True
    error_message: str | None = None
    metadata: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True
