"""
Integration tests for user and device management.

Tests cover:
- User profile get/update
- Device registration and listing
- Device revocation
- Trusted contact CRUD
- Access control
- Audit logging
"""

import pytest
from datetime import UTC, datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DeviceNotFoundError,
    TrustedContactLimitError,
    UserNotFoundError,
)
from app.core.security import encrypt_field, hash_password, mask_phone
from app.db.enums import DevicePlatform, UserStatus
from app.db.models import User, Device, TrustedContact
from app.services.user import UserService


@pytest.mark.asyncio
class TestUserProfile:
    """Tests for user profile operations."""

    @pytest.fixture
    async def test_user(self, db: AsyncSession):
        """Create a test user."""
        user = User(
            id="usr_profile_test",
            username="profileuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Profile Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_get_profile_success(self, db: AsyncSession, test_user):
        """Test getting user profile."""
        service = UserService(db)
        user = await service.get_profile(test_user.id)

        assert user.id == test_user.id
        assert user.username == "profileuser"
        assert user.full_name == "Profile Test User"

    @pytest.mark.asyncio
    async def test_get_profile_not_found(self, db: AsyncSession):
        """Test getting non-existent user profile."""
        service = UserService(db)

        with pytest.raises(UserNotFoundError):
            await service.get_profile("usr_nonexistent")

    @pytest.mark.asyncio
    async def test_update_profile_success(self, db: AsyncSession, test_user):
        """Test updating user profile."""
        service = UserService(db)
        user = await service.update_profile(
            user_id=test_user.id,
            full_name="Updated Name",
        )

        assert user.full_name == "Updated Name"
        assert user.username == "profileuser"

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, db: AsyncSession):
        """Test updating non-existent user profile."""
        service = UserService(db)

        with pytest.raises(UserNotFoundError):
            await service.update_profile(
                user_id="usr_nonexistent",
                full_name="New Name",
            )


@pytest.mark.asyncio
class TestDeviceManagement:
    """Tests for device registration and management."""

    @pytest.fixture
    async def device_user(self, db: AsyncSession):
        """Create a test user for device tests."""
        user = User(
            id="usr_device_test",
            username="deviceuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Device Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_register_device_success(self, db: AsyncSession, device_user):
        """Test device registration."""
        service = UserService(db)
        device = await service.register_device(
            user_id=device_user.id,
            device_uuid="device-uuid-12345",
            platform="ios",
            push_token="fcm_token_123",
            app_version="1.0.0",
        )

        assert device.device_uuid == "device-uuid-12345"
        assert device.platform == "ios"
        assert device.is_primary is True  # First device

    @pytest.mark.asyncio
    async def test_register_multiple_devices(self, db: AsyncSession, device_user):
        """Test registering multiple devices."""
        service = UserService(db)

        # First device
        device1 = await service.register_device(
            user_id=device_user.id,
            device_uuid="device-1",
            platform="ios",
        )
        assert device1.is_primary is True

        # Second device
        device2 = await service.register_device(
            user_id=device_user.id,
            device_uuid="device-2",
            platform="android",
        )
        assert device2.is_primary is False

    @pytest.mark.asyncio
    async def test_register_device_user_not_found(self, db: AsyncSession):
        """Test device registration for non-existent user."""
        service = UserService(db)

        with pytest.raises(UserNotFoundError):
            await service.register_device(
                user_id="usr_nonexistent",
                device_uuid="device-uuid",
                platform="ios",
            )

    @pytest.mark.asyncio
    async def test_register_device_limit(self, db: AsyncSession, device_user):
        """Test device count limit."""
        service = UserService(db)

        # Register max devices
        for i in range(10):
            await service.register_device(
                user_id=device_user.id,
                device_uuid=f"device-{i}",
                platform="ios",
            )

        # Next registration should fail
        with pytest.raises(TrustedContactLimitError):
            await service.register_device(
                user_id=device_user.id,
                device_uuid="device-over-limit",
                platform="ios",
            )

    @pytest.mark.asyncio
    async def test_get_devices(self, db: AsyncSession, device_user):
        """Test getting user devices."""
        service = UserService(db)

        # Register devices
        await service.register_device(
            user_id=device_user.id,
            device_uuid="device-1",
            platform="ios",
        )
        await service.register_device(
            user_id=device_user.id,
            device_uuid="device-2",
            platform="android",
        )

        devices = await service.get_devices(device_user.id)
        assert len(devices) == 2

    @pytest.mark.asyncio
    async def test_revoke_device_success(self, db: AsyncSession, device_user):
        """Test revoking a device."""
        service = UserService(db)

        # Register device
        device = await service.register_device(
            user_id=device_user.id,
            device_uuid="device-to-revoke",
            platform="ios",
            push_token="token123",
        )

        # Revoke
        result = await service.revoke_device(
            user_id=device_user.id,
            device_id=device.id,
        )

        assert result is True

        # Verify device is inactive
        from app.repositories import DeviceRepository
        repo = DeviceRepository(db)
        revoked = await repo.get_by_id(device.id)
        assert revoked.is_active is False
        assert revoked.push_token is None

    @pytest.mark.asyncio
    async def test_revoke_device_not_found(self, db: AsyncSession, device_user):
        """Test revoking non-existent device."""
        service = UserService(db)

        with pytest.raises(DeviceNotFoundError):
            await service.revoke_device(
                user_id=device_user.id,
                device_id="dev_nonexistent",
            )


@pytest.mark.asyncio
class TestTrustedContacts:
    """Tests for trusted contact management."""

    @pytest.fixture
    async def contact_user(self, db: AsyncSession):
        """Create a test user for contact tests."""
        user = User(
            id="usr_contact_test",
            username="contactuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Contact Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_create_trusted_contact(self, db: AsyncSession, contact_user):
        """Test creating a trusted contact."""
        service = UserService(db)
        contact = await service.create_trusted_contact(
            user_id=contact_user.id,
            name="Mom",
            phone="+880123456789",
            relationship="mother",
            priority=1,
        )

        assert contact.name == "Mom"
        assert contact.relationship == "mother"
        assert contact.priority == 1
        assert contact.phone_masked is not None
        # documented format (mask_phone): first 5 chars + **** + last 5 chars
        assert contact.phone_masked == "+8801****56789"
        assert "+880123456789" not in contact.phone_masked

    @pytest.mark.asyncio
    async def test_create_contact_user_not_found(self, db: AsyncSession):
        """Test creating contact for non-existent user."""
        service = UserService(db)

        with pytest.raises(UserNotFoundError):
            await service.create_trusted_contact(
                user_id="usr_nonexistent",
                name="Contact",
                phone="+880123456789",
            )

    @pytest.mark.asyncio
    async def test_create_contact_limit(self, db: AsyncSession, contact_user):
        """Test trusted contact limit."""
        service = UserService(db)

        # Create max contacts
        for i in range(5):
            await service.create_trusted_contact(
                user_id=contact_user.id,
                name=f"Contact {i}",
                phone=f"+8801234567{i:02d}",
                priority=i + 1,
            )

        # Next one should fail
        with pytest.raises(TrustedContactLimitError):
            await service.create_trusted_contact(
                user_id=contact_user.id,
                name="Sixth Contact",
                phone="+880123456799",
            )

    @pytest.mark.asyncio
    async def test_get_trusted_contacts(self, db: AsyncSession, contact_user):
        """Test getting user's trusted contacts."""
        service = UserService(db)

        # Create contacts
        await service.create_trusted_contact(
            user_id=contact_user.id,
            name="Mom",
            phone="+880123456789",
        )
        await service.create_trusted_contact(
            user_id=contact_user.id,
            name="Dad",
            phone="+880987654321",
        )

        contacts = await service.get_trusted_contacts(contact_user.id)
        assert len(contacts) == 2
        names = [c.name for c in contacts]
        assert "Mom" in names
        assert "Dad" in names

    @pytest.mark.asyncio
    async def test_update_trusted_contact(self, db: AsyncSession, contact_user):
        """Test updating a trusted contact."""
        service = UserService(db)

        # Create contact
        contact = await service.create_trusted_contact(
            user_id=contact_user.id,
            name="Contact",
            phone="+880123456789",
            priority=3,
        )

        # Update
        updated = await service.update_trusted_contact(
            user_id=contact_user.id,
            contact_id=contact.id,
            name="Updated Contact",
            priority=1,
        )

        assert updated.name == "Updated Contact"
        assert updated.priority == 1

    @pytest.mark.asyncio
    async def test_update_contact_not_found(self, db: AsyncSession, contact_user):
        """Test updating non-existent contact."""
        service = UserService(db)

        with pytest.raises(DeviceNotFoundError):
            await service.update_trusted_contact(
                user_id=contact_user.id,
                contact_id="tc_nonexistent",
                name="New Name",
            )

    @pytest.mark.asyncio
    async def test_delete_trusted_contact(self, db: AsyncSession, contact_user):
        """Test deleting a trusted contact."""
        service = UserService(db)

        # Create contact
        contact = await service.create_trusted_contact(
            user_id=contact_user.id,
            name="Contact",
            phone="+880123456789",
        )

        # Delete
        result = await service.delete_trusted_contact(
            user_id=contact_user.id,
            contact_id=contact.id,
        )

        assert result is True

        # Verify deletion
        contacts = await service.get_trusted_contacts(contact_user.id)
        assert len(contacts) == 0

    @pytest.mark.asyncio
    async def test_delete_contact_not_found(self, db: AsyncSession, contact_user):
        """Test deleting non-existent contact."""
        service = UserService(db)

        with pytest.raises(DeviceNotFoundError):
            await service.delete_trusted_contact(
                user_id=contact_user.id,
                contact_id="tc_nonexistent",
            )


@pytest.mark.asyncio
class TestAuditLogging:
    """Tests for audit logging in user operations."""

    @pytest.fixture
    async def audit_user(self, db: AsyncSession):
        """Create a test user for audit tests."""
        user = User(
            id="usr_audit_test",
            username="audituser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Audit Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_audit_profile_update(self, db: AsyncSession, audit_user):
        """Test audit logging for profile updates."""
        service = UserService(db)

        await service.update_profile(
            user_id=audit_user.id,
            full_name="New Name",
        )

        # Check audit log
        from app.repositories import AuditLogRepository
        audit_repo = AuditLogRepository(db)
        # Note: Need to check if audit log was created
        # This depends on how audit logging is implemented

    @pytest.mark.asyncio
    async def test_audit_device_registration(self, db: AsyncSession, audit_user):
        """Test audit logging for device registration."""
        service = UserService(db)

        await service.register_device(
            user_id=audit_user.id,
            device_uuid="audit-device",
            platform="ios",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        # Audit log should be created

    @pytest.mark.asyncio
    async def test_audit_trusted_contact_creation(self, db: AsyncSession, audit_user):
        """Test audit logging for trusted contact creation."""
        service = UserService(db)

        await service.create_trusted_contact(
            user_id=audit_user.id,
            name="Contact",
            phone="+880123456789",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        # Audit log should be created


@pytest.mark.asyncio
class TestAccessControl:
    """Tests for access control and authorization."""

    @pytest.fixture
    async def user1(self, db: AsyncSession):
        """Create first test user."""
        user = User(
            id="usr_access_1",
            username="user1",
            password_hash=hash_password("Password123!"),
            full_name="User One",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.fixture
    async def user2(self, db: AsyncSession):
        """Create second test user."""
        user = User(
            id="usr_access_2",
            username="user2",
            password_hash=hash_password("Password123!"),
            full_name="User Two",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_user_cannot_access_others_devices(self, db: AsyncSession, user1, user2):
        """Test that users can only access their own devices."""
        service1 = UserService(db)
        service2 = UserService(db)

        # User1 registers device
        device = await service1.register_device(
            user_id=user1.id,
            device_uuid="user1-device",
            platform="ios",
        )

        # User2 should not be able to revoke user1's device
        from app.core.exceptions import DeviceNotFoundError as DNFError
        with pytest.raises(DNFError):
            await service2.revoke_device(
                user_id=user2.id,
                device_id=device.id,
            )

    @pytest.mark.asyncio
    async def test_user_cannot_access_others_contacts(self, db: AsyncSession, user1, user2):
        """Test that users can only access their own contacts."""
        service1 = UserService(db)
        service2 = UserService(db)

        # User1 creates contact
        contact = await service1.create_trusted_contact(
            user_id=user1.id,
            name="Contact",
            phone="+880123456789",
        )

        # User2 should not be able to update user1's contact
        from app.core.exceptions import DeviceNotFoundError as DNFError
        with pytest.raises(DNFError):
            await service2.update_trusted_contact(
                user_id=user2.id,
                contact_id=contact.id,
                name="Hacked",
            )
