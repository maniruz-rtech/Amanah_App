"""
User model with encrypted PII fields.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base, generate_ulid
from app.db.enums import UserStatus


class User(Base):
    """User entity with encrypted sensitive fields."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: generate_ulid("usr_"),
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("regions.id", ondelete="CASCADE"),
        nullable=False,
    )
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # Provenance: the admin who created this account (NULL = self-service/bootstrap).
    created_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Encrypted PII fields (stored as bytes)
    phone_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    phone_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # Password hash (Argon2id)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Full name and display
    full_name_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # MFA fields
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # TOTP shared secret, AES-256-GCM encrypted at rest (never stored in clear).
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mfa_backup_codes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Account lifecycle.
    #
    # `status` is the lifecycle state of record and is what admins filter by:
    #     pending_verification -> pending_activation -> active <-> suspended
    #                                                   active  -> deactivated
    # The three booleans below are the *enforcement* flags read on every request
    # (login, get_current_user, presence, nearby). They are kept in step with
    # `status` by `_sync_status_from_flags` and by the repository transitions
    # (`suspend_user` / `activate_user`), so the two cannot silently diverge.
    status: Mapped[UserStatus] = mapped_column(
        ENUM(
            UserStatus,
            name="user_status_enum",
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=UserStatus.PENDING_VERIFICATION,
        server_default=UserStatus.PENDING_VERIFICATION.value,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    suspension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audit fields
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Account security
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Last-known H3 cells, populated by the client's periodic presence ping
    # (REST or WS). DISTRICT (resolution 7) is used by the broad-cast
    # `/users/nearby` query; BLOCK (resolution 9) is reserved for tight
    # precise-dispatch filtering. Plain string columns — indexed below.
    last_h3_cell_district: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_h3_cell_block:    Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_seen_at:          Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="users"
    )
    region: Mapped["Region"] = relationship(
        "Region", back_populates="users"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        foreign_keys="UserRole.user_id",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    trusted_contacts: Mapped[list["TrustedContact"]] = relationship(
        "TrustedContact",
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    responder_status: Mapped["ResponderStatus | None"] = relationship(
        "ResponderStatus",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )

    @property
    def full_name(self) -> str | None:
        """Decrypt and return full name."""
        if self.full_name_encrypted:
            from app.core.security import decrypt_field
            return decrypt_field(self.full_name_encrypted)
        return self.display_name or self.username

    @property
    def email(self) -> str | None:
        """Decrypted email address (None when unset)."""
        if self.email_encrypted:
            from app.core.security import decrypt_field
            return decrypt_field(self.email_encrypted)
        return None

    @email.setter
    def email(self, value: str | None) -> None:
        from app.core.security import encrypt_field, hash_contact
        self.email_encrypted = encrypt_field(value) if value else None
        self.email_hash = hash_contact(value) if value else None

    @property
    def phone(self) -> str | None:
        """Decrypted phone number (None when unset)."""
        if self.phone_encrypted:
            from app.core.security import decrypt_field
            return decrypt_field(self.phone_encrypted)
        return None

    @phone.setter
    def phone(self, value: str | None) -> None:
        from app.core.security import encrypt_field, hash_contact
        self.phone_encrypted = encrypt_field(value) if value else None
        self.phone_hash = hash_contact(value) if value else None

    @full_name.setter
    def full_name(self, value: str | None) -> None:
        """Encrypt and store the full name (allows ``User(full_name=...)``)."""
        from app.core.security import encrypt_field
        self.full_name_encrypted = encrypt_field(value) if value else None

    @validates("is_suspended", "is_active")
    def _sync_status_from_flags(self, key: str, value: bool) -> bool:
        """Keep `status` consistent when an enforcement flag is flipped directly.

        Only moves *into* / *out of* the suspended and deactivated states; it
        never overrides the pending_* or active states set explicitly.
        """
        current = self.__dict__.get("status")
        if key == "is_suspended":
            if value:
                self.status = UserStatus.SUSPENDED
            elif current == UserStatus.SUSPENDED:
                self.status = UserStatus.ACTIVE if self.__dict__.get("is_verified") else UserStatus.PENDING_VERIFICATION
        elif key == "is_active":
            if not value:
                self.status = UserStatus.DEACTIVATED
            elif current == UserStatus.DEACTIVATED:
                self.status = UserStatus.ACTIVE if self.__dict__.get("is_verified") else UserStatus.PENDING_VERIFICATION
        return value

    @property
    def roles(self) -> list[str]:
        """Get list of role names for this user."""
        return [ur.role.name for ur in self.user_roles if ur.role]

    @property
    def is_admin(self) -> bool:
        """Check if user has any admin role."""
        return any(r in ("regional_admin", "super_admin") for r in self.roles)

    @property
    def is_super_admin(self) -> bool:
        """Check if user is a super admin."""
        return "super_admin" in self.roles

    @property
    def is_responder(self) -> bool:
        """Check if user has responder role."""
        return "responder" in self.roles

    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_organization_id", "organization_id"),
        Index("idx_users_region_id", "region_id"),
        Index("idx_users_is_active", "is_active"),
        Index("idx_users_status", "status"),
        Index("idx_users_last_h3_cell_district", "last_h3_cell_district"),
        Index("idx_users_last_h3_cell_block",    "last_h3_cell_block"),
    )


# Import to avoid circular imports
from app.db.models.device import Device  # noqa: E402
from app.db.models.organization import Organization  # noqa: E402, F811
from app.db.models.region import Region  # noqa: E402, F811
from app.db.models.responder_status import ResponderStatus  # noqa: E402
from app.db.models.role import UserRole  # noqa: E402
from app.db.models.trusted_contact import TrustedContact  # noqa: E402
