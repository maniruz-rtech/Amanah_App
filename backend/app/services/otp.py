"""
OTP service for OTP generation, delivery, and verification.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    InvalidOTPError,
    OTPExpiredError,
    RateLimitError,
    UserNotFoundError,
)
from app.core.security import generate_otp, hash_contact, hash_otp, verify_otp_hash
from app.db.enums import enum_value
from app.db.enums import OTPChannel, OTPPurpose
from app.repositories import AuditLogRepository, UserRepository
from app.repositories.otp import OTPRepository
from app.schemas.otp import (
    OTPBatchResponse,
    OTPRequestCreate,
    OTPResendRequest,
    OTPResendResponse,
    OTPResponse,
    OTPStatusResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    OTPVerifyStep,
)

logger = structlog.get_logger()


class OTPService:
    """Service for OTP generation, delivery, and verification."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.otp_repo = OTPRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditLogRepository(db)

    # ─────────────────────────────────────────────────────────────────────────
    # OTP Generation and Delivery
    # ─────────────────────────────────────────────────────────────────────────

    async def request_otp(
        self,
        request: OTPRequestCreate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[OTPResponse, str]:
        """
        Request OTP for verification.

        Returns (OTPResponse, OTP code) where OTP code is for delivery.
        In production, OTP code is sent via SMS/email only, not returned.
        """
        # Verify user exists if user_id provided
        if request.user_id:
            user = await self.user_repo.get_by_id(request.user_id)
            if not user:
                raise UserNotFoundError()

        # Check for duplicate active request (prevent spam)
        destination_hash = hash_contact(request.destination)
        existing_otp = await self.otp_repo.get_by_destination_hash(
            destination_hash=destination_hash,
            purpose=request.purpose,
            channel=request.channel,
        )

        if existing_otp:
            # Return existing request (user already has valid OTP)
            await logger.ainfo(
                "otp_duplicate_request",
                request_id=existing_otp.id,
                purpose=enum_value(request.purpose),
                channel=enum_value(request.channel),
            )

            expires_in_seconds = int(
                (existing_otp.expires_at - datetime.now(UTC)).total_seconds()
            )

            return (
                OTPResponse(
                    request_id=existing_otp.id,
                    channel=enum_value(request.channel),
                    expires_in_seconds=expires_in_seconds,
                    message="OTP already sent to this destination",
                    otp_code=None,  # Never return existing OTP
                ),
                "",  # Don't resend
            )

        # Generate new OTP
        otp_code = generate_otp()
        otp_hash = hash_otp(otp_code)

        # Create OTP request in database
        otp = await self.otp_repo.create_otp(
            user_id=request.user_id,
            channel=request.channel,
            purpose=request.purpose,
            destination_hash=destination_hash,
            otp_hash=otp_hash,
        )

        # Audit log
        await self.audit_repo.log_action(
            action="otp_requested",
            resource_type="otp",
            resource_id=otp.id,
            actor_user_id=request.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "channel": enum_value(request.channel),
                "purpose": enum_value(request.purpose),
            },
        )

        await logger.ainfo(
            "otp_requested",
            request_id=otp.id,
            channel=enum_value(request.channel),
            purpose=enum_value(request.purpose),
        )

        # Prepare response
        response = OTPResponse(
            request_id=otp.id,
            channel=enum_value(request.channel),
            expires_in_seconds=settings.otp_expire_minutes * 60,
            message="OTP has been sent",
            # Only include OTP in development mode
            otp_code=otp_code if settings.debug else None,
        )

        # Return response and code (for delivery system to use)
        return response, otp_code

    # ─────────────────────────────────────────────────────────────────────────
    # OTP Verification
    # ─────────────────────────────────────────────────────────────────────────

    async def verify_otp(
        self,
        request: OTPVerifyRequest,
        user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> OTPVerifyResponse:
        """
        Verify OTP code.

        Enforces:
        - Expiration (TTL)
        - One-time use semantics
        - Attempt limits with rate limiting
        """
        # Get valid OTP
        otp = await self.otp_repo.get_valid_otp(request.request_id)

        if not otp:
            await logger.awarning(
                "otp_verification_invalid_request",
                request_id=request.request_id,
            )
            raise OTPExpiredError()

        # Verify user ownership if user_id provided
        if user_id and otp.user_id and otp.user_id != user_id:
            await logger.awarning(
                "otp_verification_unauthorized",
                request_id=request.request_id,
                user_id=user_id,
                otp_user_id=otp.user_id,
            )
            raise InvalidOTPError()

        # Check if expired
        if otp.is_expired:
            await logger.awarning(
                "otp_verification_expired",
                request_id=request.request_id,
            )
            raise OTPExpiredError()

        # Check attempts
        if otp.is_max_attempts_exceeded:
            await logger.awarning(
                "otp_verification_max_attempts",
                request_id=request.request_id,
                attempts=otp.attempt_count,
                max_attempts=otp.max_attempts,
            )
            raise RateLimitError("Maximum OTP attempts exceeded")

        # Verify code
        if not verify_otp_hash(request.code, otp.otp_hash):
            updated = await self.otp_repo.increment_attempts(request.request_id)
            attempts_used = updated.attempt_count if updated else otp.attempt_count + 1

            await logger.awarning(
                "otp_verification_invalid_code",
                request_id=request.request_id,
                attempt=attempts_used,
                max_attempts=otp.max_attempts,
            )

            # The wrong guess that exhausts the budget locks the request out.
            remaining = otp.max_attempts - attempts_used
            if remaining <= 0:
                raise RateLimitError("Maximum OTP attempts exceeded")
            raise InvalidOTPError(f"{remaining} attempts remaining")

        # Mark as used (one-time use enforcement)
        await self.otp_repo.mark_used(request.request_id)

        # Audit log
        await self.audit_repo.log_action(
            action="otp_verified",
            resource_type="otp",
            resource_id=request.request_id,
            actor_user_id=user_id or otp.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "channel": enum_value(otp.channel),
                "purpose": enum_value(otp.purpose),
            },
        )

        await logger.ainfo(
            "otp_verified",
            request_id=request.request_id,
            channel=enum_value(otp.channel),
            purpose=enum_value(otp.purpose),
        )

        return OTPVerifyResponse(
            verified=True,
            message="OTP verified successfully",
            channel=enum_value(otp.channel),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # OTP Status and Resend
    # ─────────────────────────────────────────────────────────────────────────

    async def get_otp_status(
        self,
        request_id: str,
        user_id: str | None = None,
    ) -> OTPStatusResponse:
        """Get OTP request status."""
        otp = await self.otp_repo.get_by_id_with_details(request_id)

        if not otp:
            raise OTPExpiredError()

        # Verify user ownership if provided
        if user_id and otp.user_id and otp.user_id != user_id:
            raise InvalidOTPError()

        attempts_remaining = max(0, otp.max_attempts - otp.attempt_count)

        return OTPStatusResponse(
            request_id=otp.id,
            purpose=enum_value(otp.purpose),
            channel=enum_value(otp.channel),
            is_verified=otp.is_used,
            is_expired=otp.is_expired,
            is_used=otp.is_used,
            attempts_remaining=attempts_remaining,
            expires_at=otp.expires_at,
            created_at=otp.created_at,
            verified_at=otp.used_at,
        )

    async def resend_otp(
        self,
        request: OTPResendRequest,
        user_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[OTPResendResponse, str]:
        """
        Resend OTP.

        Returns new OTP request if changing channel, or reuses same request.
        """
        # Get existing OTP
        otp = await self.otp_repo.get_by_id_with_details(request.request_id)

        if not otp:
            raise OTPExpiredError()

        # Verify user ownership if provided
        if user_id and otp.user_id and otp.user_id != user_id:
            raise InvalidOTPError()

        if otp.is_expired:
            raise OTPExpiredError()

        if otp.is_used:
            raise InvalidOTPError("OTP already used")

        # If channel change requested, create new OTP
        if request.channel and request.channel != otp.channel:
            # Create new OTP for different channel
            otp_code = generate_otp()
            otp_hash = hash_otp(otp_code)

            new_otp = await self.otp_repo.create_otp(
                user_id=otp.user_id,
                channel=request.channel,
                purpose=otp.purpose,
                destination_hash=otp.destination_hash,
                otp_hash=otp_hash,
                max_attempts=otp.max_attempts,
            )

            await self.audit_repo.log_action(
                action="otp_resent",
                resource_type="otp",
                resource_id=new_otp.id,
                actor_user_id=user_id or otp.user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={
                    "original_request_id": request.request_id,
                    "channel": enum_value(request.channel),
                },
            )

            expires_in_seconds = (
                settings.otp_expire_minutes * 60
            )

            return (
                OTPResendResponse(
                    request_id=new_otp.id,
                    channel=enum_value(request.channel),
                    expires_in_seconds=expires_in_seconds,
                    message="OTP resent to different channel",
                    otp_code=otp_code if settings.debug else None,
                ),
                otp_code,
            )

        else:
            # Reset attempts and return same OTP request
            otp.attempt_count = 0
            await self.db.flush()

            # Generate new OTP code for delivery
            otp_code = generate_otp()
            otp_hash = hash_otp(otp_code)

            # Update hash
            otp.otp_hash = otp_hash
            otp.used_at = None  # Clear used flag to reactivate
            await self.db.flush()

            await self.audit_repo.log_action(
                action="otp_resent",
                resource_type="otp",
                resource_id=otp.id,
                actor_user_id=user_id or otp.user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"channel": enum_value(otp.channel)},
            )

            expires_in_seconds = int(
                (otp.expires_at - datetime.now(UTC)).total_seconds()
            )

            return (
                OTPResendResponse(
                    request_id=otp.id,
                    channel=enum_value(otp.channel),
                    expires_in_seconds=expires_in_seconds,
                    message="OTP code regenerated",
                    otp_code=otp_code if settings.debug else None,
                ),
                otp_code,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Delivery Hooks
    # ─────────────────────────────────────────────────────────────────────────

    async def send_otp(
        self,
        request_id: str,
        otp_code: str,
    ) -> bool:
        """
        Send OTP via configured delivery system.

        This is an orchestration hook - actual delivery is delegated
        to external systems (SMS gateway, email service, etc).
        """
        otp = await self.otp_repo.get_by_id(request_id)

        if not otp:
            await logger.awarning("otp_send_request_not_found", request_id=request_id)
            return False

        # TODO: Delegate to external delivery system
        # - If SMS: call SMS gateway
        # - If EMAIL: queue email job
        # - If development: log to console

        await logger.ainfo(
            "otp_delivery_hook",
            request_id=request_id,
            channel=enum_value(otp.channel),
            purpose=enum_value(otp.purpose),
            message="Delivery delegation hook (implement external integration)",
        )

        return True
