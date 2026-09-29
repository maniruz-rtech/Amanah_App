"""
Custom exception classes and error handling.

Provides standardized error responses per README Section 17.
"""

from typing import Any

from fastapi import HTTPException, status


class AmanahException(HTTPException):
    """Base exception for Amanah application errors."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, **self.details},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Authentication Errors
# ─────────────────────────────────────────────────────────────────────────────


class InvalidCredentialsError(AmanahException):
    """Invalid username or password."""

    def __init__(self, message: str = "Invalid username or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID_CREDENTIALS",
            message=message,
        )


class AccountSuspendedError(AmanahException):
    """Account has been suspended."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_ACCOUNT_SUSPENDED",
            message="Account has been suspended",
        )


class AccountNotVerifiedError(AmanahException):
    """Account has not been verified."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_ACCOUNT_NOT_VERIFIED",
            message="Account has not been verified",
        )


class AccountLockedError(AmanahException):
    """Account is temporarily locked due to failed login attempts."""

    def __init__(self, lockout_minutes: int):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="AUTH_ACCOUNT_LOCKED",
            message=f"Account is locked. Try again in {lockout_minutes} minutes",
            details={"lockout_minutes": lockout_minutes},
        )


class MFARequiredError(AmanahException):
    """MFA verification is required."""

    def __init__(self, mfa_session_token: str | None = None, mfa_challenge_id: str | None = None):
        # Support both parameter names for backwards compatibility
        challenge_id = mfa_challenge_id or mfa_session_token or "unknown"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_MFA_REQUIRED",
            message="MFA verification required",
            details={"mfa_challenge_id": challenge_id},
        )
        self.mfa_session_token = mfa_session_token


class InvalidTokenError(AmanahException):
    """Invalid or expired token."""

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID_TOKEN",
            message=message,
        )


class DeviceNotRegisteredError(AmanahException):
    """Device is not registered for this user."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="DEVICE_NOT_REGISTERED",
            message="Device is not registered",
        )


class UserNotFoundError(AmanahException):
    """User not found."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found",
        )


class DeviceNotFoundError(AmanahException):
    """Device not found."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DEVICE_NOT_FOUND",
            message="Device not found",
        )


class TrustedContactLimitError(AmanahException):
    """Maximum trusted contacts limit reached."""

    def __init__(self, limit: int = 5):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="TRUSTED_CONTACT_LIMIT_EXCEEDED",
            message=f"Maximum trusted contacts limit ({limit}) reached",
            details={"limit": limit},
        )


class DuplicateDeviceError(AmanahException):
    """Device already registered."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="DEVICE_ALREADY_EXISTS",
            message="Device already registered",
        )


# ─────────────────────────────────────────────────────────────────────────────
# OTP Errors
# ─────────────────────────────────────────────────────────────────────────────


class OTPInvalidError(AmanahException):
    """OTP code is invalid."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="OTP_INVALID",
            message="Invalid OTP code",
        )


class OTPExpiredError(AmanahException):
    """OTP code has expired."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="OTP_EXPIRED",
            message="OTP code has expired",
        )


class InvalidOTPError(AmanahException):
    """OTP code is invalid."""

    def __init__(self, message: str = "Invalid OTP code"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="OTP_INVALID",
            message=message,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Authorization Errors
# ─────────────────────────────────────────────────────────────────────────────


class ForbiddenError(AmanahException):
    """Access denied."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message=message,
        )


class RoleRequiredError(AmanahException):
    """Required role not present."""

    def __init__(self, required_role: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_ROLE_REQUIRED",
            message=f"Required role: {required_role}",
        )


class RegionScopeError(AmanahException):
    """Access to region denied."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_REGION_SCOPE",
            message="Access to this region is denied",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Incident Errors
# ─────────────────────────────────────────────────────────────────────────────


class IncidentNotFoundError(AmanahException):
    """Incident not found or not accessible."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INCIDENT_NOT_FOUND",
            message="Incident not found",
        )


class IncidentNotActiveError(AmanahException):
    """Incident is not in an active state."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="INCIDENT_NOT_ACTIVE",
            message="Incident is not active",
        )


class IncidentAlreadyResolvedError(AmanahException):
    """Incident has already been resolved."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="INCIDENT_ALREADY_RESOLVED",
            message="Incident has already been resolved",
        )


class InvalidStatusTransitionError(AmanahException):
    """Invalid incident status transition."""

    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INCIDENT_INVALID_TRANSITION",
            message=f"Cannot transition from {current_status} to {target_status}",
        )


class InvalidVerificationPinError(AmanahException):
    """Invalid verification PIN for cancellation."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INCIDENT_INVALID_PIN",
            message="Invalid verification PIN",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiting Errors
# ─────────────────────────────────────────────────────────────────────────────


class RateLimitExceededError(AmanahException):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int | None = None):
        details = {"retry_after": retry_after} if retry_after else {}
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMIT_EXCEEDED",
            message="Rate limit exceeded. Please try again later.",
            details=details,
        )


class RateLimitError(RateLimitExceededError):
    """Alias for RateLimitExceededError for backwards compatibility."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__()
        self.message = message


# ─────────────────────────────────────────────────────────────────────────────
# Resource Errors
# ─────────────────────────────────────────────────────────────────────────────


class ResourceNotFoundError(AmanahException):
    """Generic resource not found."""

    def __init__(self, resource: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} not found",
        )


class ResourceAlreadyExistsError(AmanahException):
    """Resource already exists."""

    def __init__(self, resource: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="RESOURCE_ALREADY_EXISTS",
            message=f"{resource} already exists",
        )


class ValidationError(AmanahException):
    """Validation error."""

    def __init__(self, message: str, field: str | None = None):
        details = {"field": field} if field else {}
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message=message,
            details=details,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Permission Errors
# ─────────────────────────────────────────────────────────────────────────────


class PermissionDeniedError(AmanahException):
    """Permission denied for the requested action."""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="PERMISSION_DENIED",
            message=message,
        )


# ─────────────────────────────────────────────────────────────────────────────
# State Transition Errors
# ─────────────────────────────────────────────────────────────────────────────


class InvalidStateTransitionError(AmanahException):
    """Invalid state transition."""

    def __init__(self, message: str = "Invalid state transition"):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_STATE_TRANSITION",
            message=message,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Responder Errors
# ─────────────────────────────────────────────────────────────────────────────


class ResponderNotFoundError(AmanahException):
    """Responder not found or not available."""

    def __init__(self, message: str = "Responder not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RESPONDER_NOT_FOUND",
            message=message,
        )
