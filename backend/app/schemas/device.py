"""
Device management schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.enums import DevicePlatform
from app.schemas.common import BaseSchema, TimestampMixin


class DeviceRegisterRequest(BaseSchema):
    """Device registration request."""

    device_uuid: str = Field(min_length=1, max_length=255)
    platform: DevicePlatform
    push_token: str | None = Field(default=None, max_length=500)
    app_version: str | None = Field(default=None, max_length=50)


class DevicePushTokenUpdate(BaseSchema):
    """Update device push token request."""

    push_token: str = Field(min_length=1, max_length=500)


class DeviceDetailResponse(BaseSchema, TimestampMixin):
    """Device detail response with all available information."""

    id: str
    device_uuid: str
    platform: str
    app_version: str | None
    is_primary: bool
    is_active: bool
    last_seen_at: datetime | None


class DeviceResponse(BaseSchema, TimestampMixin):
    """Device response (minimal)."""

    id: str
    device_uuid: str
    platform: str
    app_version: str | None
    is_primary: bool
    is_active: bool
    last_seen_at: datetime | None


class DeviceListResponse(BaseSchema):
    """Device list response."""

    devices: list[DeviceResponse]
    total: int


class DeviceRevokeResponse(BaseSchema):
    """Device revocation response."""

    success: bool = True
    message: str = "Device revoked successfully"
