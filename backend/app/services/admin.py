"""
Admin service for password reset approvals, audit logs, and user management.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    InvalidStateTransitionError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.core.security import generate_password
from app.db.enums import ApprovalStatus, IncidentStatus, UserStatus
from app.db.models import AuditLog, PasswordResetRequest, User
from app.repositories import (
    AuditLogRepository,
    PasswordResetRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.repositories.admin import (
    AdminIncidentRepository,
    AdminRepository,
    AdminUserRepository,
)
from app.schemas.admin import (
    AuditLogResponse,
    PasswordResetApproval,
    PasswordResetRequestResponse,
)

logger = structlog.get_logger()


class AdminService:
    """Service for admin operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.admin_repo = AdminRepository(db)
        self.admin_incident_repo = AdminIncidentRepository(db)
        self.admin_user_repo = AdminUserRepository(db)
        self.password_reset_repo = PasswordResetRepository(db)
        self.token_repo = RefreshTokenRepository(db)
        self.audit_repo = AuditLogRepository(db)

    # Password reset management
    async def get_pending_password_resets(
        self,
        region_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[PasswordResetRequestResponse], int]:
        """Get pending password reset requests for a region."""
        requests, total = await self.password_reset_repo.get_pending_for_region(
            region_id=region_id,
            skip=skip,
            limit=limit,
        )

        return [PasswordResetRequestResponse.model_validate(r) for r in requests], total

    async def approve_password_reset(
        self,
        request_id: str,
        admin_id: str,
        approval: PasswordResetApproval,
    ) -> PasswordResetRequest:
        """Approve a password reset request."""
        request = await self.password_reset_repo.get_by_id(request_id)
        if not request:
            raise UserNotFoundError("Password reset request not found")

        if request.admin_approval_status != ApprovalStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Request is already {request.admin_approval_status}"
            )

        if request.expires_at < datetime.now(UTC):
            raise InvalidStateTransitionError("Request has expired")

        if approval.approved:
            request = await self.password_reset_repo.approve(
                request_id=request_id,
                approved_by_id=admin_id,
                note=approval.note,
            )
            action = "password_reset_approved"
        else:
            if not approval.rejection_reason:
                raise ValueError("Rejection reason is required")

            request = await self.password_reset_repo.reject(
                request_id=request_id,
                rejected_by_id=admin_id,
                reason=approval.rejection_reason,
            )
            action = "password_reset_rejected"

        await self.audit_repo.log_action(
            action=action,
            resource_type="password_reset",
            resource_id=request_id,
            actor_user_id=admin_id,
            metadata={
                "user_id": request.user_id,
                "approved": approval.approved,
                "note": approval.note,
                "rejection_reason": approval.rejection_reason,
            },
        )

        await logger.ainfo(
            action,
            request_id=request_id,
            admin_id=admin_id,
            user_id=request.user_id,
        )

        return request

    # User management
    async def suspend_user(
        self,
        user_id: str,
        admin_id: str,
        reason: str,
    ) -> User:
        """Suspend a user account."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        if user.is_suspended:
            raise InvalidStateTransitionError("User is already suspended")

        user = await self.user_repo.suspend_user(user_id, reason)

        # Revoke all tokens
        await self.token_repo.revoke_all_for_user(user_id)

        await self.audit_repo.log_action(
            action="user_suspended",
            resource_type="user",
            resource_id=user_id,
            actor_user_id=admin_id,
            metadata={"reason": reason},
        )

        await logger.ainfo(
            "user_suspended",
            user_id=user_id,
            admin_id=admin_id,
            reason=reason,
        )

        return user

    async def activate_user(
        self,
        user_id: str,
        admin_id: str,
    ) -> User:
        """Activate/unsuspend a user account."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        if not user.is_suspended:
            raise InvalidStateTransitionError("User is not suspended")

        user = await self.user_repo.activate_user(user_id)

        await self.audit_repo.log_action(
            action="user_activated",
            resource_type="user",
            resource_id=user_id,
            actor_user_id=admin_id,
        )

        await logger.ainfo(
            "user_activated",
            user_id=user_id,
            admin_id=admin_id,
        )

        return user

    async def get_users(
        self,
        organization_id: str,
        region_id: str | None = None,
        is_active: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[User], int]:
        """Get users with filters."""
        from sqlalchemy import and_, func, select

        filters = [User.organization_id == organization_id]

        if region_id:
            filters.append(User.region_id == region_id)
        if is_active is not None:
            filters.append(User.is_active == is_active)

        query = (
            select(User)
            .where(and_(*filters))
            .order_by(User.created_at.desc())
        )

        # Count
        count_query = select(func.count(User.id)).where(and_(*filters))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return users, total

    # Audit logs
    async def search_audit_logs(
        self,
        actor_user_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[AuditLogResponse], int]:
        """Search audit logs."""
        logs, total = await self.audit_repo.search_logs(
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )

        return [AuditLogResponse.model_validate(log) for log in logs], total

    async def log_action(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor_user_id: str | None = None,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        metadata: dict | None = None,
        description: str | None = None,
        success: bool = True,
        error_message: str | None = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        return await self.audit_repo.log_action(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_user_id=actor_user_id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata=metadata,
            description=description,
            success=success,
            error_message=error_message,
        )

    # User creation and activation
    async def create_user(
        self,
        full_name: str,
        username: str,
        organization_id: str,
        region_id: str,
        admin_id: str,
        email: str | None = None,
        phone: str | None = None,
        roles: list[str] | None = None,
    ) -> User:
        """Create a new user via admin."""
        # Generate temporary password
        temp_password = generate_password(16)

        # Create user
        user = await self.user_repo.create_user(
            full_name=full_name,
            username=username,
            password=temp_password,
            organization_id=organization_id,
            region_id=region_id,
            email=email,
            phone=phone,
            created_by_id=admin_id,
            roles=roles,
        )

        # Log action
        await self.audit_repo.log_action(
            action="user_created",
            resource_type="user",
            resource_id=user.id,
            actor_user_id=admin_id,
            metadata={
                "full_name": full_name,
                "username": username,
                "roles": roles,
            },
        )

        await logger.ainfo(
            "user_created",
            user_id=user.id,
            created_by=admin_id,
        )

        return user

    async def assign_role(
        self,
        user_id: str,
        role_id: str,
        admin_id: str,
    ) -> None:
        """Assign a role to user."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        await self.admin_user_repo.assign_role(
            user_id=user_id,
            role_id=role_id,
            assigned_by_id=admin_id,
        )

        await self.audit_repo.log_action(
            action="role_assigned",
            resource_type="user",
            resource_id=user_id,
            actor_user_id=admin_id,
            metadata={"role_id": role_id},
        )

        await logger.ainfo(
            "role_assigned",
            user_id=user_id,
            role_id=role_id,
            assigned_by=admin_id,
        )

    async def revoke_role(
        self,
        user_id: str,
        role_id: str,
        admin_id: str,
    ) -> None:
        """Revoke a role from user."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        await self.admin_user_repo.revoke_role(
            user_id=user_id,
            role_id=role_id,
        )

        await self.audit_repo.log_action(
            action="role_revoked",
            resource_type="user",
            resource_id=user_id,
            actor_user_id=admin_id,
            metadata={"role_id": role_id},
        )

        await logger.ainfo(
            "role_revoked",
            user_id=user_id,
            role_id=role_id,
            revoked_by=admin_id,
        )

    # Incident management
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
    ) -> tuple[list, int]:
        """Search incidents with advanced filters."""
        incidents, total = await self.admin_incident_repo.search_incidents(
            organization_id=organization_id,
            region_id=region_id,
            status=status,
            severity=severity,
            created_by_id=created_by_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )

        return incidents, total

    async def get_incident_statistics(
        self,
        organization_id: str,
        region_id: str | None = None,
        days: int = 30,
    ) -> dict:
        """Get incident statistics."""
        date_from = datetime.now() - timedelta(days=days)

        return await self.admin_incident_repo.get_incident_statistics(
            organization_id=organization_id,
            region_id=region_id,
            date_from=date_from,
        )

    # User search and filtering
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
        """Search users with advanced filters."""
        return await self.admin_user_repo.search_users(
            organization_id=organization_id,
            region_id=region_id,
            status=status,
            is_active=is_active,
            is_suspended=is_suspended,
            has_role=has_role,
            created_by_id=created_by_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )
