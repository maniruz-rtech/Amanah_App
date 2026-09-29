"""
User service for profile, devices, and trusted contacts management.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DeviceNotFoundError,
    TrustedContactLimitError,
    UserNotFoundError,
)
from app.core.security import decrypt_field, encrypt_field, mask_email, mask_phone
from app.db.enums import enum_value
from app.db.models import User
from app.repositories import (
    AuditLogRepository,
    DeviceRepository,
    TrustedContactRepository,
    UserRepository,
)
from app.schemas.user import (
    DeviceResponse,
    TrustedContactResponse,
    UserProfileUpdate,
    UserResponse,
)

logger = structlog.get_logger()

MAX_TRUSTED_CONTACTS = 5
MAX_DEVICES = 10


class UserService:
    """Service for user-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.device_repo = DeviceRepository(db)
        self.contact_repo = TrustedContactRepository(db)
        self.audit_repo = AuditLogRepository(db)

    # ─────────────────────────────────────────────────────────────────────────
    # Profile Management
    # ─────────────────────────────────────────────────────────────────────────

    async def get_profile(self, user_id: str) -> User:
        """Get user profile with relations."""
        user = await self.user_repo.get_by_id_with_relations(user_id)
        if not user:
            raise UserNotFoundError()
        return user

    async def update_profile(
        self,
        user_id: str,
        full_name: str | None = None,
    ) -> User:
        """Update user profile."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        updated_fields = []

        if full_name:
            user.full_name = full_name
            updated_fields.append("full_name")

        if updated_fields:
            await self.db.flush()
            await self.db.refresh(user)

            await self.audit_repo.log_action(
                action="profile_updated",
                resource_type="user",
                resource_id=user_id,
                actor_user_id=user_id,
                metadata={"fields": updated_fields},
            )

            await logger.ainfo("profile_updated", user_id=user_id, fields=updated_fields)

        return user

    # ─────────────────────────────────────────────────────────────────────────
    # Device Management
    # ─────────────────────────────────────────────────────────────────────────

    async def register_device(
        self,
        user_id: str,
        device_uuid: str,
        platform: str,
        push_token: str | None = None,
        app_version: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> DeviceResponse:
        """Register or update a device."""
        # Verify user  exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Check device count limit
        devices = await self.device_repo.get_user_devices(user_id)
        known = any(d.device_uuid == device_uuid for d in devices)
        if not known and len(devices) >= MAX_DEVICES:
            await logger.awarning(
                "device_limit_exceeded",
                user_id=user_id,
                device_count=len(devices),
            )
            raise TrustedContactLimitError(limit=MAX_DEVICES)

        # Register or update device
        device = await self.device_repo.register_or_update(
            user_id=user_id,
            device_uuid=device_uuid,
            platform=platform,
            push_token=push_token,
            app_version=app_version,
        )

        await self.audit_repo.log_action(
            action="device_registered",
            resource_type="device",
            resource_id=device.id,
            actor_user_id=user_id,
            device_id=device.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"platform": enum_value(platform)},
        )

        await logger.ainfo(
            "device_registered",
            user_id=user_id,
            device_id=device.id,
            platform=enum_value(platform),
        )

        return DeviceResponse.model_validate(device)

    async def get_devices(self, user_id: str) -> list[DeviceResponse]:
        """Get all devices for user."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        devices = await self.device_repo.get_user_devices(user_id)
        return [DeviceResponse.model_validate(d) for d in devices]

    async def revoke_device(
        self,
        user_id: str,
        device_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Revoke a device."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Revoke device
        device = await self.device_repo.revoke(device_id, user_id)
        if not device:
            raise DeviceNotFoundError()

        await self.audit_repo.log_action(
            action="device_revoked",
            resource_type="device",
            resource_id=device_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await logger.ainfo(
            "device_revoked",
            user_id=user_id,
            device_id=device_id,
        )

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Trusted Contact Management
    # ─────────────────────────────────────────────────────────────────────────

    async def create_trusted_contact(
        self,
        user_id: str,
        name: str,
        phone: str,
        relationship: str | None = None,
        priority: int = 1,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TrustedContactResponse:
        """Create a trusted contact."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Check contact limit
        contact_count = await self.contact_repo.count_user_contacts(user_id)
        if contact_count >= MAX_TRUSTED_CONTACTS:
            await logger.awarning(
                "trusted_contact_limit_exceeded",
                user_id=user_id,
                contact_count=contact_count,
            )
            raise TrustedContactLimitError(limit=MAX_TRUSTED_CONTACTS)

        # Encrypt phone
        phone_encrypted = encrypt_field(phone)

        # Create contact
        contact = await self.contact_repo.create_contact(
            user_id=user_id,
            name=name,
            phone_encrypted=phone_encrypted,
            relationship=relationship,
            priority=priority,
        )

        await self.audit_repo.log_action(
            action="trusted_contact_created",
            resource_type="trusted_contact",
            resource_id=contact.id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"name": name},
        )

        await logger.ainfo(
            "trusted_contact_created",
            user_id=user_id,
            contact_id=contact.id,
        )

        # Decrypt for response
        try:
            phone_decrypted = decrypt_field(contact.phone_encrypted)
            phone_masked = mask_phone(phone_decrypted)
        except Exception:
            phone_masked = "***"

        return TrustedContactResponse(
            id=contact.id,
            name=contact.name,
            phone_masked=phone_masked,
            relationship=contact.relationship_type,
            priority=contact.priority,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )

    async def get_trusted_contacts(self, user_id: str) -> list[TrustedContactResponse]:
        """Get all trusted contacts for user."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        contacts = await self.contact_repo.get_user_contacts(user_id)

        result = []
        for contact in contacts:
            try:
                phone_decrypted = decrypt_field(contact.phone_encrypted)
                phone_masked = mask_phone(phone_decrypted)
            except Exception:
                phone_masked = "***"

            result.append(
                TrustedContactResponse(
                    id=contact.id,
                    name=contact.name,
                    phone_masked=phone_masked,
                    relationship=contact.relationship_type,
                    priority=contact.priority,
                    created_at=contact.created_at,
                    updated_at=contact.updated_at,
                )
            )

        return result

    async def update_trusted_contact(
        self,
        user_id: str,
        contact_id: str,
        name: str | None = None,
        phone: str | None = None,
        relationship: str | None = None,
        priority: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TrustedContactResponse:
        """Update a trusted contact."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Get contact
        contact = await self.contact_repo.get_by_id(contact_id)
        if not contact or contact.user_id != user_id:
            raise DeviceNotFoundError()  # Reuse for trusted contact not found

        updated_fields = []

        if name:
            contact.name = name
            updated_fields.append("name")

        if phone:
            contact.phone_encrypted = encrypt_field(phone)
            updated_fields.append("phone")

        if relationship is not None:
            contact.relationship_type = relationship
            updated_fields.append("relationship")

        if priority is not None:
            contact.priority = priority
            updated_fields.append("priority")

        if updated_fields:
            await self.db.flush()

            await self.audit_repo.log_action(
                action="trusted_contact_updated",
                resource_type="trusted_contact",
                resource_id=contact_id,
                actor_user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"fields": updated_fields},
            )

            await logger.ainfo(
                "trusted_contact_updated",
                user_id=user_id,
                contact_id=contact_id,
                fields=updated_fields,
            )

        # Decrypt for response
        try:
            phone_decrypted = decrypt_field(contact.phone_encrypted)
            phone_masked = mask_phone(phone_decrypted)
        except Exception:
            phone_masked = "***"

        return TrustedContactResponse(
            id=contact.id,
            name=contact.name,
            phone_masked=phone_masked,
            relationship=contact.relationship_type,
            priority=contact.priority,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )

    async def delete_trusted_contact(
        self,
        user_id: str,
        contact_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Delete a trusted contact."""
        # Verify user exists
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()

        # Get contact
        contact = await self.contact_repo.get_by_id(contact_id)
        if not contact or contact.user_id != user_id:
            raise DeviceNotFoundError()  # Reuse for trusted contact not found

        # Delete
        await self.db.delete(contact)
        await self.db.flush()

        await self.audit_repo.log_action(
            action="trusted_contact_deleted",
            resource_type="trusted_contact",
            resource_id=contact_id,
            actor_user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await logger.ainfo(
            "trusted_contact_deleted",
            user_id=user_id,
            contact_id=contact_id,
        )

        return True
