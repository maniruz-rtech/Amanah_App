"""
User repository for user-related database operations.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import encrypt_field, hash_password
from app.db.enums import UserStatus
from app.db.models import Device, RefreshToken, Role, User, UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username with roles loaded."""
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.user_roles).selectinload(UserRole.role),
                selectinload(User.region),
                selectinload(User.organization),
            )
            .where(User.username == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(self, user_id: str) -> User | None:
        """Get user by ID with all relations loaded."""
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.user_roles).selectinload(UserRole.role),
                selectinload(User.region),
                selectinload(User.organization),
                selectinload(User.devices),
                selectinload(User.trusted_contacts),
                selectinload(User.responder_status),
            )
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        full_name: str,
        username: str,
        password: str,
        organization_id: str,
        region_id: str,
        phone: str | None = None,
        email: str | None = None,
        created_by_id: str | None = None,
        roles: list[str] | None = None,
    ) -> User:
        """Create a new user with encrypted PII."""
        from app.db.base import generate_ulid

        user = User(
            id=generate_ulid("usr_"),
            full_name=full_name,
            username=username.lower(),
            password_hash=hash_password(password),
            organization_id=organization_id,
            region_id=region_id,
            phone=phone,
            email=email,
            created_by_id=created_by_id,
            status=UserStatus.PENDING_VERIFICATION,
            is_verified=False,
            is_active=True,
        )

        self.db.add(user)
        await self.db.flush()

        # Assign roles
        if roles:
            await self._assign_roles(user.id, roles, created_by_id)

        await self.db.refresh(user)
        return user

    async def _assign_roles(
        self,
        user_id: str,
        role_names: list[str],
        assigned_by_id: str | None,
    ) -> None:
        """Assign roles to user."""
        from app.db.base import generate_ulid

        for role_name in role_names:
            # Get role
            result = await self.db.execute(
                select(Role).where(Role.name == role_name)
            )
            role = result.scalar_one_or_none()
            if role:
                user_role = UserRole(
                    id=generate_ulid("urol_"),
                    user_id=user_id,
                    role_id=role.id,
                    assigned_by_id=assigned_by_id,
                    assigned_at=datetime.now(UTC),
                )
                self.db.add(user_role)

        await self.db.flush()

    async def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp."""
        await self.db.execute(
            update(User).execution_options(synchronize_session="fetch")
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(UTC))
        )
        await self.db.flush()

    async def update_password(self, user_id: str, new_password: str) -> None:
        """Update user's password hash."""
        await self.db.execute(
            update(User).execution_options(synchronize_session="fetch")
            .where(User.id == user_id)
            .values(password_hash=hash_password(new_password))
        )
        await self.db.flush()

    async def suspend_user(self, user_id: str, reason: str | None = None) -> User | None:
        """Suspend a user account."""
        user = await self.get_by_id(user_id)
        if user:
            user.is_suspended = True
            user.status = UserStatus.SUSPENDED
            await self.db.flush()
        return user

    async def activate_user(self, user_id: str) -> User | None:
        """Activate a user account."""
        user = await self.get_by_id(user_id)
        if user:
            user.is_verified = True
            user.is_active = True
            user.is_suspended = False
            user.status = UserStatus.ACTIVE
            await self.db.flush()
        return user

    async def enable_mfa(self, user_id: str, totp_secret: str) -> None:
        """Enable MFA for a user by storing their TOTP secret."""
        from app.core.security import encrypt_field

        user = await self.get_by_id(user_id)
        if user:
            # Encrypt the TOTP secret before storing
            user.totp_secret_encrypted = encrypt_field(totp_secret)
            user.mfa_enabled = True
            await self.db.flush()

    async def disable_mfa(self, user_id: str) -> None:
        """Disable MFA for a user."""
        user = await self.get_by_id(user_id)
        if user:
            user.totp_secret_encrypted = None
            user.mfa_enabled = False
            await self.db.flush()

    async def get_users_by_region(
        self,
        region_id: str,
        skip: int = 0,
        limit: int = 100,
        status: UserStatus | None = None,
    ) -> tuple[list[User], int]:
        """Get users in a region with pagination."""
        from sqlalchemy import func

        query = (
            select(User)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .where(User.region_id == region_id)
        )

        if status:
            query = query.where(User.status == status)

        # Count
        count_query = select(func.count(User.id)).where(User.region_id == region_id)
        if status:
            count_query = count_query.where(User.status == status)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit).order_by(User.created_at.desc())
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return users, total

    async def revoke_all_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user."""
        result = await self.db.execute(
            update(RefreshToken).execution_options(synchronize_session="fetch")
            .where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked == False,
                )
            )
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.flush()
        return result.rowcount  # type: ignore

    # ── Presence + nearby ─────────────────────────────────────────────────────

    async def update_presence(
        self,
        user_id: str,
        h3_cell_district: str | None,
        h3_cell_block: str | None,
    ) -> None:
        """Refresh the user's last-known H3 cells + last_seen_at."""
        user = await self.get_by_id(user_id)
        if not user:
            return
        if h3_cell_district is not None:
            user.last_h3_cell_district = h3_cell_district
        if h3_cell_block is not None:
            user.last_h3_cell_block = h3_cell_block
        user.last_seen_at = datetime.now(UTC)
        await self.db.flush()

    async def list_active_in_h3_cells(
        self,
        organization_id: str,
        cells: list[str],
        exclude_user_id: str | None = None,
        max_idle_seconds: int = 600,
        limit: int = 50,
    ) -> list[User]:
        """
        Return active users whose last presence ping placed them in any of
        the supplied H3 cells (resolution 7) within the last
        [max_idle_seconds] seconds.

        Used by ``/api/v1/users/nearby`` after the API layer computes the
        k-ring set from the caller's own H3 cell.
        """
        from sqlalchemy import func
        if not cells:
            return []

        cutoff = datetime.now(UTC) - timedelta(seconds=max_idle_seconds)
        query = (
            select(User)
            .where(
                and_(
                    User.organization_id == organization_id,
                    User.is_active == True,
                    User.is_suspended == False,
                    User.last_h3_cell_district.in_(cells),
                    User.last_seen_at.is_not(None),
                    User.last_seen_at >= cutoff,
                )
            )
        )
        if exclude_user_id:
            query = query.where(User.id != exclude_user_id)
        query = query.order_by(User.last_seen_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())


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
        """Get all devices for a user."""
        result = await self.db.execute(
            select(Device)
            .where(Device.user_id == user_id)
            .order_by(Device.is_primary.desc(), Device.last_seen_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_active_devices(self, user_id: str) -> list[Device]:
        """Get all active devices with FCM tokens for a user."""
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

    async def register_or_update(
        self,
        user_id: str,
        device_uuid: str,
        platform: str,
        push_token: str | None = None,
        app_version: str | None = None,
    ) -> Device:
        """Register new device or update existing."""
        from app.db.base import generate_ulid

        device = await self.get_by_uuid(user_id, device_uuid)

        if device:
            # Update existing
            device.push_token = push_token
            device.app_version = app_version
            device.last_seen_at = datetime.now(UTC)
            device.is_active = True
        else:
            # Check if first device
            existing_count = await self.count(user_id=user_id)
            is_primary = existing_count == 0

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

    async def revoke(self, device_id: str, user_id: str) -> Device | None:
        """Revoke a device."""
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
