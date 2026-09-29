"""
Trusted contact schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import BaseSchema, TimestampMixin


class TrustedContactCreate(BaseSchema):
    """Create trusted contact request."""

    name: str = Field(min_length=1, max_length=255, description="Contact full name")
    phone: str = Field(
        min_length=10, max_length=20, description="Phone number (will be encrypted)"
    )
    relationship: str | None = Field(
        default=None, max_length=50, description="Relationship type (e.g., parent, sibling)"
    )
    priority: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Priority (1=highest, 5=lowest)",
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate and normalize phone number."""
        # Keep only digits and + prefix
        cleaned = "".join(c for c in v if c.isdigit() or c == "+")
        if len(cleaned) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return cleaned


class TrustedContactUpdate(BaseSchema):
    """Update trusted contact request."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=10, max_length=20)
    relationship: str | None = Field(default=None, max_length=50)
    priority: int | None = Field(default=None, ge=1, le=5)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        """Validate and normalize phone number if provided."""
        if v is None:
            return None
        cleaned = "".join(c for c in v if c.isdigit() or c == "+")
        if len(cleaned) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return cleaned


class TrustedContactResponse(BaseSchema, TimestampMixin):
    """Trusted contact response."""

    id: str = Field(description="Unique contact identifier")
    name: str = Field(description="Contact full name")
    phone_masked: str = Field(description="Masked phone number (***-****-1234)")
    relationship: str | None = Field(description="Relationship type")
    priority: int = Field(description="Priority level (1=highest, 5=lowest)")


class TrustedContactDetailResponse(BaseSchema, TimestampMixin):
    """Detailed trusted contact response with additional info."""

    id: str
    name: str
    phone_masked: str
    relationship: str | None
    priority: int
    user_id: str
    is_primary: bool = False  # Could indicate primary emergency contact


class TrustedContactListResponse(BaseSchema):
    """List of trusted contacts."""

    total: int = Field(description="Total number of contacts")
    limit: int = Field(description="Results per page")
    offset: int = Field(description="Offset for pagination")
    contacts: list[TrustedContactResponse]


class TrustedContactDeleteResponse(BaseSchema):
    """Response to trusted contact deletion."""

    success: bool = True
    message: str = "Trusted contact deleted successfully"


class TrustedContactBulkDeleteRequest(BaseSchema):
    """Delete multiple trusted contacts."""

    contact_ids: list[str] = Field(min_length=1, max_length=100)


class TrustedContactBulkDeleteResponse(BaseSchema):
    """Response to bulk deletion."""

    deleted_count: int
    failed_count: int
    message: str = "Bulk deletion completed"


class TrustedContactPriorityUpdate(BaseSchema):
    """Reorder contact priorities."""

    contact_priorities: dict[str, int] = Field(
        description="Map of contact_id to new priority (1-5)"
    )
