"""
Device service for device management operations.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DeviceNotFoundError,
    TrustedContactLimitError,
    UserNotFoundError,
)
from app.db.enums import enum_value
from app.db.models import Device
from app.repositories import AuditLogRepository, UserRepository
from app.repositories.device import DeviceRepository
from app.schemas.device import (
    DeviceDetailResponse,
    DevicePushTokenUpdate,
    DeviceRegisterRequest,
    DeviceResponse,
)

logger = structlog.get_logger()

MAX_DEVICES = 10


class DeviceService:
    """Service for device management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.device_repo = DeviceRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_repo = AuditLogRepository(db)

    # ─────────────────────────────────────────────────────────────────────────
    # Device Registration
    # ─────────────────────────────────────────────────────────────────────────

    async def register_device(
        self,
        user_id: str,
        request: DeviceRegisterRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DeviceResponse:
        """Register or update a device for push notifications."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Check device count limit (re-registering a known device is always allowed)
        devices = await self.device_repo.get_user_devices(user_id)
        known = any(d.device_uuid == request.device_uuid for d in devices)
        if not known and len(devices) >= MAX_DEVICES:
            await logger.awarning(
                "device_limit_exceeded",
                user_id=user_id,
                device_count=len(devices),
                max_devices=MAX_DEVICES,
            )
            raise TrustedContactLimitError(limit=MAX_DEVICES)

        # Register or update device
        device = await self.device_repo.register_or_update(
            user_id=user_id,
            device_uuid=request.device_uuid,
            platform=enum_value(request.platform),
            push_token=request.push_token,
            app_version=request.app_version,
        )

        await self.audit_repo.log_action(
            action="device_registered",
            resource_type="device",
            resource_id=device.id,
            actor_user_id=user_id,
            device_id=device.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "platform": enum_value(device.platform),
                "app_version": request.app_version,
                "is_new": device.id is not None,
            },
        )

        await logger.ainfo(
            "device_registered",
            user_id=user_id,
            device_id=device.id,
            platform=enum_value(device.platform),
        )

        return DeviceResponse.model_validate(device)

    # ─────────────────────────────────────────────────────────────────────────
    # Device Listing
    # ─────────────────────────────────────────────────────────────────────────

    async def get_user_devices(self, user_id: str) -> list[DeviceResponse]:
        """Get all devices for a user."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        devices = await self.device_repo.get_user_devices(user_id)
        return [DeviceResponse.model_validate(d) for d in devices]

    async def get_device_details(
        self,
        device_id: str,
        user_id: str,
    ) -> DeviceDetailResponse:
        """Get detailed information about a specific device."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Get device ensuring user ownership
        device = await self.device_repo.get_by_id(device_id)
        if not device or device.user_id != user_id:
            raise DeviceNotFoundError()

        return DeviceDetailResponse.model_validate(device)

    # ─────────────────────────────────────────────────────────────────────────
    # Push Token Management
    # ─────────────────────────────────────────────────────────────────────────

    async def update_push_token(
        self,
        device_id: str,
        user_id: str,
        request: DevicePushTokenUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DeviceResponse:
        """Update push token for a device."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Update push token
        device = await self.device_repo.update_push_token(
            device_id=device_id,
            user_id=user_id,
            push_token=request.push_token,
        )

        if not device:
            raise DeviceNotFoundError()

        # Log audit
        await self.audit_repo.log_action(
            action="device_token_updated",
            resource_type="device",
            resource_id=device_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"has_token": bool(request.push_token)},
        )

        await logger.ainfo(
            "device_token_updated",
            user_id=user_id,
            device_id=device_id,
        )

        return DeviceResponse.model_validate(device)

    # ─────────────────────────────────────────────────────────────────────────
    # Device Revocation/Deactivation
    # ─────────────────────────────────────────────────────────────────────────

    async def revoke_device(
        self,
        device_id: str,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Revoke/deactivate a device."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Revoke device
        device = await self.device_repo.revoke(device_id, user_id)
        if not device:
            raise DeviceNotFoundError()

        # Log audit
        await self.audit_repo.log_action(
            action="device_revoked",
            resource_type="device",
            resource_id=device_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"was_primary": device.is_primary},
        )

        await logger.ainfo(
            "device_revoked",
            user_id=user_id,
            device_id=device_id,
        )

        return True

    async def deactivate_all(
        self,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> int:
        """Deactivate all devices for a user (security event)."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Deactivate all devices
        count = await self.device_repo.deactivate_user_devices(user_id)

        # Log audit
        await self.audit_repo.log_action(
            action="all_devices_deactivated",
            resource_type="user",
            resource_id=user_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"devices_deactivated": count},
        )

        await logger.ainfo(
            "all_devices_deactivated",
            user_id=user_id,
            device_count=count,
        )

        return count

    # ─────────────────────────────────────────────────────────────────────────
    # Device Management
    # ─────────────────────────────────────────────────────────────────────────

    async def get_active_devices_for_notification(
        self, user_id: str
    ) -> list[Device]:
        """Get all active devices with push tokens for sending notifications."""
        return await self.device_repo.get_user_active_devices(user_id)

    async def set_primary_device(
        self,
        device_id: str,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DeviceResponse:
        """Set a device as the primary device for the user."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Set primary device
        device = await self.device_repo.set_primary_device(device_id, user_id)
        if not device:
            raise DeviceNotFoundError()

        # Log audit
        await self.audit_repo.log_action(
            action="primary_device_set",
            resource_type="device",
            resource_id=device_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await logger.ainfo(
            "primary_device_set",
            user_id=user_id,
            device_id=device_id,
        )

        return DeviceResponse.model_validate(device)
