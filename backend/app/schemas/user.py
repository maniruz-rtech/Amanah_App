"""
User and profile schemas.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import BaseSchema, TimestampMixin


# ─────────────────────────────────────────────────────────────────────────────
# User Profile
# ─────────────────────────────────────────────────────────────────────────────


class UserResponse(BaseSchema, TimestampMixin):
    """User profile response."""

    id: str
    full_name: str | None = None
    username: str
    phone_masked: str | None = None
    email_masked: str | None = None
    roles: list[str] = []
    region_id: str
    organization_id: str
    is_verified: bool
    is_active: bool
    is_suspended: bool = False


class UserProfileUpdate(BaseSchema):
    """Update user profile request."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)


# ─────────────────────────────────────────────────────────────────────────────
# Nearby (proximity-aware responder lookup)
# ─────────────────────────────────────────────────────────────────────────────


class PresencePingRequest(BaseSchema):
    """Periodic presence ping from the Android client."""

    h3_cell_district: str = Field(min_length=1, max_length=16)
    h3_cell_block:    str | None = Field(default=None, max_length=16)


class NearbyUserResponse(BaseSchema):
    """One row in the response of GET /api/v1/users/nearby."""

    user_id: str
    display_name: str
    h3_cell_district: str
    last_seen_at: datetime
    is_responder: bool = False


class NearbyUsersResponse(BaseSchema):
    """Envelope for the nearby-users list."""

    items: list[NearbyUserResponse]
    total: int
    queried_h3_cells: list[str]



# ─────────────────────────────────────────────────────────────────────────────
# Trusted Contacts
# ─────────────────────────────────────────────────────────────────────────────


class TrustedContactCreate(BaseSchema):
    """Create trusted contact request."""

    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=10, max_length=20)
    relationship: str | None = Field(default=None, max_length=50)
    priority: int = Field(default=1, ge=1, le=5)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Basic phone validation - could be improved with phonenumbers library
        cleaned = "".join(c for c in v if c.isdigit() or c == "+")
        if len(cleaned) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return cleaned


class TrustedContactUpdate(BaseSchema):
    """Update trusted contact request."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=10, max_length=20)
    relationship: str | None = Field(default=None, max_length=50)
    priority: int | None = Field(default=None, ge=1, le=5)


class TrustedContactResponse(BaseSchema, TimestampMixin):
    """Trusted contact response."""

    id: str
    name: str
    phone_masked: str
    relationship: str | None
    priority: int


# ─────────────────────────────────────────────────────────────────────────────
# Device
# ─────────────────────────────────────────────────────────────────────────────


class DeviceRegisterRequest(BaseSchema):
    """Device registration request."""

    device_uuid: str = Field(min_length=1, max_length=255)
    platform: str  # DevicePlatform enum
    push_token: str | None = Field(default=None, max_length=500)
    app_version: str | None = Field(default=None, max_length=50)


class DeviceResponse(BaseSchema, TimestampMixin):
    """Device response."""

    id: str
    device_uuid: str
    platform: str
    app_version: str | None
    is_primary: bool
    is_active: bool
    last_seen_at: datetime | None


class DeviceRevokeResponse(BaseSchema):
    """Device revocation response."""

    success: bool = True
    message: str = "Device revoked successfully"


# ─────────────────────────────────────────────────────────────────────────────
# Admin User Management
# ─────────────────────────────────────────────────────────────────────────────


class AdminUserCreate(BaseSchema):
    """Admin create user request."""

    full_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=3, max_length=100)
    phone: str = Field(min_length=10, max_length=20)
    email: EmailStr | None = None
    organization_id: str
    region_id: str
    roles: list[str] = Field(default=["member"])

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v.replace("_", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, and underscores")
        return v.lower()


class AdminUserCreateResponse(BaseSchema, TimestampMixin):
    """Admin user creation response."""

    id: str
    full_name: str | None = None
    username: str
    phone_masked: str | None = None
    email_masked: str | None = None
    organization_id: str
    region_id: str
    roles: list[str] = []
    is_active: bool = True
    is_verified: bool = False
    temporary_password: str  # Only shown once!


class AdminUserUpdate(BaseSchema):
    """Admin update user request."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    region_id: str | None = None
    is_active: bool | None = None


class UserSuspendRequest(BaseSchema):
    """User suspension request."""

    reason: str = Field(min_length=1, max_length=500)


class UserActivateRequest(BaseSchema):
    """User activation request."""

    note: str | None = Field(default=None, max_length=500)


class RoleAssignRequest(BaseSchema):
    """Role assignment request."""

    role: str = Field(min_length=1, max_length=50)


class AdminUserListResponse(BaseSchema, TimestampMixin):
    """Admin user list item response."""

    id: str
    full_name: str | None = None
    username: str
    roles: list[str] = []
    region_id: str
    region_name: str | None = None
    organization_id: str
    is_verified: bool = False
    is_active: bool = True
    is_suspended: bool = False
    last_login_at: datetime | None = None


# Alias for backward compatibility
UserProfileResponse = UserResponse
