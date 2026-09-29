"""
Admin-specific repositories for user, incident, and approval management.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.enums import (
    ApprovalRequestType,
    ApprovalStatus,
    IncidentSeverity,
    IncidentStatus,
    UserStatus,
    enum_value,
)
from app.db.models import (
    AdminApproval,
    Incident,
    IncidentAssignment,
    User,
    UserRole,
)
from app.repositories.base import BaseRepository


class AdminRepository(BaseRepository[AdminApproval]):
    """Repository for AdminApproval operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(AdminApproval, db)

    async def get_pending_user_activations(
        self,
        organization_id: str,
        region_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AdminApproval], int]:
        """Get pending user activation approvals."""
        filters = [
            AdminApproval.request_type == ApprovalRequestType.USER_ACTIVATION,
            AdminApproval.status == ApprovalStatus.PENDING,
        ]

        if region_id:
            # Join with user to filter by region
            filters.append(
                AdminApproval.requested_by_id.in_(
                    select(User.id).where(User.region_id == region_id)
                )
            )

        query = (
            select(AdminApproval)
            .where(and_(*filters))
            .order_by(AdminApproval.created_at.asc())
        )

        # Count
        count_query = select(func.count(AdminApproval.id)).where(and_(*filters))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        approvals = list(result.scalars().all())

        return approvals, total

    async def create_user_activation_request(
        self,
        user_id: str,
    ) -> AdminApproval:
        """Create a user activation approval request."""
        from app.db.base import generate_ulid

        approval = AdminApproval(
            id=generate_ulid("aprv_"),
            request_type=ApprovalRequestType.USER_ACTIVATION,
            request_ref_id=user_id,
            requested_by_id=user_id,
            status=ApprovalStatus.PENDING,
        )
        self.db.add(approval)
        await self.db.flush()
        await self.db.refresh(approval)
        return approval

    async def approve_user_activation(
        self,
        approval_id: str,
        approved_by_id: str,
        notes: str | None = None,
    ) -> AdminApproval:
        """Approve user activation request."""
        approval = await self.get_by_id(approval_id)
        if approval:
            approval.status = ApprovalStatus.APPROVED
            approval.reviewed_by_id = approved_by_id
            approval.reviewed_at = datetime.now(UTC)
            approval.notes = notes
            await self.db.flush()
            await self.db.refresh(approval)

        return approval

    async def reject_user_activation(
        self,
        approval_id: str,
        rejected_by_id: str,
        reason: str,
    ) -> AdminApproval:
        """Reject user activation request."""
        approval = await self.get_by_id(approval_id)
        if approval:
            approval.status = ApprovalStatus.REJECTED
            approval.reviewed_by_id = rejected_by_id
            approval.reviewed_at = datetime.now(UTC)
            approval.notes = reason
            await self.db.flush()
            await self.db.refresh(approval)

        return approval


