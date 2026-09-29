"""
OTP verification API endpoints.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    AuthenticatedUser,
    OptionalUser,
    ClientIP,
    DBSession,
    UserAgent,
)
from app.core.exceptions import (
    InvalidOTPError,
    OTPExpiredError,
    RateLimitError,
    UserNotFoundError,
)
from app.schemas.otp import (
    OTPRequestCreate,
    OTPResendRequest,
    OTPResendResponse,
    OTPResponse,
    OTPStatusRequest,
    OTPStatusResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
)
from app.services.otp import OTPService

logger = structlog.get_logger()

router = APIRouter(prefix="/otp", tags=["OTP Verification"])


# ─────────────────────────────────────────────────────────────────────────────
# Request OTP
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/request", response_model=OTPResponse, status_code=status.HTTP_201_CREATED)
async def request_otp(
    request: OTPRequestCreate,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Request OTP for verification.

    Supports multiple purposes:
    - phone_verification: Verify user's phone number
    - email_verification: Verify user's email address
    - password_reset: Initiate password reset
    - login_mfa: Second-factor authentication during login

    Channels:
    - sms: Send via SMS to phone number
    - email: Send via email

    In production, OTP is sent via configured delivery system.
    In development mode, OTP is returned in response for testing.
    """
    service = OTPService(db)

    try:
        response, otp_code = await service.request_otp(
            request=request,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Trigger delivery (delegated to external system)
        # In production, this queues the OTP for delivery via SMS/email
        await service.send_otp(response.request_id, otp_code)

        return response

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Verify OTP
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/verify", response_model=OTPVerifyResponse)
async def verify_otp(
    request: OTPVerifyRequest,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
    current_user: OptionalUser,
):
    """Verify OTP code.

    Enforces:
    - Expiration (TTL): OTP must be verified within configured minutes
    - One-time use: OTP can only be verified once
    - Attempt limits: Maximum failed attempts before lockout
    - Rate limiting: Too many attempts returns 429 Too Many Requests

    If authenticated user is provided, verifies OTP belongs to user.
    If no authenticated user, OTP is verified for any user (password reset, signup).
    """
    service = OTPService(db)

    try:
        response = await service.verify_otp(
            request=request,
            user_id=current_user.user_id if current_user else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return response

    except OTPExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one.",
        )
    except InvalidOTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP code. {str(e)}",
        )
    except RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP verification attempts exceeded. Request a new OTP.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# OTP Status
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/status", response_model=OTPStatusResponse)
async def check_otp_status(
    request: OTPStatusRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    """Check OTP request status without verification.

    Provides:
    - Verification status (verified or pending)
    - Expiration status and time
    - Remaining attempts
    - Purpose and channel

    If authenticated user provided, only returns status for own OTPs.
    """
    service = OTPService(db)

    try:
        status = await service.get_otp_status(
            request_id=request.request_id,
            user_id=current_user.user_id if current_user else None,
        )
        return status

    except OTPExpiredError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OTP request not found or has expired",
        )
    except InvalidOTPError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this OTP request",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Resend OTP
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/resend", response_model=OTPResendResponse)
async def resend_otp(
    request: OTPResendRequest,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
    current_user: OptionalUser,
):
    """Resend OTP code.

    Allows:
    - Resending same OTP to same channel (code regenerated, attempts reset)
    - Switching to different channel (creates new OTP request)

    Cannot resend:
    - Expired OTPs
    - Already verified OTPs

    Useful when user didn't receive OTP or wants multi-channel verification.
    """
    service = OTPService(db)

    try:
        response, otp_code = await service.resend_otp(
            request=request,
            user_id=current_user.user_id if current_user else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Trigger delivery
        await service.send_otp(response.request_id, otp_code)

        return response

    except OTPExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP request has expired. Please request a new one.",
        )
    except InvalidOTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
