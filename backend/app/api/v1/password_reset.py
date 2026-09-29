"""
Password reset API endpoints.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    AuthenticatedUser,
    ClientIP,
    DBSession,
    UserAgent,
)
from app.core.exceptions import (
    InvalidOTPError,
    InvalidTokenError,
    OTPExpiredError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.schemas.password_reset import (
    CompletePasswordResetRequest,
    CompletePasswordResetResponse,
    OTPVerificationRequest,
    OTPVerificationResponse,
    PasswordResetApprovalRequest,
    PasswordResetApprovalResponse,
    PasswordResetRequestCreate,
    PasswordResetRequestResponse,
    PasswordResetStatusResponse,
)
from app.services.password_reset import PasswordResetService

logger = structlog.get_logger()

router = APIRouter(prefix="/password-reset", tags=["Password Reset"])


# ─────────────────────────────────────────────────────────────────────────────
# Request Password Reset
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_password_reset(
    request: PasswordResetRequestCreate,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Initiate password reset request.

    Sends OTP to user's registered phone or email.
    This endpoint does not reveal if a user exists (user enumeration prevention).
    """
    service = PasswordResetService(db)
    response = await service.request_password_reset(
        username=request.username,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Get Reset Status
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{request_id}/status", response_model=PasswordResetStatusResponse)
async def get_reset_status(
    request_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get current status of password reset request.

    Allows user to check progress through the reset flow:
    - Phone/email verification status
    - Admin approval status
    - Whether reset can be completed
    - Expiration time
    """
    service = PasswordResetService(db)
    try:
        status = await service.get_reset_status(
            request_id=request_id,
            user_id=current_user.user_id,
        )
        return status

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this reset request",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Verify OTP
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/verify-otp", response_model=OTPVerificationResponse)
async def verify_otp(
    request: OTPVerificationRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Verify OTP for password reset.

    User must verify phone or email OTP (as requested in reset initiation).
    """
    service = PasswordResetService(db)
    try:
        response = await service.verify_otp(
            request=request,
            user_id=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return response

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except OTPExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new reset.",
        )
    except InvalidOTPError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code. Please try again.",
        )
    except PermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this reset request",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Complete Password Reset
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/complete",
    response_model=CompletePasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
async def complete_password_reset(
    request: CompletePasswordResetRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Complete password reset with new password.

    Can only be called after:
    - OTP verification (phone or email)
    - Admin approval

    Password requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*)

    Upon successful completion:
    - Password is updated
    - All existing refresh tokens are revoked (requires re-login)
    - This becomes a one-time-use operation (cannot be repeated)
    """
    service = PasswordResetService(db)
    try:
        success = await service.complete_password_reset(
            request=request,
            user_id=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if success:
            return CompletePasswordResetResponse()

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this reset request",
        )
    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Admin Approval (integration with admin module)
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{request_id}/approve",
    response_model=PasswordResetApprovalResponse,
)
async def approve_password_reset(
    request_id: str,
    request: PasswordResetApprovalRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Approve or reject password reset (admin action).

    Admins review and approve password reset requests in their region.
    This is a required step before users can complete the reset.

    To reject, set approve=false and provide a reason.
    """
    # Check if user has admin role (this should be in admin router)
    # For now, this endpoint documents the approval flow
    service = PasswordResetService(db)

    request.reset_request_id = request_id

    try:
        response = await service.approve_password_reset(
            request=request,
            admin_user_id=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return response

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
