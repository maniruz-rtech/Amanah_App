"""
Role-Based Access Control (RBAC) and Permission System.

Implements:
- Role definitions (Member, Responder, Regional Admin, Super Admin)
- Permission checks
- Region-scoped authorization
"""

from enum import Enum
from functools import wraps
from typing import Any, Callable

from fastapi import HTTPException, status


class Role(str, Enum):
    """System roles per README specification."""

    MEMBER = "member"
    RESPONDER = "responder"
    REGIONAL_ADMIN = "regional_admin"
    SUPER_ADMIN = "super_admin"


class Permission(str, Enum):
    """Granular permissions for RBAC."""

    # User permissions
    READ_OWN_PROFILE = "read:own_profile"
    UPDATE_OWN_PROFILE = "update:own_profile"
    MANAGE_OWN_CONTACTS = "manage:own_contacts"

    # Incident permissions
    CREATE_INCIDENT = "create:incident"
    CANCEL_OWN_INCIDENT = "cancel:own_incident"
    READ_OWN_INCIDENT = "read:own_incident"

    # Responder permissions
    SET_AVAILABILITY = "set:availability"
    RECEIVE_INCIDENTS = "receive:incidents"
    ACCEPT_INCIDENTS = "accept:incidents"
    UPDATE_RESPONSE_STATUS = "update:response_status"

    # Admin permissions
    CREATE_USERS = "create:users"
    APPROVE_ACTIVATIONS = "approve:activations"
    APPROVE_RESETS = "approve:resets"
    SUSPEND_USERS = "suspend:users"
    VIEW_REGIONAL_INCIDENTS = "view:regional_incidents"
    VIEW_REGIONAL_AUDITS = "view:regional_audits"
    ESCALATE_INCIDENTS = "escalate:incidents"
    ASSIGN_ROLES = "assign:roles"

    # Super Admin permissions
    MANAGE_ALL_ORGS = "manage:all_orgs"
    VIEW_ALL_INCIDENTS = "view:all_incidents"
    VIEW_ALL_AUDITS = "view:all_audits"
    SYSTEM_CONFIG = "system:config"


# Role to Permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.MEMBER: {
        Permission.READ_OWN_PROFILE,
        Permission.UPDATE_OWN_PROFILE,
        Permission.MANAGE_OWN_CONTACTS,
        Permission.CREATE_INCIDENT,
        Permission.CANCEL_OWN_INCIDENT,
        Permission.READ_OWN_INCIDENT,
    },
    Role.RESPONDER: {
        # Includes all member permissions
        Permission.READ_OWN_PROFILE,
        Permission.UPDATE_OWN_PROFILE,
        Permission.MANAGE_OWN_CONTACTS,
        Permission.CREATE_INCIDENT,
        Permission.CANCEL_OWN_INCIDENT,
        Permission.READ_OWN_INCIDENT,
        # Responder-specific
        Permission.SET_AVAILABILITY,
        Permission.RECEIVE_INCIDENTS,
        Permission.ACCEPT_INCIDENTS,
        Permission.UPDATE_RESPONSE_STATUS,
    },
    Role.REGIONAL_ADMIN: {
        # Includes member permissions
        Permission.READ_OWN_PROFILE,
        Permission.UPDATE_OWN_PROFILE,
        Permission.MANAGE_OWN_CONTACTS,
        Permission.CREATE_INCIDENT,
        Permission.CANCEL_OWN_INCIDENT,
        Permission.READ_OWN_INCIDENT,
        # Regional admin-specific
        Permission.CREATE_USERS,
        Permission.APPROVE_ACTIVATIONS,
        Permission.APPROVE_RESETS,
        Permission.SUSPEND_USERS,
        Permission.VIEW_REGIONAL_INCIDENTS,
        Permission.VIEW_REGIONAL_AUDITS,
        Permission.ESCALATE_INCIDENTS,
        Permission.ASSIGN_ROLES,
    },
    Role.SUPER_ADMIN: {
        # All permissions
        Permission.READ_OWN_PROFILE,
        Permission.UPDATE_OWN_PROFILE,
        Permission.MANAGE_OWN_CONTACTS,
        Permission.CREATE_INCIDENT,
        Permission.CANCEL_OWN_INCIDENT,
        Permission.READ_OWN_INCIDENT,
        Permission.SET_AVAILABILITY,
        Permission.RECEIVE_INCIDENTS,
        Permission.ACCEPT_INCIDENTS,
        Permission.UPDATE_RESPONSE_STATUS,
        Permission.CREATE_USERS,
        Permission.APPROVE_ACTIVATIONS,
        Permission.APPROVE_RESETS,
        Permission.SUSPEND_USERS,
        Permission.VIEW_REGIONAL_INCIDENTS,
        Permission.VIEW_REGIONAL_AUDITS,
        Permission.ESCALATE_INCIDENTS,
        Permission.ASSIGN_ROLES,
        Permission.MANAGE_ALL_ORGS,
        Permission.VIEW_ALL_INCIDENTS,
        Permission.VIEW_ALL_AUDITS,
        Permission.SYSTEM_CONFIG,
    },
}


