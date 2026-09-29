"""
Password reset and recovery schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.enums import ApprovalStatus, OTPChannel
from app.schemas.common import BaseSchema, TimestampMixin


class PasswordResetRequestCreate(BaseSchema):
    """Request password reset (initiate flow)."""

    username: str = Field(min_length=3, max_length=100)
    channel: OTPChannel = OTPChannel.SMS


class PasswordResetRequestResponse(BaseSchema):
    """Response to password reset request."""

    request_id: str
    message: str = "Password reset request created"
    expires_in_minutes: int = 1440  # 24 hours


class PasswordResetStatusResponse(BaseSchema, TimestampMixin):
    """Password reset request status."""

    request_id: str
    phone_verified: bool
    email_verified: bool
    admin_approval_status: str  # ApprovalStatus enum value
    can_complete: bool
    expires_at: datetime
    is_expired: bool


class OTPVerificationRequest(BaseSchema):
    """Verify OTP for password reset."""

    reset_request_id: str
    otp: str = Field(min_length=6, max_length=6)
    channel: OTPChannel = OTPChannel.SMS

    @field_validator("otp")
    @classmethod
    def validate_otp_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must be numeric")
        return v


class OTPVerificationResponse(BaseSchema):
    """Response to OTP verification."""

    verified: bool = True
    channel: str
    message: str = "OTP verified successfully"
    next_step: str = "awaiting_admin_approval"


class CompletePasswordResetRequest(BaseSchema):
    """Complete password reset with new password."""

    reset_request_id: str
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements."""
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain at least one special character")
        return v


class CompletePasswordResetResponse(BaseSchema):
    """Response to password reset completion."""

    success: bool = True
    message: str = "Password has been successfully reset. Please login with your new password."


class PasswordResetApprovalRequest(BaseSchema):
    """Admin approval for password reset."""

    reset_request_id: str
    approve: bool = True
    reason: str | None = Field(default=None, max_length=500)


class PasswordResetApprovalResponse(BaseSchema):
    """Response to password reset approval."""

    reset_request_id: str
    status: str  # ApprovalStatus enum value
    message: str


class PasswordResetHistoryItem(BaseSchema, TimestampMixin):
    """Password reset history item."""

    request_id: str
    requested_at: datetime
    approval_status: str
    completed: bool
    expires_at: datetime


class PasswordResetHistoryResponse(BaseSchema):
    """User's password reset history."""

    total: int
    items: list[PasswordResetHistoryItem]


class ResendOTPRequest(BaseSchema):
    """Resend OTP for password reset."""

    reset_request_id: str
    channel: OTPChannel = OTPChannel.SMS


class ResendOTPResponse(BaseSchema):
    """Response to OTP resend request."""

    success: bool = True
    channel: str
    expires_in_minutes: int = 10
    message: str = "OTP has been resent"
