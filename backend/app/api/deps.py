"""
FastAPI dependencies for authentication, authorization, and database sessions.
"""

from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountSuspendedError,
    InvalidTokenError,
    PermissionDeniedError,
)
from app.core.permissions import Permission, has_permission
from app.core.security import verify_access_token
from app.db.session import get_db
from app.repositories import UserRepository

logger = structlog.get_logger()

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


# Type alias for database dependency
DBSession = Annotated[AsyncSession, Depends(get_db)]


class CurrentUser:
    """Current authenticated user data."""

    def __init__(
        self,
        user_id: str,
        roles: list[str],
        organization_id: str | None = None,
        region_id: str | None = None,
    ):
        self.user_id = user_id
        self.roles = roles
        self.organization_id = organization_id
        self.region_id = region_id


async def get_current_user(
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> CurrentUser:
    """
    Validate JWT token and return current user.

    Raises HTTPException if token is invalid or user is not found/active.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_access_token(credentials.credentials)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.sub
    roles = payload.roles

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database to verify status and get org/region
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is not active",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended",
        )

    return CurrentUser(
        user_id=user_id,
        roles=roles,
        organization_id=user.organization_id,
        region_id=user.region_id,
    )


# Type alias for current user dependency
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]


def require_permission(permission: Permission):
    """
    Dependency factory for permission checking.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_permission(Permission.MANAGE_USERS))])
    """
    async def check_permission(current_user: AuthenticatedUser) -> CurrentUser:
        if not has_permission(current_user.roles, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )
        return current_user

    return check_permission


def require_any_permission(*permissions: Permission):
    """
    Dependency factory requiring any of the given permissions.

    Usage:
        @router.get("/data", dependencies=[Depends(require_any_permission(Permission.VIEW_INCIDENTS, Permission.MANAGE_INCIDENTS))])
    """
    async def check_permission(current_user: AuthenticatedUser) -> CurrentUser:
        for permission in permissions:
            if has_permission(current_user.roles, permission):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: one of {[p.value for p in permissions]} required",
        )

    return check_permission


def require_all_permissions(*permissions: Permission):
    """
    Dependency factory requiring all of the given permissions.
    """
    async def check_permissions(current_user: AuthenticatedUser) -> CurrentUser:
        missing = []
        for permission in permissions:
            if not has_permission(current_user.roles, permission):
                missing.append(permission.value)

        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: missing {missing}",
            )
        return current_user

    return check_permissions


async def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    # Check for forwarded headers (behind reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct client
    if request.client:
        return request.client.host

    return "unknown"


async def get_user_agent(
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
) -> str | None:
    """Get user agent from request headers."""
    return user_agent


async def get_request_id(
    request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> str | None:
    """Get request ID from headers or generate one."""
    if request_id:
        return request_id

    import secrets
    return f"req_{secrets.token_urlsafe(8)}"


# Type aliases for common header dependencies
ClientIP = Annotated[str, Depends(get_client_ip)]
UserAgent = Annotated[str | None, Depends(get_user_agent)]
RequestID = Annotated[str | None, Depends(get_request_id)]


async def get_optional_current_user(
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> CurrentUser | None:
    """
    Validate JWT token and return current user if provided, otherwise None.
    Does not require authentication - for endpoints that optionally use auth.
    """
    if not credentials:
        return None

    try:
        payload = verify_access_token(credentials.credentials)
    except InvalidTokenError:
        return None

    user_id = payload.sub
    roles = payload.roles

    if not user_id:
        return None

    # Get user from database to verify status and get org/region
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user or not user.is_active:
        return None

    return CurrentUser(
        user_id=user_id,
        roles=roles,
        organization_id=user.organization_id,
        region_id=user.region_id,
    )


# Type alias for optional current user dependency
OptionalUser = Annotated[CurrentUser | None, Depends(get_optional_current_user)]
