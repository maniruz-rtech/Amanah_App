"""
Trusted contact repository for trusted contact management operations.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import generate_ulid
from app.db.models import TrustedContact
from app.repositories.base import BaseRepository


class TrustedContactRepository(BaseRepository[TrustedContact]):
    """Repository for TrustedContact operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(TrustedContact, db)

    async def create_contact(
        self,
        user_id: str,
        name: str,
        phone_encrypted: bytes,
        relationship: str | None = None,
        priority: int = 1,
    ) -> TrustedContact:
        """Create a trusted contact."""
        contact = TrustedContact(
            id=generate_ulid("tc_"),
            user_id=user_id,
            name=name,
            phone_encrypted=phone_encrypted,
            relationship_type=relationship,
            priority=priority,
        )
        self.db.add(contact)
        await self.db.flush()
        await self.db.refresh(contact)
        return contact

    async def get_user_contacts(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[TrustedContact], int]:
        """Get all trusted contacts for a user with pagination."""
        # Count total
        count_result = await self.db.execute(
            select(func.count(TrustedContact.id)).where(
                TrustedContact.user_id == user_id
            )
        )
        total = count_result.scalar() or 0

        # Get paginated results
        result = await self.db.execute(
            select(TrustedContact)
            .where(TrustedContact.user_id == user_id)
            .order_by(TrustedContact.priority, TrustedContact.created_at)
            .offset(skip)
            .limit(limit)
        )
        contacts = list(result.scalars().all())

        return contacts, total

    async def count_user_contacts(self, user_id: str) -> int:
        """Count total trusted contacts for a user."""
        result = await self.db.execute(
            select(func.count(TrustedContact.id)).where(
                TrustedContact.user_id == user_id
            )
        )
        return result.scalar() or 0

    async def get_by_user_and_id(
        self,
        user_id: str,
        contact_id: str,
    ) -> TrustedContact | None:
        """Get contact ensuring user ownership."""
        result = await self.db.execute(
            select(TrustedContact).where(
                and_(
                    TrustedContact.id == contact_id,
                    TrustedContact.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_contact(
        self,
        user_id: str,
        contact_id: str,
        name: str | None = None,
        phone_encrypted: bytes | None = None,
        relationship: str | None = None,
        priority: int | None = None,
    ) -> TrustedContact | None:
        """Update a trusted contact (with user ownership check)."""
        contact = await self.get_by_user_and_id(user_id, contact_id)

        if not contact:
            return None

        updated = False

        if name is not None:
            contact.name = name
            updated = True

        if phone_encrypted is not None:
            contact.phone_encrypted = phone_encrypted
            updated = True

        if relationship is not None:
            contact.relationship_type = relationship
            updated = True

        if priority is not None:
            contact.priority = priority
            updated = True

        if updated:
            contact.updated_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(contact)

        return contact

    async def delete_contact(self, user_id: str, contact_id: str) -> bool:
        """Delete a trusted contact (soft or hard delete)."""
        contact = await self.get_by_user_and_id(user_id, contact_id)

        if not contact:
            return False

        await self.db.delete(contact)
        await self.db.flush()
        return True

    async def delete_multiple(self, user_id: str, contact_ids: list[str]) -> int:
        """Delete multiple contacts for a user."""
        result = await self.db.execute(
            delete(TrustedContact).execution_options(synchronize_session="fetch").where(
                and_(
                    TrustedContact.user_id == user_id,
                    TrustedContact.id.in_(contact_ids),
                )
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    async def delete_all_user_contacts(self, user_id: str) -> int:
        """Delete all contacts for a user (e.g., account deletion)."""
        result = await self.db.execute(
            delete(TrustedContact).execution_options(synchronize_session="fetch").where(
                TrustedContact.user_id == user_id
            )
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    async def reorder_priorities(
        self,
        user_id: str,
        priority_map: dict[str, int],
    ) -> list[TrustedContact]:
        """Update priorities for multiple contacts."""
        contacts = []

        for contact_id, priority in priority_map.items():
            contact = await self.get_by_user_and_id(user_id, contact_id)

            if contact:
                contact.priority = priority
                contact.updated_at = datetime.now(UTC)
                contacts.append(contact)

        if contacts:
            await self.db.flush()

        return contacts

    async def get_high_priority_contacts(
        self,
        user_id: str,
        limit: int = 3,
    ) -> list[TrustedContact]:
        """Get highest priority contacts for a user."""
        result = await self.db.execute(
            select(TrustedContact)
            .where(TrustedContact.user_id == user_id)
            .order_by(TrustedContact.priority)
            .limit(limit)
        )
        return list(result.scalars().all())
