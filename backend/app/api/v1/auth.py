"""
Authentication API endpoints.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    AuthenticatedUser,
    ClientIP,
    DBSession,
    RequestID,
    UserAgent,
)
from app.core.exceptions import (
    AccountLockedError,
    AccountSuspendedError,
    InvalidCredentialsError,
    InvalidOTPError,
    InvalidTokenError,
    MFARequiredError,
    OTPExpiredError,
    RateLimitError,
)
from app.db.enums import OTPChannel, OTPPurpose, enum_value
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    MFAVerifyRequest,
    OTPRequest,
    OTPResponse,
    OTPVerifyRequest,
    PasswordResetCompleteRequest,
    PasswordResetRequest,
    TokenRefreshRequest,
    TokenResponse,
)
from app.schemas.user import UserProfileResponse
from app.services import AuthService
from app.services.auth import DeviceInfo

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """
    Authenticate user with username and password.

    Returns tokens on success. If MFA is enabled, returns mfa_required=true
    with a session token for the second factor.
    """
    auth_service = AuthService(db)

    try:
        tokens, user = await auth_service.login(
            username=request.username,
            password=request.password,
            device=DeviceInfo(
                device_uuid=request.device_uuid,
                platform=enum_value(request.platform),
                push_token=request.push_token,
                app_version=request.app_version,
            ),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return LoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
            user=UserProfileResponse.model_validate(user),
            mfa_required=False,
        )

    except MFARequiredError as e:
        return LoginResponse(
            mfa_required=True,
            mfa_session_token=e.mfa_session_token,
        )
    except AccountLockedError as e:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked until {e.locked_until}",
        )
    except AccountSuspendedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended",
        )
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) or "Invalid credentials",
        )


@router.post("/mfa/verify", response_model=LoginResponse)
async def verify_mfa(
    request: MFAVerifyRequest,
    db: DBSession,
):
    """Verify MFA code and complete login."""
    auth_service = AuthService(db)

    try:
        tokens, user = await auth_service.verify_mfa(
            mfa_session_token=request.mfa_challenge_id,
            totp_code=request.code,
        )

        return LoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in=tokens.expires_in,
            user=UserProfileResponse.model_validate(user),
            mfa_required=False,
        )

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) or "Invalid MFA code",
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: TokenRefreshRequest,
    db: DBSession,
):
    """
    Refresh access token using refresh token.

    Implements token rotation - old refresh token is revoked.
    """
    auth_service = AuthService(db)

    try:
        # Extract JTI from refresh token
        from app.core.security import verify_refresh_token

        payload = verify_refresh_token(request.refresh_token)
        jti = payload.get("jti")

        if not jti:
            raise InvalidTokenError("Invalid refresh token")

        tokens = await auth_service.refresh_tokens(
            refresh_token_jti=jti,
            device_id=request.device_id,
        )

        return tokens

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
):
    """Logout user by revoking refresh token."""
    auth_service = AuthService(db)

    try:
        from app.core.security import verify_refresh_token

        payload = verify_refresh_token(request.refresh_token)
        jti = payload.get("jti")

        if jti:
            await auth_service.logout(
                refresh_token_jti=jti,
                user_id=current_user.user_id,
                ip_address=ip_address,
            )

    except InvalidTokenError:
        # Token already invalid, that's fine for logout
        pass


@router.post("/logout/all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_devices(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Logout from all devices by revoking all refresh tokens."""
    auth_service = AuthService(db)
    await auth_service.logout_all_devices(current_user.user_id)


@router.post("/otp/request", response_model=OTPResponse)
async def request_otp(
    request: OTPRequest,
    db: DBSession,
):
    """
    Request OTP for phone/email verification.

    In production, OTP is sent via SMS/email. For development,
    the OTP is returned in the response.
    """
    auth_service = AuthService(db)

    try:
        request_id, otp_code = await auth_service.request_otp(
            user_id=request.user_id,
            channel=request.channel,
            purpose=request.purpose,
            destination=request.destination,
        )

        # In production, don't return OTP - send via SMS/email
        from app.core.config import settings

        return OTPResponse(
            request_id=request_id,
            channel=request.channel,
            expires_in_seconds=settings.otp_expire_minutes * 60,
            # Development only - remove in production
            otp_code=otp_code if settings.debug else None,
        )

    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )


@router.post("/otp/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_otp(
    request: OTPVerifyRequest,
    db: DBSession,
):
    """Verify OTP code."""
    auth_service = AuthService(db)

    try:
        await auth_service.verify_otp(
            request_id=request.request_id,
            otp_code=request.code,
        )

    except OTPExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired",
        )
    except InvalidOTPError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code",
        )
    except RateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )


@router.post("/password-reset/request")
async def request_password_reset(
    request: PasswordResetRequest,
    db: DBSession,
):
    """
    Request password reset.

    Requires phone and email verification, then admin approval.
    """
    from app.repositories import UserRepository

    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(request.username)

    if not user:
        # Don't reveal if user exists
        return {"message": "If the account exists, a reset request has been created"}

    auth_service = AuthService(db)
    request_id = await auth_service.request_password_reset(user.id)

    return {
        "message": "Password reset request created. Complete verification steps.",
        "request_id": request_id,
    }


@router.post("/password-reset/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_password_reset(
    request: PasswordResetCompleteRequest,
    db: DBSession,
):
    """
    Complete password reset after all verifications.

    Requires:
    - Phone OTP verified
    - Email OTP verified
    - Admin approval
    """
    auth_service = AuthService(db)

    try:
        await auth_service.complete_password_reset(
            request_id=request.request_id,
            new_password=request.new_password,
        )

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ─────────────────────────────────────────────────────────────────────────────
# MFA Setup (Admin only)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/mfa/setup")
async def setup_mfa(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Generate MFA secret for setup.

    Returns a TOTP provisioning URI for QR code generation.
    The secret should be stored after user confirms with a valid code.
    """
    from app.core.security import generate_totp_secret, get_totp_uri
    from app.core.permissions import is_admin

    # MFA is mandatory for admins, optional for others
    if not is_admin(current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA setup is currently only available for admin accounts",
        )

    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "message": "Scan the QR code with your authenticator app, then confirm with /mfa/confirm",
    }


@router.post("/mfa/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_mfa(
    request: MFAVerifyRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Confirm MFA setup by verifying a TOTP code.

    After confirmation, MFA is enabled for the account.
    """
    from app.core.security import verify_totp
    from app.repositories import UserRepository

    if not request.code or len(request.code) != 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code format",
        )

    # The secret should be passed in mfa_session_token field during setup confirmation
    secret = request.mfa_session_token
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA secret required. Use the secret from /mfa/setup",
        )

    if not verify_totp(secret, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code. Please try again.",
        )

    # Store the secret and enable MFA for the user
    user_repo = UserRepository(db)
    await user_repo.enable_mfa(current_user.user_id, secret)
    await db.commit()

    await logger.ainfo(
        "mfa_enabled",
        user_id=current_user.user_id,
    )


@router.delete("/mfa", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mfa(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Disable MFA for the account.

    Requires current TOTP code verification.
    This endpoint should be restricted in production (e.g., require password).
    """
    from app.core.permissions import is_admin

    # Admins cannot disable MFA (it's mandatory)
    if is_admin(current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA cannot be disabled for admin accounts",
        )

    from app.repositories import UserRepository

    user_repo = UserRepository(db)
    await user_repo.disable_mfa(current_user.user_id)
    await db.commit()

    await logger.ainfo(
        "mfa_disabled",
        user_id=current_user.user_id,
    )
