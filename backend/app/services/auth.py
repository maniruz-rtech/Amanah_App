"""
Authentication service for login, tokens, OTP, and password reset.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decrypt_field,
    encrypt_field,
    generate_otp,
    hash_contact,
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_password,
    verify_totp,
)
from app.db.enums import OTPChannel, OTPPurpose
from app.db.models import Device, User
from app.repositories import (
    AuditLogRepository,
    DeviceRepository,
    OTPRepository,
    PasswordResetRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import TokenResponse

logger = structlog.get_logger()

# Simple in-memory MFA session store (should be Redis in production)
_mfa_sessions: dict[str, dict] = {}


MAX_DEVICES = 10


@dataclass(frozen=True)
class DeviceInfo:
    """Device identity presented at login (see ``app.db.models.device.Device``)."""

    device_uuid: str
    platform: str
    push_token: str | None = None
    app_version: str | None = None


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.device_repo = DeviceRepository(db)
        self.token_repo = RefreshTokenRepository(db)
        self.otp_repo = OTPRepository(db)
        self.password_reset_repo = PasswordResetRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def login(
        self,
        username: str,
        password: str,
        device: DeviceInfo | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[TokenResponse, User]:
        """
        Authenticate user and return tokens.

        Returns (TokenResponse, User) or raises exception.
        """
        # Find user
        user = await self.user_repo.get_by_username(username)

        if not user:
            await logger.awarning("login_failed_user_not_found", username=username)
            raise InvalidCredentialsError()

        # Check account status
        if not user.is_active:
            await logger.awarning("login_failed_inactive", user_id=user.id)
            raise InvalidCredentialsError()  # generic: do not reveal account state

        if user.is_suspended:
            await logger.awarning("login_failed_suspended", user_id=user.id)
            raise AccountSuspendedError()

        # Check lockout
        if user.locked_until and user.locked_until > datetime.now(UTC):
            lockout_minutes = int((user.locked_until - datetime.now(UTC)).total_seconds() / 60)
            await logger.awarning("login_failed_locked", user_id=user.id)
            raise AccountLockedError(lockout_minutes=lockout_minutes)

        # Verify password
        if not verify_password(password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= settings.account_lockout_attempts:
                # Lock account
                user.locked_until = datetime.now(UTC) + timedelta(
                    minutes=settings.account_lockout_duration_minutes
                )
                await logger.awarning(
                    "account_locked",
                    user_id=user.id,
                    attempts=user.failed_login_attempts,
                )

            await self.db.flush()
            raise InvalidCredentialsError()

        # Check if MFA is required
        if user.mfa_enabled:
            # Generate MFA session token for second factor
            mfa_session_token = secrets.token_urlsafe(32)
            # Store in simple session dict (in production, use Redis with TTL)
            _mfa_sessions[mfa_session_token] = {
                "user_id": user.id,
                "created_at": datetime.now(UTC),
                "device": device,
            }
            raise MFARequiredError(mfa_session_token=mfa_session_token)

        # Successful login - reset failed attempts
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        await self.db.flush()

        # Bind (register or refresh) the device this login came from, then issue
        # tokens bound to it.
        device_id = await self._bind_device(user, device)
        tokens = await self._generate_tokens(user, device_id)

        # Audit log
        await self.audit_repo.log_action(
            action="login",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=user.id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await logger.ainfo("login_success", user_id=user.id)
        return tokens, user

    async def verify_mfa(
        self,
        mfa_session_token: str,
        totp_code: str,
    ) -> tuple[TokenResponse, User]:
        """Verify MFA code and complete login."""
        # Get user from session
        session = _mfa_sessions.get(mfa_session_token)
        if not session:
            raise InvalidTokenError("Invalid or expired MFA session")

        user = await self.user_repo.get_by_id(session["user_id"])
        if not user:
            raise InvalidTokenError("User not found")

        # Verify TOTP
        if not user.totp_secret_encrypted:
            raise InvalidTokenError("MFA not configured")

        try:
            totp_secret = decrypt_field(user.totp_secret_encrypted)
        except Exception:
            raise InvalidTokenError("Failed to decrypt TOTP secret")

        if not verify_totp(totp_secret, totp_code):
            raise InvalidCredentialsError("Invalid MFA code")

        # Clear session
        del _mfa_sessions[mfa_session_token]

        # Update last login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)
        await self.db.flush()

        # Device presented at the first factor
        device_id = await self._bind_device(user, session.get("device"))
        tokens = await self._generate_tokens(user, device_id)

        await logger.ainfo("mfa_verified", user_id=user.id)
        return tokens, user

    async def refresh_tokens(
        self,
        refresh_token_jti: str,
        device_id: str | None = None,
    ) -> TokenResponse:
        """Refresh access token using refresh token JTI."""
        # Get token record
        token_record = await self.token_repo.get_by_jti(refresh_token_jti)

        if not token_record:
            raise InvalidTokenError("Token not found")

        if token_record.is_revoked:
            # Possible token reuse attack - revoke all tokens for user
            await self.token_repo.revoke_all_for_user(token_record.user_id)
            await logger.awarning(
                "refresh_token_reuse_detected",
                user_id=token_record.user_id,
                jti=refresh_token_jti,
            )
            raise InvalidTokenError("Token has been revoked")

        if token_record.expires_at < datetime.now(UTC):
            raise InvalidTokenError("Token has expired")

        # Get user
        user = await self.user_repo.get_by_id(token_record.user_id)
        if not user or not user.is_active or user.is_suspended:
            raise InvalidTokenError("User is not active")

        # Rotate token
        new_jti = secrets.token_urlsafe(32)
        new_token_record = await self.token_repo.rotate_token(
            old_jti=refresh_token_jti,
            new_jti=new_jti,
            user_id=user.id,
            device_id=token_record.device_id,  # binding survives rotation
        )

        if not new_token_record:
            raise InvalidTokenError("Failed to rotate token")

        # Generate new tokens
        access_token = create_access_token(
            user_id=user.id,
            roles=user.roles,
            device_id=token_record.device_id,
        )
        refresh_token = create_refresh_token(
            user_id=user.id, jti=new_jti, device_id=token_record.device_id
        )

        await logger.ainfo("tokens_refreshed", user_id=user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )

    async def logout(
        self,
        refresh_token_jti: str,
        user_id: str,
        ip_address: str | None = None,
    ) -> None:
        """Logout user by revoking refresh token."""
        await self.token_repo.revoke_token(refresh_token_jti)

        await self.audit_repo.log_action(
            action="logout",
            resource_type="user",
            resource_id=user_id,
            actor_user_id=user_id,
            ip_address=ip_address,
        )

        await logger.ainfo("logout_success", user_id=user_id)

    async def logout_all_devices(self, user_id: str) -> int:
        """Revoke all refresh tokens for user."""
        count = await self.token_repo.revoke_all_for_user(user_id)
        await logger.ainfo("logout_all_devices", user_id=user_id, tokens_revoked=count)
        return count

    async def request_otp(
        self,
        user_id: str | None,
        channel: OTPChannel,
        purpose: OTPPurpose,
        destination: str,
    ) -> tuple[str, str]:
        """
        Generate and return OTP request.

        Returns (request_id, otp_code) - OTP code should be sent via SMS/email.
        """
        # Generate OTP
        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)
        destination_hash = hash_contact(destination)

        # Create OTP request
        otp_request = await self.otp_repo.create_otp(
            user_id=user_id,
            channel=channel,
            purpose=purpose,
            destination_hash=destination_hash,
            otp_hash=otp_hash,
        )

        await logger.ainfo(
            "otp_requested",
            request_id=otp_request.id,
            channel=channel,
            purpose=purpose,
        )

        return otp_request.id, otp_code

    async def verify_otp(
        self,
        request_id: str,
        otp_code: str,
    ) -> bool:
        """Verify OTP code."""
        otp_request = await self.otp_repo.get_by_id(request_id)

        if (
            not otp_request
            or otp_request.used_at is not None
            or otp_request.expires_at <= datetime.now(UTC)
        ):
            raise OTPExpiredError()

        # Attempts exhausted (checked separately so callers get a rate-limit
        # error rather than a misleading "expired")
        if otp_request.attempt_count >= otp_request.max_attempts:
            raise RateLimitError("Too many OTP attempts")

        # Verify code
        if not verify_otp_hash(otp_code, otp_request.otp_hash):
            await self.otp_repo.increment_attempts(request_id)
            raise InvalidOTPError()

        # Mark as used
        await self.otp_repo.mark_used(request_id)

        await logger.ainfo("otp_verified", request_id=request_id)
        return True

    async def request_password_reset(
        self,
        user_id: str,
    ) -> str:
        """Create password reset request. Returns request_id."""
        request = await self.password_reset_repo.create_request(user_id)

        await self.audit_repo.log_action(
            action="password_reset_requested",
            resource_type="password_reset",
            resource_id=request.id,
            actor_user_id=user_id,
        )

        await logger.ainfo("password_reset_requested", user_id=user_id, request_id=request.id)
        return request.id

    async def complete_password_reset(
        self,
        request_id: str,
        new_password: str,
    ) -> bool:
        """Complete password reset after all verifications."""
        request = await self.password_reset_repo.get_by_id(request_id)

        if not request:
            raise InvalidTokenError("Reset request not found")

        if request.expires_at < datetime.now(UTC):
            raise InvalidTokenError("Reset request has expired")

        if request.completed_at:
            raise InvalidTokenError("Reset request already completed")

        # Update password
        user = await self.user_repo.get_by_id(request.user_id)
        if not user:
            raise InvalidTokenError("User not found")

        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC)

        # Mark request completed
        await self.password_reset_repo.complete(request_id)

        # Revoke all refresh tokens
        await self.token_repo.revoke_all_for_user(user.id)

        await self.audit_repo.log_action(
            action="password_reset_completed",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=user.id,
        )

        await logger.ainfo("password_reset_completed", user_id=user.id)
        return True

    async def _bind_device(self, user: User, device: DeviceInfo | None) -> str | None:
        """Register the login device (idempotent per install) and return its id.

        Logging in again from the same installation (same ``device_uuid``) reuses
        the row, refreshing push token / app version / last-seen. When a *new*
        device would exceed ``MAX_DEVICES`` the least-recently-seen non-primary
        device is deactivated so a user with stale devices can never be locked
        out of logging in.
        """
        if device is None:
            return None

        existing = await self.device_repo.get_by_uuid(user.id, device.device_uuid)
        if existing is None:
            if await self.device_repo.get_user_active_device_count(user.id) >= MAX_DEVICES:
                await self.device_repo.deactivate_stalest(user.id)

        registered = await self.device_repo.register_or_update(
            user_id=user.id,
            device_uuid=device.device_uuid,
            platform=device.platform,
            push_token=device.push_token,
            app_version=device.app_version,
        )
        await self.audit_repo.log_action(
            action="device_registered",
            resource_type="device",
            resource_id=registered.id,
            actor_user_id=user.id,
            device_id=registered.id,
            metadata={"platform": device.platform, "is_new": existing is None},
        )
        return registered.id

    async def _generate_tokens(
        self,
        user: User,
        device_id: str | None = None,
    ) -> TokenResponse:
        """Generate access and refresh tokens for user."""
        # Get user roles from property
        roles = user.roles

        # Generate JTI for refresh token
        jti = secrets.token_urlsafe(32)

        # Create tokens with roles
        access_token = create_access_token(user_id=user.id, roles=roles, device_id=device_id)
        refresh_token = create_refresh_token(user_id=user.id, jti=jti, device_id=device_id)

        await self.token_repo.create_token(user_id=user.id, jti=jti, device_id=device_id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
