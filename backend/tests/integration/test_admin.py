"""
Integration tests for admin module.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_permissions import ScopeValidator
from app.core.exceptions import (
    InvalidStateTransitionError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.db.enums import (
    ApprovalRequestType,
    ApprovalStatus,
    IncidentStatus,
    IncidentSeverity,
    UserStatus,
)
from app.db.models import (
    AdminApproval,
    Incident,
    User,
    UserRole,
)
from app.repositories.admin import (
    AdminIncidentRepository,
    AdminRepository,
    AdminUserRepository,
)
from app.services.admin import AdminService


@pytest.fixture(autouse=True)
async def referenced_rows(db_session: AsyncSession):
    """Rows the tests reference by id (foreign-key targets): acting admins and a role."""
    from app.db.models import Role

    for user_id in ("usr_admin", "usr_approver"):
        db_session.add(
            User(
                id=user_id,
                username=user_id,
                password_hash="x",
                organization_id="org_test",
                region_id="reg_test",
                is_active=True,
                is_verified=True,
                status=UserStatus.ACTIVE,
            )
        )
    db_session.add(Role(id="role_test", name="role_test"))
    await db_session.flush()


class TestAdminRepository:
    """Tests for AdminRepository."""

    @pytest.fixture
    async def admin_repo(self, db_session: AsyncSession) -> AdminRepository:
        """Create admin repository."""
        return AdminRepository(db_session)

    @pytest.fixture
    async def test_user(self, db_session: AsyncSession) -> User:
        """Create test user for activation."""
        user = User(
            id="usr_admin_test",
            full_name="Test User",
            username="test_admin",
            password_hash="hash",
            organization_id="org_test",
            region_id="reg_test",
            is_active=False,
            is_verified=False,
            status=UserStatus.PENDING_ACTIVATION,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_create_user_activation_request(
        self,
        admin_repo: AdminRepository,
        test_user: User,
    ):
        """Test creating user activation approval request."""
        approval = await admin_repo.create_user_activation_request(test_user.id)

        assert approval.id is not None
        assert approval.request_type == ApprovalRequestType.USER_ACTIVATION
        assert approval.request_ref_id == test_user.id
        assert approval.status == ApprovalStatus.PENDING

    async def test_approve_user_activation(
        self,
        admin_repo: AdminRepository,
        test_user: User,
    ):
        """Test approving user activation."""
        approval = await admin_repo.create_user_activation_request(test_user.id)

        approved = await admin_repo.approve_user_activation(
            approval_id=approval.id,
            approved_by_id="usr_approver",
            notes="Approved",
        )

        assert approved.status == ApprovalStatus.APPROVED
        assert approved.reviewed_by_id == "usr_approver"
        assert approved.notes == "Approved"

    async def test_reject_user_activation(
        self,
        admin_repo: AdminRepository,
        test_user: User,
    ):
        """Test rejecting user activation."""
        approval = await admin_repo.create_user_activation_request(test_user.id)

        rejected = await admin_repo.reject_user_activation(
            approval_id=approval.id,
            rejected_by_id="usr_approver",
            reason="Does not meet criteria",
        )

        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.reviewed_by_id == "usr_approver"
        assert rejected.notes == "Does not meet criteria"


class TestAdminIncidentRepository:
    """Tests for AdminIncidentRepository."""

    @pytest.fixture
    async def incident_repo(self, db_session: AsyncSession) -> AdminIncidentRepository:
        """Create admin incident repository."""
        return AdminIncidentRepository(db_session)

    @pytest.fixture
    async def test_incidents(self, db_session: AsyncSession) -> list[Incident]:
        """Create test incidents."""
        db_session.add(
            User(
                id="usr_incident_creator",
                username="incident_creator",
                password_hash="x",
                organization_id="org_test",
                region_id="reg_test",
                is_active=True,
                is_verified=True,
                status=UserStatus.ACTIVE,
            )
        )
        await db_session.flush()

        incidents = []
        for i in range(3):
            incident = Incident(
                id=f"inc_test{i}",
                organization_id="org_test",
                region_id="reg_test",
                created_by_id="usr_incident_creator",
                status=IncidentStatus.BROADCASTING if i == 0 else IncidentStatus.RESOLVED,
                severity=IncidentSeverity.HIGH,
                started_at=datetime.now(UTC) - timedelta(hours=i),
            )
            db_session.add(incident)
            incidents.append(incident)

        await db_session.flush()
        return incidents

    async def test_search_incidents_by_status(
        self,
        incident_repo: AdminIncidentRepository,
        test_incidents: list[Incident],
    ):
        """Test searching incidents by status."""
        incidents, total = await incident_repo.search_incidents(
            organization_id="org_test",
            status=IncidentStatus.BROADCASTING,
        )

        assert total >= 1
        assert any(i.status == IncidentStatus.BROADCASTING for i in incidents)

    async def test_search_incidents_by_severity(
        self,
        incident_repo: AdminIncidentRepository,
        test_incidents: list[Incident],
    ):
        """Test searching incidents by severity."""
        incidents, total = await incident_repo.search_incidents(
            organization_id="org_test",
            severity=IncidentSeverity.HIGH.value,
        )

        assert total >= 1

    async def test_search_incidents_with_pagination(
        self,
        incident_repo: AdminIncidentRepository,
        test_incidents: list[Incident],
    ):
        """Test paginated incident search."""
        incidents1, total = await incident_repo.search_incidents(
            organization_id="org_test",
            skip=0,
            limit=2,
        )

        incidents2, _ = await incident_repo.search_incidents(
            organization_id="org_test",
            skip=2,
            limit=2,
        )

        assert len(incidents1) <= 2
        assert total >= 1


class TestAdminUserRepository:
    """Tests for AdminUserRepository."""

    @pytest.fixture
    async def user_repo(self, db_session: AsyncSession) -> AdminUserRepository:
        """Create admin user repository."""
        return AdminUserRepository(db_session)

    @pytest.fixture
    async def test_users(self, db_session: AsyncSession) -> list[User]:
        """Create test users."""
        users = []
        for i in range(3):
            user = User(
                id=f"usr_test{i}",
                full_name=f"User {i}",
                username=f"user{i}",
                password_hash="hash",
                organization_id="org_test",
                region_id="reg_test",
                is_active=i != 1,  # One inactive
                is_suspended=False,
                status=UserStatus.ACTIVE if i != 1 else UserStatus.PENDING_ACTIVATION,
            )
            db_session.add(user)
            users.append(user)

        await db_session.flush()
        return users

    async def test_search_users_by_status(
        self,
        user_repo: AdminUserRepository,
        test_users: list[User],
    ):
        """Test searching users by status."""
        users, total = await user_repo.search_users(
            organization_id="org_test",
            status=UserStatus.ACTIVE,
        )

        assert total >= 1
        assert any(u.status == UserStatus.ACTIVE for u in users)

    async def test_search_users_by_active(
        self,
        user_repo: AdminUserRepository,
        test_users: list[User],
    ):
        """Test searching users by active status."""
        users, total = await user_repo.search_users(
            organization_id="org_test",
            is_active=True,
        )

        assert total >= 2  # At least 2 active users

    async def test_assign_role(
        self,
        user_repo: AdminUserRepository,
        test_users: list[User],
    ):
        """Test assigning role to user."""
        user = test_users[0]

        await user_repo.assign_role(
            user_id=user.id,
            role_id="role_test",
            assigned_by_id="usr_admin",
        )

        # Verify role was assigned
        result = await user_repo.db.execute(
            select(UserRole).where(
                (UserRole.user_id == user.id) &
                (UserRole.role_id == "role_test")
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_revoke_role(
        self,
        user_repo: AdminUserRepository,
        test_users: list[User],
    ):
        """Test revoking role from user."""
        user = test_users[0]

        # Assign first
        await user_repo.assign_role(
            user_id=user.id,
            role_id="role_test",
            assigned_by_id="usr_admin",
        )

        # Then revoke
        await user_repo.revoke_role(
            user_id=user.id,
            role_id="role_test",
        )

        # Verify role was revoked
        result = await user_repo.db.execute(
            select(UserRole).where(
                (UserRole.user_id == user.id) &
                (UserRole.role_id == "role_test")
            )
        )
        assert result.scalar_one_or_none() is None


class TestAdminService:
    """Tests for AdminService."""

    @pytest.fixture
    async def service(self, db_session: AsyncSession) -> AdminService:
        """Create admin service."""
        return AdminService(db_session)

    @pytest.fixture
    async def test_user(self, db_session: AsyncSession) -> User:
        """Create test user."""
        user = User(
            id="usr_service_test",
            full_name="Service Test",
            username="service_test",
            password_hash="hash",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_suspended=False,
            status=UserStatus.ACTIVE,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_create_user(
        self,
        service: AdminService,
    ):
        """Test creating user via admin."""
        user = await service.create_user(
            full_name="New User",
            username="newuser",
            organization_id="org_test",
            region_id="reg_test",
            admin_id="usr_admin",
            roles=None,
        )

        assert user.id is not None
        assert user.full_name == "New User"
        assert user.username == "newuser"
        assert user.created_by_id == "usr_admin"

    async def test_assign_role(
        self,
        service: AdminService,
        test_user: User,
    ):
        """Test assigning role."""
        await service.assign_role(
            user_id=test_user.id,
            role_id="role_test",
            admin_id="usr_admin",
        )

        # Verify in database
        result = await service.db.execute(
            select(UserRole).where(
                (UserRole.user_id == test_user.id) &
                (UserRole.role_id == "role_test")
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_revoke_role(
        self,
        service: AdminService,
        test_user: User,
    ):
        """Test revoking role."""
        # Assign first
        await service.assign_role(
            user_id=test_user.id,
            role_id="role_test",
            admin_id="usr_admin",
        )

        # Then revoke
        await service.revoke_role(
            user_id=test_user.id,
            role_id="role_test",
            admin_id="usr_admin",
        )

        # Verify revoked
        result = await service.db.execute(
            select(UserRole).where(
                (UserRole.user_id == test_user.id) &
                (UserRole.role_id == "role_test")
            )
        )
        assert result.scalar_one_or_none() is None


class TestScopeValidator:
    """Tests for ScopeValidator."""

    def test_validate_user_scope_same_org(self):
        """Test scope validation for same organization."""
        assert ScopeValidator.validate_user_scope(
            admin_user_id="usr_admin",
            admin_organization_id="org_1",
            admin_region_id="reg_1",
            admin_roles=["admin"],
            target_organization_id="org_1",
            target_region_id="reg_1",
        ) is True

    def test_validate_user_scope_different_org(self):
        """Test scope validation for different organization."""
        assert ScopeValidator.validate_user_scope(
            admin_user_id="usr_admin",
            admin_organization_id="org_1",
            admin_region_id="reg_1",
            admin_roles=["admin"],
            target_organization_id="org_2",
            target_region_id="reg_2",
        ) is False

    def test_validate_user_scope_different_region_regional_admin(self):
        """Test scope validation for regional admin accessing different region."""
        assert ScopeValidator.validate_user_scope(
            admin_user_id="usr_regional_admin",
            admin_organization_id="org_1",
            admin_region_id="reg_1",
            admin_roles=["regional_admin"],
            target_organization_id="org_1",
            target_region_id="reg_2",
        ) is False

    def test_validate_user_scope_different_region_super_admin(self):
        """Test scope validation for super admin accessing different region."""
        # Super admin with no region scope
        assert ScopeValidator.validate_user_scope(
            admin_user_id="usr_super_admin",
            admin_organization_id="org_1",
            admin_region_id=None,
            admin_roles=["super_admin"],
            target_organization_id="org_1",
            target_region_id="reg_2",
        ) is True

    def test_check_self_action(self):
        """Test self-action prevention."""
        assert ScopeValidator.check_self_action(
            admin_user_id="usr_admin",
            target_user_id="usr_admin",
            action="suspend",
        ) is True

    def test_check_self_action_different_user(self):
        """Test self-action prevention for different user."""
        assert ScopeValidator.check_self_action(
            admin_user_id="usr_admin",
            target_user_id="usr_other",
            action="suspend",
        ) is False