class AdminIncidentRepository(BaseRepository[Incident]):
    """Repository for admin incident search and filtering."""

    def __init__(self, db: AsyncSession):
        super().__init__(Incident, db)

    async def search_incidents(
        self,
        organization_id: str,
        region_id: str | None = None,
        status: IncidentStatus | None = None,
        severity: str | None = None,
        created_by_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Incident], int]:
        """Search incidents with advanced filtering."""
        filters = [Incident.organization_id == organization_id]

        if region_id:
            filters.append(Incident.region_id == region_id)

        if status:
            filters.append(Incident.status == status)

        if severity:
            filters.append(Incident.severity == IncidentSeverity(enum_value(severity)))

        if created_by_id:
            filters.append(Incident.created_by_id == created_by_id)

        if date_from:
            filters.append(Incident.created_at >= date_from)

        if date_to:
            filters.append(Incident.created_at <= date_to)

        query = (
            select(Incident)
            .options(
                selectinload(Incident.created_by),
                selectinload(Incident.region),
                selectinload(Incident.assignments).selectinload(
                    IncidentAssignment.responder
                ),
            )
            .where(and_(*filters))
            .order_by(Incident.created_at.desc())
        )

        # Count
        count_query = select(func.count(Incident.id)).where(and_(*filters))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        incidents = list(result.scalars().all())

        return incidents, total

    async def get_incident_statistics(
        self,
        organization_id: str,
        region_id: str | None = None,
        date_from: datetime | None = None,
    ) -> dict[str, Any]:
        """Get incident statistics for organization/region."""
        filters = [Incident.organization_id == organization_id]

        if region_id:
            filters.append(Incident.region_id == region_id)

        if date_from:
            filters.append(Incident.created_at >= date_from)

        # Count by status
        status_counts = {}
        for status in IncidentStatus:
            result = await self.db.execute(
                select(func.count(Incident.id)).where(
                    and_(Incident.status == status, *filters)
                )
            )
            status_counts[status.value] = result.scalar() or 0

        # Total count
        result = await self.db.execute(
            select(func.count(Incident.id)).where(and_(*filters))
        )
        total_count = result.scalar() or 0

        # Average response time
        result = await self.db.execute(
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        IncidentAssignment.accepted_at - Incident.created_at,
                    )
                )
            ).where(
                and_(
                    IncidentAssignment.accepted_at.isnot(None),
                    *filters,
                )
            )
        )
        avg_response_time = result.scalar() or 0

        return {
            "total_incidents": total_count,
            "by_status": status_counts,
            "avg_response_time_seconds": int(avg_response_time),
        }


class AdminUserRepository(BaseRepository[User]):
    """Repository for admin user management."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def search_users(
        self,
        organization_id: str,
        region_id: str | None = None,
        status: UserStatus | None = None,
        is_active: bool | None = None,
        is_suspended: bool | None = None,
        has_role: str | None = None,
        created_by_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[User], int]:
        """Search users with advanced filtering."""
        filters = [User.organization_id == organization_id]

        if region_id:
            filters.append(User.region_id == region_id)

        if status:
            filters.append(User.status == status)

        if is_active is not None:
            filters.append(User.is_active == is_active)

        if is_suspended is not None:
            filters.append(User.is_suspended == is_suspended)

        if created_by_id:
            filters.append(User.created_by_id == created_by_id)

        if date_from:
            filters.append(User.created_at >= date_from)

        if date_to:
            filters.append(User.created_at <= date_to)

        query = (
            select(User)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .where(and_(*filters))
            .order_by(User.created_at.desc())
        )

        # Filter by role if specified
        if has_role:
            role_filter = select(User.id).join(UserRole).filter(
                UserRole.role_id == has_role
            )
            query = query.where(User.id.in_(role_filter))

        # Count
        count_query = select(func.count(User.id)).where(and_(*filters))
        if has_role:
            count_query = count_query.where(User.id.in_(role_filter))

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return users, total

    async def assign_role(
        self,
        user_id: str,
        role_id: str,
        assigned_by_id: str,
    ) -> None:
        """Assign a role to user."""
        from app.db.base import generate_ulid

        # Check if already assigned
        result = await self.db.execute(
            select(UserRole).where(
                and_(
                    UserRole.user_id == user_id,
                    UserRole.role_id == role_id,
                )
            )
        )
        if result.scalar_one_or_none():
            return  # Already assigned

        user_role = UserRole(
            id=generate_ulid("urol_"),
            user_id=user_id,
            role_id=role_id,
            assigned_by_id=assigned_by_id,
            assigned_at=datetime.now(UTC),
        )
        self.db.add(user_role)
        await self.db.flush()

    async def revoke_role(
        self,
        user_id: str,
        role_id: str,
    ) -> None:
        """Revoke a role from user."""
        await self.db.execute(
            delete(UserRole).execution_options(synchronize_session="fetch").where(
                and_(
                    UserRole.user_id == user_id,
                    UserRole.role_id == role_id,
                )
            )
        )
        await self.db.flush()
