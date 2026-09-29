"""
Password reset service for password reset and recovery operations.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    InvalidOTPError,
    InvalidTokenError,
    OTPExpiredError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.core.security import (
    hash_otp,
    hash_password,
    verify_otp_hash,
    verify_password,
)
from app.db.enums import enum_value
from app.db.enums import ApprovalStatus, OTPChannel, OTPPurpose
from app.repositories import AuditLogRepository, OTPRepository, UserRepository
from app.repositories.password_reset import PasswordResetRepository
from app.schemas.password_reset import (
    CompletePasswordResetRequest,
    OTPVerificationRequest,
    OTPVerificationResponse,
    PasswordResetApprovalRequest,
    PasswordResetApprovalResponse,
    PasswordResetRequestResponse,
    PasswordResetStatusResponse,
)

logger = structlog.get_logger()

MAX_OTP_ATTEMPTS = 5


class PasswordResetService:
    """Service for password reset and recovery operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.password_reset_repo = PasswordResetRepository(db)
        self.otp_repo = OTPRepository(db)
        self.audit_repo = AuditLogRepository(db)

    # ─────────────────────────────────────────────────────────────────────────
    # Password Reset Request
    # ─────────────────────────────────────────────────────────────────────────

    async def request_password_reset(
        self,
        username: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PasswordResetRequestResponse:
        """Initiate password reset request.

        Returns response without revealing if user exists (security).
        """
        # Find user (case-insensitive)
        user = await self.user_repo.get_by_username(username)

        # Always return success message for security (user enumeration prevention)
        response = PasswordResetRequestResponse(
            request_id="",
            message="If the account exists, a password reset request has been created",
            expires_in_minutes=1440,
        )

        if not user:
            # Log the attempt without revealing if user exists
            await logger.awarning(
                "password_reset_requested_unknown_user",
                username=username,
                ip_address=ip_address,
            )
            return response

        # Check if user already has active reset request
        active_request = await self.password_reset_repo.get_active_request(user.id)
        if active_request:
            # Return existing request ID
            response.request_id = active_request.id
            await logger.ainfo(
                "password_reset_requested_existing",
                user_id=user.id,
                request_id=active_request.id,
            )
            return response

        # Create new password reset request
        reset_request = await self.password_reset_repo.create_request(user.id)

        # Audit log
        await self.audit_repo.log_action(
            action="password_reset_requested",
            resource_type="password_reset",
            resource_id=reset_request.id,
            actor_user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"username": username},
        )

        await logger.ainfo(
            "password_reset_requested",
            user_id=user.id,
            request_id=reset_request.id,
        )

        response.request_id = reset_request.id
        return response

    # ─────────────────────────────────────────────────────────────────────────
    # Password Reset Status
    # ─────────────────────────────────────────────────────────────────────────

    async def get_reset_status(
        self,
        request_id: str,
        user_id: str,
    ) -> PasswordResetStatusResponse:
        """Get current status of password reset request."""
        request = await self.password_reset_repo.get_by_id(request_id)

        if not request:
            raise InvalidTokenError("Reset request not found")

        # Verify user ownership
        if request.user_id != user_id:
            raise PermissionDeniedError()

        if request.is_expired:
            raise InvalidTokenError("Reset request has expired")

        if request.completed_at:
            raise InvalidTokenError("Reset request already completed")

        return PasswordResetStatusResponse(
            request_id=request.id,
            phone_verified=request.phone_verified_at is not None,
            email_verified=request.email_verified_at is not None,
            admin_approval_status=enum_value(request.admin_approval_status),
            can_complete=request.can_complete,
            expires_at=request.expires_at,
            is_expired=request.is_expired,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # OTP Verification
    # ─────────────────────────────────────────────────────────────────────────

    async def verify_otp(
        self,
        request: OTPVerificationRequest,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OTPVerificationResponse:
        """Verify OTP for password reset."""
        # Get reset request
        reset_request = await self.password_reset_repo.get_by_id(
            request.reset_request_id
        )

        if not reset_request:
            raise InvalidTokenError("Reset request not found")

        # Verify user ownership
        if reset_request.user_id != user_id:
            raise PermissionDeniedError()

        if reset_request.is_expired:
            raise InvalidTokenError("Reset request has expired")

        if reset_request.completed_at:
            raise InvalidTokenError("Reset request already completed")

        # The reset request has no OTP id of its own: the OTP is the user's newest
        # still-valid password-reset OTP on the channel being verified.
        otp = await self.otp_repo.get_latest_valid_for_user(
            reset_request.user_id,
            OTPPurpose.PASSWORD_RESET,
            OTPChannel(enum_value(request.channel)),
        )

        if not otp:
            raise OTPExpiredError()

        # Check if already used
        if otp.used_at:
            raise InvalidTokenError("OTP has already been used")

        # Check attempt limit
        if otp.attempt_count >= MAX_OTP_ATTEMPTS:
            raise InvalidTokenError("Maximum OTP verification attempts exceeded")

        # Verify OTP code
        if not verify_otp_hash(request.otp, otp.otp_hash):
            # Increment attempt count
            await self.otp_repo.increment_attempts(otp.id)
            await logger.awarning(
                "password_reset_otp_invalid",
                user_id=user_id,
                request_id=request.reset_request_id,
                attempt=otp.attempt_count + 1,
            )
            raise InvalidOTPError()

        # Mark OTP as used
        await self.otp_repo.mark_used(otp.id)

        # Mark phone or email as verified
        if enum_value(request.channel) == OTPChannel.SMS.value:
            await self.password_reset_repo.mark_phone_verified(
                request.reset_request_id
            )
        else:  # EMAIL
            await self.password_reset_repo.mark_email_verified(
                request.reset_request_id
            )

        # Audit log
        await self.audit_repo.log_action(
            action="password_reset_otp_verified",
            resource_type="password_reset",
            resource_id=request.reset_request_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"channel": enum_value(request.channel)},
        )

        await logger.ainfo(
            "password_reset_otp_verified",
            user_id=user_id,
            request_id=request.reset_request_id,
            channel=enum_value(request.channel),
        )

        return OTPVerificationResponse(
            verified=True,
            channel=enum_value(request.channel),
            message="OTP verified successfully",
            next_step="awaiting_admin_approval",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Password Reset Completion
    # ─────────────────────────────────────────────────────────────────────────

    async def complete_password_reset(
        self,
        request: CompletePasswordResetRequest,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Complete password reset after all verifications."""
        # Get reset request
        reset_request = await self.password_reset_repo.get_by_id_with_relations(
            request.reset_request_id
        )

        if not reset_request:
            raise InvalidTokenError("Reset request not found")

        # Verify user ownership
        if reset_request.user_id != user_id:
            raise PermissionDeniedError()

        # Verify not expired
        if reset_request.is_expired:
            raise InvalidTokenError("Reset request has expired")

        # Verify not already completed (one-time use)
        if reset_request.completed_at:
            raise InvalidTokenError("Reset request already completed")

        # Verify all conditions met
        if not reset_request.can_complete:
            missing_steps = []
            if not reset_request.is_verified:
                missing_steps.append("OTP verification")
            if not reset_request.is_approved:
                missing_steps.append("admin approval")
            raise InvalidTokenError(f"Incomplete: {', '.join(missing_steps)}")

        # Get user
        user = reset_request.user
        if not user:
            raise UserNotFoundError()

        # Update password
        user.password_hash = hash_password(request.new_password)
        user.password_changed_at = datetime.now(UTC)

        # Mark request as completed (one-time use enforcement)
        await self.password_reset_repo.complete(request.reset_request_id)

        # Revoke all refresh tokens (force re-login)
        from app.repositories import RefreshTokenRepository

        token_repo = RefreshTokenRepository(self.db)
        revoked_count = await token_repo.revoke_all_for_user(user.id)

        # Audit log
        await self.audit_repo.log_action(
            action="password_reset_completed",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"tokens_revoked": revoked_count},
        )

        await logger.ainfo(
            "password_reset_completed",
            user_id=user.id,
            request_id=request.reset_request_id,
            tokens_revoked=revoked_count,
        )

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Admin Approval
    # ─────────────────────────────────────────────────────────────────────────

    async def approve_password_reset(
        self,
        request: PasswordResetApprovalRequest,
        admin_user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> PasswordResetApprovalResponse:
        """Approve password reset request (admin action)."""
        reset_request = await self.password_reset_repo.get_pending_for_approval(
            request.reset_request_id
        )

        if not reset_request:
            raise InvalidTokenError("Reset request not found or not pending approval")

        if request.approve:
            # Approve
            await self.password_reset_repo.approve(
                request.reset_request_id,
                admin_user_id,
                note=request.reason,
            )

            status = ApprovalStatus.APPROVED.value
            message = "Password reset request approved"

            await logger.ainfo(
                "password_reset_approved",
                request_id=request.reset_request_id,
                approved_by=admin_user_id,
            )
        else:
            # Reject
            if not request.reason:
                raise ValueError("Rejection reason is required")

            await self.password_reset_repo.reject(
                request.reset_request_id,
                admin_user_id,
                reason=request.reason,
            )

            status = ApprovalStatus.REJECTED.value
            message = "Password reset request rejected"

            await logger.ainfo(
                "password_reset_rejected",
                request_id=request.reset_request_id,
                rejected_by=admin_user_id,
                reason=request.reason,
            )

        # Audit log
        await self.audit_repo.log_action(
            action=f"password_reset_{'approved' if request.approve else 'rejected'}",
            resource_type="password_reset",
            resource_id=request.reset_request_id,
            actor_user_id=admin_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "approved": request.approve,
                "reason": request.reason,
            },
        )

        return PasswordResetApprovalResponse(
            reset_request_id=request.reset_request_id,
            status=status,
            message=message,
        )
