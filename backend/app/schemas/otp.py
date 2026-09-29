"""
OTP (One-Time Password) and verification schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.enums import OTPChannel, OTPPurpose
from app.schemas.common import BaseSchema, TimestampMixin


class OTPRequestCreate(BaseSchema):
    """Request OTP for verification."""

    user_id: str | None = Field(default=None, description="Optional: required for authenticated flows")
    channel: OTPChannel = Field(default=OTPChannel.SMS, description="SMS or EMAIL")
    purpose: OTPPurpose = Field(description="Purpose of OTP (phone_verification, email_verification, password_reset, login_mfa)")
    destination: str = Field(min_length=5, max_length=255, description="Phone number or email address")


class OTPResponse(BaseSchema):
    """Response to OTP request."""

    request_id: str = Field(description="OTP request identifier")
    channel: str = Field(description="Delivery channel (sms or email)")
    expires_in_seconds: int = Field(description="Time until OTP expires")
    message: str = "OTP has been sent"
    otp_code: str | None = Field(
        default=None,
        description="Actual OTP code (development only, null in production)",
    )


class OTPVerifyRequest(BaseSchema):
    """Verify OTP code."""

    request_id: str = Field(description="OTP request identifier")
    code: str = Field(min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("code")
    @classmethod
    def validate_code_numeric(cls, v: str) -> str:
        """Ensure OTP is numeric."""
        if not v.isdigit():
            raise ValueError("OTP must be numeric")
        return v


class OTPVerifyResponse(BaseSchema):
    """Response to successful OTP verification."""

    verified: bool = True
    message: str = "OTP verified successfully"
    channel: str = Field(description="Channel used for verification")


class OTPVerifyStep(BaseSchema):
    """OTP verification step (intermediate)."""

    request_id: str
    purpose: str
    channel: str
    expires_at: datetime
    is_expired: bool
    attempts_remaining: int
    message: str


class OTPResendRequest(BaseSchema):
    """Resend OTP code."""

    request_id: str = Field(description="OTP request identifier")
    channel: OTPChannel | None = Field(
        default=None,
        description="Optional: change channel for resend",
    )


class OTPResendResponse(BaseSchema):
    """Response to OTP resend."""

    request_id: str
    channel: str
    expires_in_seconds: int
    message: str = "OTP resent successfully"
    otp_code: str | None = Field(
        default=None,
        description="OTP code (development only)",
    )


class OTPStatusRequest(BaseSchema):
    """Check OTP verification status."""

    request_id: str = Field(description="OTP request identifier")


class OTPStatusResponse(BaseSchema):
    """Response to OTP status check."""

    request_id: str
    purpose: str
    channel: str
    is_verified: bool
    is_expired: bool
    is_used: bool
    attempts_remaining: int
    expires_at: datetime
    created_at: datetime
    verified_at: datetime | None = None


class OTPBatchRequest(BaseSchema):
    """Request multiple OTP codes (internal/admin use)."""

    user_id: str | None = None
    channels: list[OTPChannel] = Field(default_factory=lambda: [OTPChannel.SMS, OTPChannel.EMAIL])
    purpose: OTPPurpose
    destination_phone: str | None = None
    destination_email: str | None = None


class OTPBatchResponse(BaseSchema):
    """Response with multiple OTP requests."""

    requests: list[dict[str, str]] = Field(description="List of {channel, request_id}")
    message: str = "OTPs sent to all configured channels"


class OTPStatusDetail(BaseSchema, TimestampMixin):
    """Detailed OTP status information."""

    request_id: str
    purpose: str
    channel: str
    is_verified: bool
    is_expired: bool
    is_used: bool
    is_locked: bool  # Too many attempts
    attempts_remaining: int
    max_attempts: int
    expires_at: datetime
    verified_at: datetime | None


class OTPHistoryItem(BaseSchema, TimestampMixin):
    """OTP history entry."""

    request_id: str
    purpose: str
    channel: str
    verified: bool
    expires_at: datetime


class OTPHistoryResponse(BaseSchema):
    """OTP verification history."""

    total: int
    items: list[OTPHistoryItem]