def get_permissions_for_roles(roles: list[str]) -> set[Permission]:
    """Get combined permissions for a list of role names."""
    permissions: set[Permission] = set()
    for role_name in roles:
        try:
            role = Role(role_name)
            permissions.update(ROLE_PERMISSIONS.get(role, set()))
        except ValueError:
            continue
    return permissions


def has_permission(user_roles: list[str], required_permission: Permission) -> bool:
    """Check if user has a specific permission."""
    permissions = get_permissions_for_roles(user_roles)
    return required_permission in permissions


def has_any_permission(user_roles: list[str], required_permissions: list[Permission]) -> bool:
    """Check if user has any of the required permissions."""
    permissions = get_permissions_for_roles(user_roles)
    return any(p in permissions for p in required_permissions)


def has_all_permissions(user_roles: list[str], required_permissions: list[Permission]) -> bool:
    """Check if user has all of the required permissions."""
    permissions = get_permissions_for_roles(user_roles)
    return all(p in permissions for p in required_permissions)


def is_admin(user_roles: list[str]) -> bool:
    """Check if user has any admin role."""
    admin_roles = {Role.REGIONAL_ADMIN.value, Role.SUPER_ADMIN.value}
    return any(role in admin_roles for role in user_roles)


def is_super_admin(user_roles: list[str]) -> bool:
    """Check if user is a super admin."""
    return Role.SUPER_ADMIN.value in user_roles


def is_responder(user_roles: list[str]) -> bool:
    """Check if user has responder role."""
    return Role.RESPONDER.value in user_roles


def can_access_region(
    user_region_id: str | None,
    user_roles: list[str],
    target_region_id: str,
) -> bool:
    """
    Check if user can access data in a specific region.

    Super admins can access all regions.
    Regional admins can only access their own region.
    """
    if is_super_admin(user_roles):
        return True
    return user_region_id == target_region_id


class PermissionDenied(HTTPException):
    """Exception raised when permission check fails."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class RegionAccessDenied(HTTPException):
    """Exception raised when region access check fails."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN_REGION_SCOPE", "message": "Access to this region is denied"},
        )


def require_permission(permission: Permission) -> Callable[..., Any]:
    """Decorator to require a specific permission."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # current_user should be injected via Depends
            current_user = kwargs.get("current_user")
            if current_user is None:
                raise PermissionDenied("Authentication required")

            user_roles = [r.role.name for r in current_user.user_roles]
            if not has_permission(user_roles, permission):
                raise PermissionDenied(f"Required permission: {permission.value}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_roles(*roles: Role) -> Callable[..., Any]:
    """Decorator to require specific roles."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_user = kwargs.get("current_user")
            if current_user is None:
                raise PermissionDenied("Authentication required")

            user_role_names = {r.role.name for r in current_user.user_roles}
            required_role_names = {r.value for r in roles}

            if not user_role_names.intersection(required_role_names):
                raise PermissionDenied(f"Required roles: {', '.join(r.value for r in roles)}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator
