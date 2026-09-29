"""
Integration tests for device management.

Tests cover:
- Device registration
- Device listing
- Push token updates
- Device revocation/deactivation
- Device limits
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
from app.core.security import hash_password
from app.db.enums import DevicePlatform, UserStatus
from app.db.models import Device, User
from app.services.device import DeviceService
from app.schemas.device import DeviceRegisterRequest


@pytest.mark.asyncio
class TestDeviceRegistration:
    """Tests for device registration."""

    @pytest.fixture
    async def test_user(self, db: AsyncSession):
        """Create a test user."""
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
    async def test_register_device_success(self, db: AsyncSession, test_user):
        """Test successful device registration."""
        service = DeviceService(db)
        request = DeviceRegisterRequest(
            device_uuid="uuid-12345",
            platform=DevicePlatform.ANDROID,
            push_token="fcm_token_12345",
            app_version="1.0.0",
        )

        device = await service.register_device(
            user_id=test_user.id,
            request=request,
            ip_address="192.168.1.1",
            user_agent="Android/1.0",
        )

        assert device.id is not None
        assert device.device_uuid == "uuid-12345"
        assert device.platform == DevicePlatform.ANDROID.value
        assert device.app_version == "1.0.0"
        assert device.is_active is True
        assert device.is_primary is True  # First device is primary

    @pytest.mark.asyncio
    async def test_register_device_without_push_token(self, db: AsyncSession, test_user):
        """Test device registration without push token."""
        service = DeviceService(db)
        request = DeviceRegisterRequest(
            device_uuid="uuid-no-token",
            platform=DevicePlatform.IOS,
            push_token=None,
            app_version="2.0.0",
        )

        device = await service.register_device(
            user_id=test_user.id,
            request=request,
        )

        assert device.device_uuid == "uuid-no-token"
        assert device.platform == DevicePlatform.IOS.value
        assert device.is_primary is True

    @pytest.mark.asyncio
    async def test_register_device_nonexistent_user(self, db: AsyncSession):
        """Test device registration for non-existent user."""
        service = DeviceService(db)
        request = DeviceRegisterRequest(
            device_uuid="uuid-12345",
            platform=DevicePlatform.ANDROID,
        )

        with pytest.raises(UserNotFoundError):
            await service.register_device(
                user_id="usr_nonexistent",
                request=request,
            )

    @pytest.mark.asyncio
    async def test_register_device_exceeds_limit(self, db: AsyncSession, test_user):
        """Test device registration exceeding limit."""
        service = DeviceService(db)

        # Register max devices
        for i in range(10):
            request = DeviceRegisterRequest(
                device_uuid=f"uuid-{i}",
                platform=DevicePlatform.ANDROID,
                push_token=f"token-{i}",
            )
            device = await service.register_device(
                user_id=test_user.id,
                request=request,
            )
            assert device.is_active is True

        # Try to register 11th device
        request = DeviceRegisterRequest(
            device_uuid="uuid-11",
            platform=DevicePlatform.ANDROID,
        )

        with pytest.raises(TrustedContactLimitError):
            await service.register_device(
                user_id=test_user.id,
                request=request,
            )

    @pytest.mark.asyncio
    async def test_register_device_update_existing(self, db: AsyncSession, test_user):
        """Test updating an existing device registration."""
        service = DeviceService(db)

        # Register device
        request1 = DeviceRegisterRequest(
            device_uuid="uuid-update-test",
            platform=DevicePlatform.ANDROID,
            push_token="old_token",
            app_version="1.0.0",
        )
        device1 = await service.register_device(
            user_id=test_user.id,
            request=request1,
        )

        # Update same device
        request2 = DeviceRegisterRequest(
            device_uuid="uuid-update-test",
            platform=DevicePlatform.ANDROID,
            push_token="new_token",
            app_version="2.0.0",
        )
        device2 = await service.register_device(
            user_id=test_user.id,
            request=request2,
        )

        # Should be same device with updated token
        assert device1.id == device2.id
        assert device2.app_version == "2.0.0"

    @pytest.mark.asyncio
    async def test_first_registered_device_is_primary(
        self, db: AsyncSession, test_user
    ):
        """Test that first registered device becomes primary."""
        service = DeviceService(db)

        # Register first device
        request1 = DeviceRegisterRequest(
            device_uuid="uuid-first",
            platform=DevicePlatform.ANDROID,
        )
        device1 = await service.register_device(
            user_id=test_user.id,
            request=request1,
        )
        assert device1.is_primary is True

        # Register second device
        request2 = DeviceRegisterRequest(
            device_uuid="uuid-second",
            platform=DevicePlatform.IOS,
        )
        device2 = await service.register_device(
            user_id=test_user.id,
            request=request2,
        )
        assert device2.is_primary is False


@pytest.mark.asyncio
class TestDeviceListing:
    """Tests for device listing."""

    @pytest.fixture
    async def test_user_with_devices(self, db: AsyncSession):
        """Create a test user with devices."""
        user = User(
            id="usr_listing_test",
            username="listinguser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Listing Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Add devices
        for i in range(3):
            device = Device(
                id=f"dev_listing_{i}",
                user_id=user.id,
                device_uuid=f"uuid-listing-{i}",
                platform=DevicePlatform.ANDROID.value,
                push_token=f"token-{i}",
                app_version="1.0.0",
                is_primary=i == 0,
                is_active=True,
                last_seen_at=datetime.now(UTC),
            )
            db.add(device)

        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_get_user_devices(self, db: AsyncSession, test_user_with_devices):
        """Test getting all devices for a user."""
        service = DeviceService(db)
        devices = await service.get_user_devices(test_user_with_devices.id)

        assert len(devices) == 3
        assert devices[0].is_primary is True  # Primary first
        assert all(d.is_active for d in devices)

    @pytest.mark.asyncio
    async def test_get_devices_nonexistent_user(self, db: AsyncSession):
        """Test getting devices for non-existent user."""
        service = DeviceService(db)

        with pytest.raises(UserNotFoundError):
            await service.get_user_devices("usr_nonexistent")

    @pytest.mark.asyncio
    async def test_get_device_details(self, db: AsyncSession, test_user_with_devices):
        """Test getting device details."""
        service = DeviceService(db)
        device = await service.get_device_details(
            device_id="dev_listing_0",
            user_id=test_user_with_devices.id,
        )

        assert device.id == "dev_listing_0"
        assert device.is_primary is True

    @pytest.mark.asyncio
    async def test_get_device_unauthorized_access(
        self, db: AsyncSession, test_user_with_devices
    ):
        """Test that user cannot access other user's devices."""
        # A real, different user (the service checks the caller exists first).
        other = User(
            id="usr_other_user",
            username="otheruser",
            password_hash=hash_password("TestPassword123!"),
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(other)
        await db.flush()

        service = DeviceService(db)

        with pytest.raises(DeviceNotFoundError):
            await service.get_device_details(
                device_id="dev_listing_0",
                user_id=other.id,
            )


@pytest.mark.asyncio
class TestPushTokenUpdate:
    """Tests for push token updates."""

    @pytest.fixture
    async def test_device(self, db: AsyncSession):
        """Create a test user with a device."""
        user = User(
            id="usr_token_test",
            username="tokenuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Token Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        device = Device(
            id="dev_token_test",
            user_id=user.id,
            device_uuid="uuid-token-test",
            platform=DevicePlatform.ANDROID.value,
            push_token="old_token",
            app_version="1.0.0",
            is_primary=True,
            is_active=True,
            last_seen_at=datetime.now(UTC),
        )
        db.add(device)
        await db.flush()

        return {"user": user, "device": device}

    @pytest.mark.asyncio
    async def test_update_push_token_success(self, db: AsyncSession, test_device):
        """Test successful push token update."""
        from app.schemas.device import DevicePushTokenUpdate

        service = DeviceService(db)
        request = DevicePushTokenUpdate(push_token="new_token")

        device = await service.update_push_token(
            device_id=test_device["device"].id,
            user_id=test_device["user"].id,
            request=request,
            ip_address="192.168.1.1",
        )

        assert device.id == test_device["device"].id
        # Note: push_token is not exposed in response schema for security

    @pytest.mark.asyncio
    async def test_update_push_token_nonexistent_device(
        self, db: AsyncSession, test_device
    ):
        """Test updating push token for non-existent device."""
        from app.schemas.device import DevicePushTokenUpdate

        service = DeviceService(db)
        request = DevicePushTokenUpdate(push_token="new_token")

        with pytest.raises(DeviceNotFoundError):
            await service.update_push_token(
                device_id="dev_nonexistent",
                user_id=test_device["user"].id,
                request=request,
            )


@pytest.mark.asyncio
class TestDeviceRevocation:
    """Tests for device revocation/deactivation."""

    @pytest.fixture
    async def test_device(self, db: AsyncSession):
        """Create a test user with a device."""
        user = User(
            id="usr_revoke_test",
            username="revokeuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Revoke Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        device = Device(
            id="dev_revoke_test",
            user_id=user.id,
            device_uuid="uuid-revoke-test",
            platform=DevicePlatform.ANDROID.value,
            push_token="token_to_revoke",
            app_version="1.0.0",
            is_primary=True,
            is_active=True,
            last_seen_at=datetime.now(UTC),
        )
        db.add(device)
        await db.flush()

        return {"user": user, "device": device}

    @pytest.mark.asyncio
    async def test_revoke_device_success(self, db: AsyncSession, test_device):
        """Test successful device revocation."""
        service = DeviceService(db)
        success = await service.revoke_device(
            device_id=test_device["device"].id,
            user_id=test_device["user"].id,
            ip_address="192.168.1.1",
        )

        assert success is True

        # Verify device is deactivated
        devices = await service.get_user_devices(test_device["user"].id)
        assert len([d for d in devices if d.is_active]) == 0

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_device(self, db: AsyncSession, test_device):
        """Test revoking non-existent device."""
        service = DeviceService(db)

        with pytest.raises(DeviceNotFoundError):
            await service.revoke_device(
                device_id="dev_nonexistent",
                user_id=test_device["user"].id,
            )

    @pytest.mark.asyncio
    async def test_deactivate_all_devices(self, db: AsyncSession):
        """Test deactivating all devices for a user."""
        user = User(
            id="usr_deactivate_all",
            username="deactivateuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Deactivate Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Add multiple devices
        for i in range(3):
            device = Device(
                id=f"dev_all_{i}",
                user_id=user.id,
                device_uuid=f"uuid-all-{i}",
                platform=DevicePlatform.ANDROID.value,
                push_token=f"token-{i}",
                is_primary=i == 0,
                is_active=True,
                last_seen_at=datetime.now(UTC),
            )
            db.add(device)

        await db.flush()

        service = DeviceService(db)
        count = await service.deactivate_all(
            user_id=user.id,
            ip_address="192.168.1.1",
        )

        assert count == 3

        # Verify all are deactivated
        devices = await service.get_user_devices(user.id)
        assert all(not d.is_active for d in devices)


@pytest.mark.asyncio
class TestPrimaryDevice:
    """Tests for primary device management."""

    @pytest.fixture
    async def test_user_with_devices(self, db: AsyncSession):
        """Create a test user with multiple devices."""
        user = User(
            id="usr_primary_test",
            username="primaryuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Primary Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        for i in range(3):
            device = Device(
                id=f"dev_primary_{i}",
                user_id=user.id,
                device_uuid=f"uuid-primary-{i}",
                platform=DevicePlatform.ANDROID.value,
                push_token=f"token-{i}",
                is_primary=i == 0,
                is_active=True,
                last_seen_at=datetime.now(UTC),
            )
            db.add(device)

        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_set_primary_device(
        self, db: AsyncSession, test_user_with_devices
    ):
        """Test setting a device as primary."""
        service = DeviceService(db)

        # Set second device as primary
        device = await service.set_primary_device(
            device_id="dev_primary_1",
            user_id=test_user_with_devices.id,
        )

        assert device.is_primary is True

        # Verify first device is no longer primary
        devices = await service.get_user_devices(test_user_with_devices.id)
        primary_count = sum(1 for d in devices if d.is_primary)
        assert primary_count == 1
        assert devices[0].id == "dev_primary_1"
