"""
Password reset repository for password reset request operations.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.base import generate_ulid
from app.db.enums import ApprovalStatus
from app.db.models import PasswordResetRequest, User
from app.repositories.base import BaseRepository


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

    async def get_by_id_with_relations(
        self, request_id: str
    ) -> PasswordResetRequest | None:
        """Get password reset request with user loaded."""
        result = await self.db.execute(
            select(PasswordResetRequest)
            .options(selectinload(PasswordResetRequest.user))
            .where(PasswordResetRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def mark_phone_verified(self, request_id: str) -> PasswordResetRequest | None:
        """Mark phone as verified for OTP."""
        request = await self.get_by_id(request_id)
        if request:
            request.phone_verified_at = datetime.now(UTC)
            await self.db.flush()
        return request

    async def mark_email_verified(self, request_id: str) -> PasswordResetRequest | None:
        """Mark email as verified for OTP."""
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
        """Approve password reset request (admin action)."""
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
        """Reject password reset request (admin action)."""
        request = await self.get_by_id(request_id)
        if request:
            request.admin_approval_status = ApprovalStatus.REJECTED
            request.approved_by_id = rejected_by_id
            request.approved_at = datetime.now(UTC)
            request.rejection_reason = reason
            await self.db.flush()
        return request

    async def complete(self, request_id: str) -> PasswordResetRequest | None:
        """Mark reset request as completed (one-time use enforcement)."""
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
        """Get pending password reset requests for admin approval in a region."""
        base_filter = and_(
            PasswordResetRequest.admin_approval_status == ApprovalStatus.PENDING,
            PasswordResetRequest.expires_at > datetime.now(UTC),
        )

        # Join with User to filter by region
        query = (
            select(PasswordResetRequest)
            .options(selectinload(PasswordResetRequest.user))
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

    async def get_user_requests(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[PasswordResetRequest], int]:
        """Get password reset request history for a user."""
        # Count
        count_result = await self.db.execute(
            select(func.count(PasswordResetRequest.id)).where(
                PasswordResetRequest.user_id == user_id
            )
        )
        total = count_result.scalar() or 0

        # Get paginated requests
        query = (
            select(PasswordResetRequest)
            .where(PasswordResetRequest.user_id == user_id)
            .order_by(PasswordResetRequest.requested_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        requests = list(result.scalars().all())

        return requests, total

    async def get_active_request(self, user_id: str) -> PasswordResetRequest | None:
        """Get user's active (non-expired, non-completed) password reset request."""
        result = await self.db.execute(
            select(PasswordResetRequest).where(
                and_(
                    PasswordResetRequest.user_id == user_id,
                    PasswordResetRequest.expires_at > datetime.now(UTC),
                    PasswordResetRequest.completed_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_for_approval(
        self,
        request_id: str,
    ) -> PasswordResetRequest | None:
        """Get password reset request that's pending admin approval."""
        result = await self.db.execute(
            select(PasswordResetRequest).where(
                and_(
                    PasswordResetRequest.id == request_id,
                    PasswordResetRequest.admin_approval_status
                    == ApprovalStatus.PENDING,
                    PasswordResetRequest.expires_at > datetime.now(UTC),
                    PasswordResetRequest.completed_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def cleanup_expired(self) -> int:
        """Delete expired password reset requests (older than 24 hours)."""
        result = await self.db.execute(
            delete(PasswordResetRequest).execution_options(synchronize_session="fetch").where(
                PasswordResetRequest.expires_at < datetime.now(UTC)
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore
