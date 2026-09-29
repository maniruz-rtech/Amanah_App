"""
Auth repository for tokens, OTP, and password reset.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import generate_ulid
from app.db.enums import ApprovalStatus, OTPChannel, OTPPurpose
from app.db.models import OTPRequest, PasswordResetRequest, RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Repository for RefreshToken operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(RefreshToken, db)

    async def create_token(
        self,
        user_id: str,
        jti: str,
        device_id: str | None = None,
        expires_days: int | None = None,
    ) -> RefreshToken:
        """Create a new refresh token record."""
        if expires_days is None:
            expires_days = settings.jwt_refresh_token_expire_days

        token = RefreshToken(
            id=generate_ulid("rtok_"),
            user_id=user_id,
            device_id=device_id,
            jti=jti,
            expires_at=datetime.now(UTC) + timedelta(days=expires_days),
            is_revoked=False,
        )
        self.db.add(token)
        await self.db.flush()
        await self.db.refresh(token)
        return token

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        """Get token by JTI."""
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        return result.scalar_one_or_none()

    async def revoke_token(self, jti: str) -> RefreshToken | None:
        """Revoke a token by JTI."""
        token = await self.get_by_jti(jti)
        if token:
            token.is_revoked = True
            token.revoked_at = datetime.now(UTC)
            await self.db.flush()
        return token

    async def rotate_token(
        self,
        old_jti: str,
        new_jti: str,
        user_id: str,
        device_id: str | None = None,
    ) -> RefreshToken | None:
        """Rotate token: revoke old, create new."""
        # Revoke old token
        old_token = await self.get_by_jti(old_jti)
        if not old_token or old_token.is_revoked:
            return None

        old_token.is_revoked = True
        old_token.revoked_at = datetime.now(UTC)
        old_token.replaced_by_jti = new_jti

        # Create new token
        new_token = await self.create_token(
            user_id=user_id,
            jti=new_jti,
            device_id=device_id,
        )

        await self.db.flush()
        return new_token

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all tokens for a user."""
        result = await self.db.execute(
            update(RefreshToken).execution_options(synchronize_session="fetch")
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked == False,
                )
            )
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.flush()
        return result.rowcount  # type: ignore


class OTPRepository(BaseRepository[OTPRequest]):
    """Repository for OTP operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(OTPRequest, db)

    async def create_otp(
        self,
        user_id: str | None,
        channel: OTPChannel,
        purpose: OTPPurpose,
        destination_hash: str,
        otp_hash: str,
    ) -> OTPRequest:
        """Create an OTP request."""
        otp = OTPRequest(
            id=generate_ulid("otp_"),
            user_id=user_id,
            channel=channel,
            purpose=purpose,
            destination_hash=destination_hash,
            otp_hash=otp_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.otp_expire_minutes),
        )
        self.db.add(otp)
        await self.db.flush()
        await self.db.refresh(otp)
        return otp

    async def get_valid_otp(self, request_id: str) -> OTPRequest | None:
        """Get valid (not expired, not used) OTP."""
        result = await self.db.execute(
            select(OTPRequest).where(
                and_(
                    OTPRequest.id == request_id,
                    OTPRequest.expires_at > datetime.now(UTC),
                    OTPRequest.used_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, request_id: str) -> OTPRequest | None:
        """Mark OTP as used."""
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


class PasswordResetRepository(BaseRepository[PasswordResetRequest]):
    """Repository for password reset operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(PasswordResetRequest, db)

    async def create_request(self, user_id: str) -> PasswordResetRequest:
        """Create a new password reset request."""
        now = datetime.now(UTC)

        request = PasswordResetRequest(
            id=generate_ulid("prr_"),
            user_id=user_id,
            requested_at=now,
            expires_at=now + timedelta(hours=24),
            admin_approval_status=ApprovalStatus.PENDING,
        )
        self.db.add(request)
        await self.db.flush()
        await self.db.refresh(request)
        return request

    async def mark_phone_verified(self, request_id: str) -> PasswordResetRequest | None:
        """Mark phone as verified."""
        request = await self.get_by_id(request_id)
        if request:
            request.phone_verified_at = datetime.now(UTC)
            await self.db.flush()
        return request

    async def mark_email_verified(self, request_id: str) -> PasswordResetRequest | None:
        """Mark email as verified."""
        request = await self.get_by_id(request_id)
        if request:
            request.email_verified_at = datetime.now(UTC)
            await self.db.flush()
        return request

    async def approve(
        self,
        request_id: str,
        approved_by_id: str,
        note: str | None = None,
    ) -> PasswordResetRequest | None:
        """Approve password reset request."""
        request = await self.get_by_id(request_id)
        if request:
            request.admin_approval_status = ApprovalStatus.APPROVED
            request.approved_by_id = approved_by_id
            request.approved_at = datetime.now(UTC)
            await self.db.flush()
        return request

    async def reject(
        self,
        request_id: str,
        rejected_by_id: str,
        reason: str,
    ) -> PasswordResetRequest | None:
        """Reject password reset request."""
        request = await self.get_by_id(request_id)
        if request:
            request.admin_approval_status = ApprovalStatus.REJECTED
            request.approved_by_id = rejected_by_id
            request.approved_at = datetime.now(UTC)
            request.rejection_reason = reason
            await self.db.flush()
        return request

    async def complete(self, request_id: str) -> PasswordResetRequest | None:
        """Mark request as completed."""
        request = await self.get_by_id(request_id)
        if request:
            request.completed_at = datetime.now(UTC)
            await self.db.flush()
        return request

    async def get_pending_for_region(
        self,
        region_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[PasswordResetRequest], int]:
        """Get pending requests for a region."""
        from sqlalchemy import func

        from app.db.models import User

        base_filter = and_(
            PasswordResetRequest.admin_approval_status == ApprovalStatus.PENDING,
            PasswordResetRequest.expires_at > datetime.now(UTC),
        )

        # Join with User to filter by region
        query = (
            select(PasswordResetRequest)
            .join(User, User.id == PasswordResetRequest.user_id)
            .where(and_(base_filter, User.region_id == region_id))
            .order_by(PasswordResetRequest.requested_at.desc())
        )

        # Count
        count_query = (
            select(func.count(PasswordResetRequest.id))
            .join(User, User.id == PasswordResetRequest.user_id)
            .where(and_(base_filter, User.region_id == region_id))
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        requests = list(result.scalars().all())

        return requests, total
