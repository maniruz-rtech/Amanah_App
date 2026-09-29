"""
OTP repository for OTP request and verification operations.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.base import generate_ulid
from app.db.enums import OTPChannel, OTPPurpose
from app.db.models import OTPRequest
from app.repositories.base import BaseRepository


class OTPRepository(BaseRepository[OTPRequest]):
    """Repository for OTP request operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(OTPRequest, db)

    async def create_otp(
        self,
        user_id: str | None,
        channel: OTPChannel,
        purpose: OTPPurpose,
        destination_hash: str,
        otp_hash: str,
        max_attempts: int | None = None,
    ) -> OTPRequest:
        """Create a new OTP request."""
        if max_attempts is None:
            max_attempts = settings.otp_max_attempts

        otp = OTPRequest(
            id=generate_ulid("otp_"),
            user_id=user_id,
            channel=channel,
            purpose=purpose,
            destination_hash=destination_hash,
            otp_hash=otp_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.otp_expire_minutes),
            max_attempts=max_attempts,
        )
        self.db.add(otp)
        await self.db.flush()
        await self.db.refresh(otp)
        return otp

    async def get_valid_otp(self, request_id: str) -> OTPRequest | None:
        """Get valid (not expired, not used, attempts remaining) OTP."""
        result = await self.db.execute(
            select(OTPRequest).where(
                and_(
                    OTPRequest.id == request_id,
                    OTPRequest.expires_at > datetime.now(UTC),
                    OTPRequest.used_at.is_(None),
                    OTPRequest.attempt_count < OTPRequest.max_attempts,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_valid_for_user(
        self,
        user_id: str,
        purpose: OTPPurpose,
        channel: OTPChannel,
    ) -> OTPRequest | None:
        """Newest OTP of this purpose/channel for the user that can still be verified."""
        result = await self.db.execute(
            select(OTPRequest)
            .where(
                and_(
                    OTPRequest.user_id == user_id,
                    OTPRequest.purpose == purpose,
                    OTPRequest.channel == channel,
                    OTPRequest.expires_at > datetime.now(UTC),
                    OTPRequest.used_at.is_(None),
                    OTPRequest.attempt_count < OTPRequest.max_attempts,
                )
            )
            .order_by(OTPRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_details(self, request_id: str) -> OTPRequest | None:
        """Get OTP with user relation loaded."""
        result = await self.db.execute(
            select(OTPRequest)
            .options(selectinload(OTPRequest.user))
            .where(OTPRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, request_id: str) -> OTPRequest | None:
        """Mark OTP as used (one-time use enforcement)."""
        otp = await self.get_by_id(request_id)
        if otp:
            otp.used_at = datetime.now(UTC)
            await self.db.flush()
        return otp

    async def increment_attempts(self, request_id: str) -> OTPRequest | None:
        """Increment failed attempt count."""
        otp = await self.get_by_id(request_id)
        if otp:
            otp.attempt_count += 1
            await self.db.flush()
        return otp

    async def get_user_otp_requests(
        self,
        user_id: str,
        purpose: OTPPurpose | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[OTPRequest], int]:
        """Get OTP history for a user."""
        base_filter = OTPRequest.user_id == user_id

        if purpose:
            base_filter = and_(base_filter, OTPRequest.purpose == purpose)

        # Count
        count_result = await self.db.execute(
            select(func.count(OTPRequest.id)).where(base_filter)
        )
        total = count_result.scalar() or 0

        # Get paginated results
        query = (
            select(OTPRequest)
            .where(base_filter)
            .order_by(OTPRequest.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        requests = list(result.scalars().all())

        return requests, total

    async def get_user_active_requests(
        self,
        user_id: str,
    ) -> list[OTPRequest]:
        """Get user's active (not expired, not used) OTP requests."""
        result = await self.db.execute(
            select(OTPRequest).where(
                and_(
                    OTPRequest.user_id == user_id,
                    OTPRequest.expires_at > datetime.now(UTC),
                    OTPRequest.used_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_destination_hash(
        self,
        destination_hash: str,
        purpose: OTPPurpose,
        channel: OTPChannel,
    ) -> OTPRequest | None:
        """Get OTP by destination hash (for duplicate request prevention)."""
        result = await self.db.execute(
            select(OTPRequest).where(
                and_(
                    OTPRequest.destination_hash == destination_hash,
                    OTPRequest.purpose == purpose,
                    OTPRequest.channel == channel,
                    OTPRequest.expires_at > datetime.now(UTC),
                    OTPRequest.used_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def attempt_verification(
        self,
        request_id: str,
    ) -> tuple[bool, int]:
        """Track verification attempt and return (is_allowed, attempts_remaining)."""
        otp = await self.get_by_id(request_id)

        if not otp:
            return False, 0

        # Check if expired
        if otp.is_expired:
            return False, 0

        # Check if already used
        if otp.is_used:
            return False, 0

        # Check if max attempts exceeded
        if otp.is_max_attempts_exceeded:
            return False, 0

        attempts_remaining = otp.max_attempts - otp.attempt_count

        return True, attempts_remaining

    async def cleanup_expired(self) -> int:
        """Delete expired OTP requests (older than configured expiry)."""
        result = await self.db.execute(
            delete(OTPRequest).execution_options(synchronize_session="fetch").where(
                OTPRequest.expires_at < datetime.now(UTC) - timedelta(hours=1)
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    async def cleanup_used(self, older_than_hours: int = 24) -> int:
        """Delete used/verified OTP requests older than specified hours."""
        cutoff_time = datetime.now(UTC) - timedelta(hours=older_than_hours)

        result = await self.db.execute(
            delete(OTPRequest).execution_options(synchronize_session="fetch").where(
                and_(
                    OTPRequest.used_at.is_not(None),
                    OTPRequest.used_at < cutoff_time,
                )
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore
