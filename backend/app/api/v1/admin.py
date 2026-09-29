"""
Admin API endpoints for user management, password resets, and audit logs.
"""

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    AuthenticatedUser,
    DBSession,
    require_any_permission,
    require_permission,
)
from app.core.admin_permissions import Permission, ScopeValidator
from app.core.exceptions import (
    InvalidStateTransitionError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.core.permissions import has_permission
from app.db.enums import IncidentStatus, UserStatus
from app.db.models import User
from app.schemas.admin import (
    AuditLogResponse,
    IncidentAdminResponse,
    PasswordResetApproval,
    PasswordResetRequestResponse,
    UserAdminResponse,
    UserCreateRequest,
    UserSuspendRequest,
)
from app.schemas.common import PaginatedResponse
from app.services import AdminService

logger = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["Admin"])


def _build_paginated_response(items: list, total: int, skip: int, limit: int) -> PaginatedResponse:
    """Build a schema-compliant paginated response from offset pagination params."""
    page = (skip // limit) + 1
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=limit,
    )


# Password reset management
@router.get(
    "/password-resets",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.APPROVE_RESETS))],
)
async def get_pending_password_resets(
    current_user: AuthenticatedUser,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    Get pending password reset requests for admin's region.

    Requires APPROVE_PASSWORD_RESETS permission.
    """
    if not current_user.region_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to a region",
        )

    admin_service = AdminService(db)
    requests, total = await admin_service.get_pending_password_resets(
        region_id=current_user.region_id,
        skip=skip,
        limit=limit,
    )

    return _build_paginated_response(requests, total, skip, limit)


@router.post(
    "/password-resets/{request_id}/approve",
    response_model=PasswordResetRequestResponse,
    dependencies=[Depends(require_permission(Permission.APPROVE_RESETS))],
)
async def approve_password_reset(
    request_id: str,
    approval: PasswordResetApproval,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Approve or reject a password reset request.

    Requires APPROVE_PASSWORD_RESETS permission.
    """
    admin_service = AdminService(db)

    try:
        request = await admin_service.approve_password_reset(
            request_id=request_id,
            admin_id=current_user.user_id,
            approval=approval,
        )
        return PasswordResetRequestResponse.model_validate(request)

    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# User management
@router.get(
    "/users",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.CREATE_USERS))],
)
async def get_users(
    current_user: AuthenticatedUser,
    db: DBSession,
    region_id: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    Get users in organization.

    Regional admins can only see users in their region.
    Super admins can filter by region.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to an organization",
        )

    # Regional admins can only see their region
    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        region_id = current_user.region_id

    admin_service = AdminService(db)
    users, total = await admin_service.get_users(
        organization_id=current_user.organization_id,
        region_id=region_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )

    return _build_paginated_response(
        [UserAdminResponse.model_validate(u) for u in users],
        total,
        skip,
        limit,
    )


@router.post(
    "/users/{user_id}/suspend",
    response_model=UserAdminResponse,
    dependencies=[Depends(require_permission(Permission.CREATE_USERS))],
)
async def suspend_user(
    user_id: str,
    request: UserSuspendRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Suspend a user account.

    Revokes all tokens and prevents login.
    """
    # Cannot suspend yourself
    if user_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend your own account",
        )

    admin_service = AdminService(db)

    try:
        user = await admin_service.suspend_user(
            user_id=user_id,
            admin_id=current_user.user_id,
            reason=request.reason,
        )
        return UserAdminResponse.model_validate(user)

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/users/{user_id}/activate",
    response_model=UserAdminResponse,
    dependencies=[Depends(require_permission(Permission.CREATE_USERS))],
)
async def activate_user(
    user_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Activate/unsuspend a user account."""
    admin_service = AdminService(db)

    try:
        user = await admin_service.activate_user(
            user_id=user_id,
            admin_id=current_user.user_id,
        )
        return UserAdminResponse.model_validate(user)

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Audit logs
@router.get(
    "/audit-logs",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.VIEW_REGIONAL_AUDITS))],
)
async def search_audit_logs(
    current_user: AuthenticatedUser,
    db: DBSession,
    actor_user_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    resource_id: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
):
    """
    Search audit logs with filters.

    Requires VIEW_AUDIT_LOGS permission.
    """
    admin_service = AdminService(db)

    logs, total = await admin_service.search_audit_logs(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )

    return _build_paginated_response(logs, total, skip, limit)


# ─────────────────────────────────────────────────────────────────────────────
# New Admin Endpoints
# ─────────────────────────────────────────────────────────────────────────────


# Incident management
@router.get(
    "/incidents",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.VIEW_REGIONAL_INCIDENTS))],
)
async def search_incidents(
    current_user: AuthenticatedUser,
    db: DBSession,
    region_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
    created_by_id: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    Search incidents with filters.

    Regional admins can only see incidents in their region.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to an organization",
        )

    # Regional admins can only see their region
    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        region_id = current_user.region_id

    admin_service = AdminService(db)

    incidents, total = await admin_service.search_incidents(
        organization_id=current_user.organization_id,
        region_id=region_id,
        status=IncidentStatus(status) if status else None,
        severity=severity,
        created_by_id=created_by_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )

    return _build_paginated_response(
        [IncidentAdminResponse.model_validate(i) for i in incidents],
        total,
        skip,
        limit,
    )


@router.get(
    "/incidents/statistics",
    dependencies=[Depends(require_permission(Permission.VIEW_REGIONAL_INCIDENTS))],
)
async def get_incident_statistics(
    current_user: AuthenticatedUser,
    db: DBSession,
    region_id: Annotated[str | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
):
    """Get incident statistics for organization/region."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to an organization",
        )

    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        region_id = current_user.region_id

    admin_service = AdminService(db)
    stats = await admin_service.get_incident_statistics(
        organization_id=current_user.organization_id,
        region_id=region_id,
        days=days,
    )

    return stats


# User role management
@router.post(
    "/users/{user_id}/roles/{role_id}",
    dependencies=[Depends(require_permission(Permission.ASSIGN_ROLES))],
)
async def assign_role_to_user(
    user_id: str,
    role_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Assign a role to a user."""
    # Scope check
    from sqlalchemy import select

    user = await db.execute(
        select(User).where(User.id == user_id)
    )
    target_user = user.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not ScopeValidator.validate_user_scope(
        admin_user_id=current_user.user_id,
        admin_organization_id=current_user.organization_id,
        admin_region_id=current_user.region_id,
        admin_roles=current_user.roles,
        target_organization_id=target_user.organization_id,
        target_region_id=target_user.region_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users outside your scope",
        )

    admin_service = AdminService(db)

    try:
        await admin_service.assign_role(
            user_id=user_id,
            role_id=role_id,
            admin_id=current_user.user_id,
        )
        await db.commit()

        return {"success": True, "message": "Role assigned successfully"}

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.delete(
    "/users/{user_id}/roles/{role_id}",
    dependencies=[Depends(require_permission(Permission.ASSIGN_ROLES))],
)
async def revoke_role_from_user(
    user_id: str,
    role_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Revoke a role from a user."""
    from sqlalchemy import select

    user = await db.execute(
        select(User).where(User.id == user_id)
    )
    target_user = user.scalar_one_or_none()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not ScopeValidator.validate_user_scope(
        admin_user_id=current_user.user_id,
        admin_organization_id=current_user.organization_id,
        admin_region_id=current_user.region_id,
        admin_roles=current_user.roles,
        target_organization_id=target_user.organization_id,
        target_region_id=target_user.region_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users outside your scope",
        )

    admin_service = AdminService(db)

    try:
        await admin_service.revoke_role(
            user_id=user_id,
            role_id=role_id,
            admin_id=current_user.user_id,
        )
        await db.commit()

        return {"success": True, "message": "Role revoked successfully"}

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


# Advanced user search
@router.get(
    "/users/search",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.CREATE_USERS))],
)
async def search_users(
    current_user: AuthenticatedUser,
    db: DBSession,
    region_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    is_suspended: Annotated[bool | None, Query()] = None,
    has_role: Annotated[str | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    Advanced user search with filters.

    Regional admins can only search within their region.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to an organization",
        )

    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        region_id = current_user.region_id

    admin_service = AdminService(db)
    users, total = await admin_service.search_users(
        organization_id=current_user.organization_id,
        region_id=region_id,
        status=UserStatus(status) if status else None,
        is_active=is_active,
        is_suspended=is_suspended,
        has_role=has_role,
        skip=skip,
        limit=limit,
    )

    return _build_paginated_response(
        [UserAdminResponse.model_validate(u) for u in users],
        total,
        skip,
        limit,
    )


# ─────────────────────────────────────────────────────────────────────────────
# User Creation
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/users",
    response_model=UserAdminResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CREATE_USERS))],
)
async def create_user(
    request: UserCreateRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Create a new user.

    Admin creates user in their organization. User receives temporary password
    and must verify phone/email before full activation.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to an organization",
        )

    # Regional admins can only create users in their region
    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        if current_user.region_id != request.region_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create users outside your region",
            )

    admin_service = AdminService(db)

    try:
        user = await admin_service.create_user(
            full_name=request.full_name,
            username=request.username,
            organization_id=current_user.organization_id,
            region_id=request.region_id,
            admin_id=current_user.user_id,
            email=request.email,
            phone=request.phone,
            roles=request.roles,
        )
        await db.commit()

        return UserAdminResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Organization and Region Listing
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/organizations",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.VIEW_REGIONAL_INCIDENTS))],
)
async def list_organizations(
    current_user: AuthenticatedUser,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    List organizations.

    Super admins see all; regional admins see their own org only.
    """
    from sqlalchemy import and_, func, select
    from app.db.models import Organization
    from app.schemas.admin import OrganizationResponse

    filters = []
    
    # Non-super admins see only their organization
    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        if current_user.organization_id:
            filters.append(Organization.id == current_user.organization_id)

    query = select(Organization)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(Organization.name)

    # Count
    count_query = select(func.count(Organization.id))
    if filters:
        count_query = count_query.where(and_(*filters))
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    orgs = list(result.scalars().all())

    return _build_paginated_response(
        [OrganizationResponse.model_validate(o) for o in orgs],
        total,
        skip,
        limit,
    )


@router.get(
    "/regions",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_permission(Permission.VIEW_REGIONAL_INCIDENTS))],
)
async def list_regions(
    current_user: AuthenticatedUser,
    db: DBSession,
    organization_id: Annotated[str | None, Query()] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    List regions in organization.

    Super admins can filter by org; regional admins see their own org only.
    """
    from sqlalchemy import and_, func, select
    from app.db.models import Region
    from app.schemas.admin import RegionResponse

    # Default to current user's org
    org_id = organization_id or current_user.organization_id
    
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization ID required",
        )

    # Non-super admins can only see their own org
    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        if org_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot view regions outside your organization",
            )

    query = (
        select(Region)
        .where(Region.organization_id == org_id)
        .order_by(Region.name)
    )

    # Count
    count_query = select(func.count(Region.id)).where(Region.organization_id == org_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    regions = list(result.scalars().all())

    return _build_paginated_response(
        [RegionResponse.model_validate(r) for r in regions],
        total,
        skip,
        limit,
    )


@router.get(
    "/responders/statistics",
    dependencies=[Depends(require_permission(Permission.VIEW_REGIONAL_INCIDENTS))],
)
async def get_responder_statistics(
    current_user: AuthenticatedUser,
    db: DBSession,
    region_id: Annotated[str | None, Query()] = None,
):
    """
    Get responder availability statistics.
    """
    from sqlalchemy import and_, func, select
    from app.db.models import ResponderStatus, User

    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin must be assigned to an organization",
        )

    # Regional admins can only see their region
    if not has_permission(current_user.roles, Permission.VIEW_ALL_INCIDENTS):
        region_id = current_user.region_id

    # Base query joining responder_status with users in org
    base_filter = [
        User.organization_id == current_user.organization_id,
    ]
    if region_id:
        base_filter.append(User.region_id == region_id)

    # Count available responders
    available_query = (
        select(func.count(ResponderStatus.id))
        .join(User, ResponderStatus.user_id == User.id)
        .where(
            and_(
                *base_filter,
                ResponderStatus.is_available == True,
            )
        )
    )
    available_result = await db.execute(available_query)
    available_count = available_result.scalar() or 0

    # Count total responders
    total_query = (
        select(func.count(ResponderStatus.id))
        .join(User, ResponderStatus.user_id == User.id)
        .where(and_(*base_filter))
    )
    total_result = await db.execute(total_query)
    total_count = total_result.scalar() or 0

    # Count responders with active incidents
    busy_query = (
        select(func.count(ResponderStatus.id))
        .join(User, ResponderStatus.user_id == User.id)
        .where(
            and_(
                *base_filter,
                ResponderStatus.active_incident_count > 0,
            )
        )
    )
    busy_result = await db.execute(busy_query)
    busy_count = busy_result.scalar() or 0

    return {
        "total_responders": total_count,
        "available_responders": available_count,
        "busy_responders": busy_count,
        "offline_responders": total_count - available_count,
    }
