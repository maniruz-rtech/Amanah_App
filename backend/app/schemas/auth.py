"""
Authentication schemas for login, tokens, MFA, and password reset.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.enums import DevicePlatform, OTPChannel
from app.schemas.common import BaseSchema


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────


class LoginRequest(BaseSchema):
    """Login request schema."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1)
    device_uuid: str = Field(min_length=1, max_length=255)
    platform: DevicePlatform
    push_token: str | None = Field(default=None, max_length=500)
    app_version: str | None = Field(default=None, max_length=50)


class UserProfile(BaseSchema):
    """User profile in login response."""

    id: str
    full_name: str | None = None
    username: str
    roles: list[str] = []
    region_id: str
    organization_id: str
    is_verified: bool


class LoginResponse(BaseSchema):
    """Successful login response."""

    access_token: str
    refresh_token: str
    expires_in: int  # Seconds
    user: UserProfile


class MFAChallengeResponse(BaseSchema):
    """Response when MFA is required."""

    mfa_challenge_id: str
    mfa_required: bool = True
    message: str = "MFA verification required"


# ─────────────────────────────────────────────────────────────────────────────
# Token Refresh
# ─────────────────────────────────────────────────────────────────────────────


class RefreshTokenRequest(BaseSchema):
    """Token refresh request."""

    refresh_token: str


class RefreshTokenResponse(BaseSchema):
    """Token refresh response."""

    access_token: str
    refresh_token: str
    expires_in: int


# ─────────────────────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────────────────────


class LogoutRequest(BaseSchema):
    """Logout request."""

    refresh_token: str


# ─────────────────────────────────────────────────────────────────────────────
# MFA
# ─────────────────────────────────────────────────────────────────────────────


class MFASetupResponse(BaseSchema):
    """MFA setup response with QR code data."""

    secret: str
    qr_code_uri: str
    backup_codes: list[str]


class MFAVerifyRequest(BaseSchema):
    """MFA verification request."""

    mfa_challenge_id: str
    code: str = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def validate_code_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("MFA code must be numeric")
        return v


class MFAVerifyResponse(BaseSchema):
    """MFA verification success response."""

    access_token: str
    refresh_token: str
    expires_in: int
    user: UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Password Reset
# ─────────────────────────────────────────────────────────────────────────────


class PasswordResetRequestCreate(BaseSchema):
    """Request password reset."""

    username: str = Field(min_length=3, max_length=100)
    channel: OTPChannel = OTPChannel.SMS


class PasswordResetRequestResponse(BaseSchema):
    """Password reset request response."""

    request_id: str
    message: str = "OTP sent to registered phone/email"
    expires_in: int  # Minutes


class OTPVerifyRequest(BaseSchema):
    """OTP verification request."""

    request_id: str
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("otp")
    @classmethod
    def validate_otp_numeric(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must be numeric")
        return v


class OTPVerifyResponse(BaseSchema):
    """OTP verification response."""

    verified: bool = True
    message: str = "OTP verified. Awaiting admin approval."


class CompletePasswordResetRequest(BaseSchema):
    """Complete password reset with new password."""

    reset_request_id: str
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
            raise ValueError("Password must contain special character")
        return v


class CompletePasswordResetResponse(BaseSchema):
    """Password reset complete response."""

    success: bool = True
    message: str = "Password has been reset. Please login with new password."


# ─────────────────────────────────────────────────────────────────────────────
# Token Response (used internally by services)
# ─────────────────────────────────────────────────────────────────────────────


class TokenResponse(BaseSchema):
    """Generic token response used by auth service."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds


# ─────────────────────────────────────────────────────────────────────────────
# OTP Request/Response (aliased from existing)
# ─────────────────────────────────────────────────────────────────────────────

# Alias for backward compatibility
OTPRequest = OTPVerifyRequest
OTPResponse = OTPVerifyResponse

# Alias PasswordResetRequest and PasswordResetCompleteRequest
PasswordResetRequest = PasswordResetRequestCreate
PasswordResetCompleteRequest = CompletePasswordResetRequest
TokenRefreshRequest = RefreshTokenRequest
