"""
Permission and scoping helpers for admin operations.

Provides role-based access control and organization/region scoping utilities.
"""

import structlog
from app.core.permissions import Permission

logger = structlog.get_logger()


class ScopeValidator:
    """Validates and enforces region/organization scoping."""

    @staticmethod
    def validate_user_scope(
        admin_user_id: str,
        admin_organization_id: str,
        admin_region_id: str | None,
        admin_roles: list[str],
        target_organization_id: str,
        target_region_id: str | None,
    ) -> bool:
        """
        Validate if admin can manage target user.

        Admins can only manage users in their organization and region (if scoped).
        Super admins can manage across regions in their organization.

        Args:
            admin_user_id: Admin user ID
            admin_organization_id: Admin's organization
            admin_region_id: Admin's region (None for super admin)
            admin_roles: Admin's roles
            target_organization_id: Target user's organization
            target_region_id: Target user's region

        Returns:
            True if admin can manage target user, False otherwise
        """
        # Must be same organization
        if admin_organization_id != target_organization_id:
            logger.warning(
                "scope_violation_org",
                admin_id=admin_user_id,
                target_org=target_organization_id,
            )
            return False

        # If admin is region-scoped, must target same region
        if admin_region_id and admin_region_id != target_region_id:
            logger.warning(
                "scope_violation_region",
                admin_id=admin_user_id,
                admin_region=admin_region_id,
                target_region=target_region_id,
            )
            return False

        return True

    @staticmethod
    def validate_incident_scope(
        admin_user_id: str,
        admin_organization_id: str,
        admin_region_id: str | None,
        incident_organization_id: str,
        incident_region_id: str | None,
    ) -> bool:
        """
        Validate if admin can view/manage incident.

        Args:
            admin_user_id: Admin user ID
            admin_organization_id: Admin's organization
            admin_region_id: Admin's region (None for super admin)
            incident_organization_id: Incident's organization
            incident_region_id: Incident's region

        Returns:
            True if admin can access incident, False otherwise
        """
        # Must be same organization
        if admin_organization_id != incident_organization_id:
            logger.warning(
                "scope_violation_incident_org",
                admin_id=admin_user_id,
                incident_org=incident_organization_id,
            )
            return False

        # If admin is region-scoped, must target same region
        if admin_region_id and admin_region_id != incident_region_id:
            logger.warning(
                "scope_violation_incident_region",
                admin_id=admin_user_id,
                admin_region=admin_region_id,
                incident_region=incident_region_id,
            )
            return False

        return True

    @staticmethod
    def check_self_action(
        admin_user_id: str,
        target_user_id: str,
        action: str,
    ) -> bool:
        """
        Check if admin is performing action on themselves.

        Some actions (suspend, role revoke) should not be allowed on self.

        Args:
            admin_user_id: Admin's user ID
            target_user_id: Target user ID
            action: Action being performed

        Returns:
            True if performing action on self, False otherwise
        """
        if admin_user_id == target_user_id:
            logger.warning(
                "self_action_prevented",
                user_id=admin_user_id,
                action=action,
            )
            return True

        return False


__all__ = ["ScopeValidator", "Permission"]

