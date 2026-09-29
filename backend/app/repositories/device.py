"""
Device repository for device management operations.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device
from app.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    """Repository for Device operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(Device, db)

    async def get_by_uuid(self, user_id: str, device_uuid: str) -> Device | None:
        """Get device by user and UUID."""
        result = await self.db.execute(
            select(Device).where(
                and_(
                    Device.user_id == user_id,
                    Device.device_uuid == device_uuid,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_user_devices(self, user_id: str) -> list[Device]:
        """Get all devices for a user, ordered by primary first, then by last seen."""
        result = await self.db.execute(
            select(Device)
            .where(Device.user_id == user_id)
            .order_by(Device.is_primary.desc(), Device.last_seen_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_active_devices(self, user_id: str) -> list[Device]:
        """Get all active devices with push tokens for a user."""
        result = await self.db.execute(
            select(Device)
            .where(
                and_(
                    Device.user_id == user_id,
                    Device.is_active == True,
                    Device.push_token.isnot(None),
                )
            )
            .order_by(Device.is_primary.desc(), Device.last_seen_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_active_device_count(self, user_id: str) -> int:
        """Get count of active devices for a user."""
        from sqlalchemy import func

        result = await self.db.execute(
            select(func.count(Device.id)).where(
                and_(Device.user_id == user_id, Device.is_active == True)
            )
        )
        return result.scalar() or 0

    async def register_or_update(
        self,
        user_id: str,
        device_uuid: str,
        platform: str,
        push_token: str | None = None,
        app_version: str | None = None,
    ) -> Device:
        """Register new device or update existing device."""
        from app.db.base import generate_ulid

        device = await self.get_by_uuid(user_id, device_uuid)

        if device:
            # Update existing device. A missing push token / version means "not
            # provided", not "clear it" (login sends them only when known).
            if push_token is not None:
                device.push_token = push_token
            if app_version is not None:
                device.app_version = app_version
            device.last_seen_at = datetime.now(UTC)
            device.is_active = True
        else:
            # Create new device - first device is primary
            active_count = await self.get_user_active_device_count(user_id)
            is_primary = active_count == 0

            device = Device(
                id=generate_ulid("dev_"),
                user_id=user_id,
                device_uuid=device_uuid,
                platform=platform,
                push_token=push_token,
                app_version=app_version,
                is_primary=is_primary,
                is_active=True,
                last_seen_at=datetime.now(UTC),
            )
            self.db.add(device)

        await self.db.flush()
        await self.db.refresh(device)
        return device

    async def deactivate_stalest(self, user_id: str) -> Device | None:
        """Deactivate the least-recently-seen active non-primary device."""
        result = await self.db.execute(
            select(Device)
            .where(
                and_(
                    Device.user_id == user_id,
                    Device.is_active == True,  # noqa: E712
                    Device.is_primary == False,  # noqa: E712
                )
            )
            .order_by(Device.last_seen_at.asc().nullsfirst())
            .limit(1)
        )
        device = result.scalar_one_or_none()
        if device:
            device.is_active = False
            await self.db.flush()
        return device

    async def update_push_token(
        self,
        device_id: str,
        user_id: str,
        push_token: str,
    ) -> Device | None:
        """Update push token for a device."""
        result = await self.db.execute(
            select(Device).where(
                and_(
                    Device.id == device_id,
                    Device.user_id == user_id,
                )
            )
        )
        device = result.scalar_one_or_none()

        if device:
            device.push_token = push_token
            device.last_seen_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(device)

        return device

    async def revoke(self, device_id: str, user_id: str) -> Device | None:
        """Revoke/deactivate a device (soft delete)."""
        result = await self.db.execute(
            select(Device).where(
                and_(
                    Device.id == device_id,
                    Device.user_id == user_id,
                )
            )
        )
        device = result.scalar_one_or_none()

        if device:
            device.is_active = False
            device.push_token = None
            await self.db.flush()

        return device

    async def deactivate_user_devices(self, user_id: str) -> int:
        """Deactivate all devices for a user."""
        result = await self.db.execute(
            update(Device).execution_options(synchronize_session="fetch")
            .where(Device.user_id == user_id)
            .values(is_active=False, push_token=None)
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    async def set_primary_device(
        self, device_id: str, user_id: str
    ) -> Device | None:
        """Set a device as primary and clear primary from others."""
        # Clear primary from all user's devices
        await self.db.execute(
            update(Device).execution_options(synchronize_session="fetch")
            .where(Device.user_id == user_id)
            .values(is_primary=False)
        )

        # Set specified device as primary
        result = await self.db.execute(
            select(Device).where(
                and_(
                    Device.id == device_id,
                    Device.user_id == user_id,
                )
            )
        )
        device = result.scalar_one_or_none()

        if device:
            device.is_primary = True
            await self.db.flush()
            await self.db.refresh(device)

        return device
