"""
User profile and device management API endpoints.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    AuthenticatedUser,
    ClientIP,
    DBSession,
    UserAgent,
)
from app.core.exceptions import (
    DeviceNotFoundError,
    TrustedContactLimitError,
    UserNotFoundError,
)
from app.schemas.user import (
    DeviceRegisterRequest,
    DeviceResponse,
    DeviceRevokeResponse,
    NearbyUserResponse,
    NearbyUsersResponse,
    PresencePingRequest,
    TrustedContactCreate,
    TrustedContactResponse,
    TrustedContactUpdate,
    UserProfileUpdate,
    UserResponse,
)
from app.repositories.user import UserRepository
from app.services import UserService

logger = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["Users"])


# ─────────────────────────────────────────────────────────────────────────────
# Profile Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
async def get_profile(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get current user's profile."""
    service = UserService(db)
    try:
        user = await service.get_profile(current_user.user_id)
        from app.core.security import decrypt_field, mask_email, mask_phone

        phone_masked = None
        email_masked = None

        if user.phone_encrypted:
            try:
                phone = decrypt_field(user.phone_encrypted)
                phone_masked = mask_phone(phone)
            except Exception:
                phone_masked = "***"

        if user.email_encrypted:
            try:
                email = decrypt_field(user.email_encrypted)
                email_masked = mask_email(email)
            except Exception:
                email_masked = "***"

        return UserResponse(
            id=user.id,
            full_name=user.full_name,
            username=user.username,
            phone_masked=phone_masked,
            email_masked=email_masked,
            roles=user.roles,
            region_id=user.region_id,
            organization_id=user.organization_id,
            is_verified=user.is_verified,
            is_active=user.is_active,
            is_suspended=user.is_suspended,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    request: UserProfileUpdate,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Update current user's profile."""
    service = UserService(db)
    try:
        user = await service.update_profile(
            user_id=current_user.user_id,
            full_name=request.full_name,
        )

        from app.core.security import decrypt_field, mask_email, mask_phone

        phone_masked = None
        email_masked = None

        if user.phone_encrypted:
            try:
                phone = decrypt_field(user.phone_encrypted)
                phone_masked = mask_phone(phone)
            except Exception:
                phone_masked = "***"

        if user.email_encrypted:
            try:
                email = decrypt_field(user.email_encrypted)
                email_masked = mask_email(email)
            except Exception:
                email_masked = "***"

        return UserResponse(
            id=user.id,
            full_name=user.full_name,
            username=user.username,
            phone_masked=phone_masked,
            email_masked=email_masked,
            roles=user.roles,
            region_id=user.region_id,
            organization_id=user.organization_id,
            is_verified=user.is_verified,
            is_active=user.is_active,
            is_suspended=user.is_suspended,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Device Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    request: DeviceRegisterRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Register a device for push notifications."""
    service = UserService(db)
    try:
        device = await service.register_device(
            user_id=current_user.user_id,
            device_uuid=request.device_uuid,
            platform=request.platform,
            push_token=request.push_token,
            app_version=request.app_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return device

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except TrustedContactLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.message),
        )


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get all devices for current user."""
    service = UserService(db)
    try:
        devices = await service.get_devices(current_user.user_id)
        return devices

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.delete("/devices/{device_id}", response_model=DeviceRevokeResponse)
async def revoke_device(
    device_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Revoke a device."""
    service = UserService(db)
    try:
        await service.revoke_device(
            user_id=current_user.user_id,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return DeviceRevokeResponse()

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Trusted Contact Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/trusted-contacts",
    response_model=TrustedContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_trusted_contact(
    request: TrustedContactCreate,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Create a trusted contact for emergency notifications."""
    service = UserService(db)
    try:
        contact = await service.create_trusted_contact(
            user_id=current_user.user_id,
            name=request.name,
            phone=request.phone,
            relationship=request.relationship,
            priority=request.priority,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return contact

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except TrustedContactLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.message),
        )


@router.get("/trusted-contacts", response_model=list[TrustedContactResponse])
async def list_trusted_contacts(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get all trusted contacts for current user."""
    service = UserService(db)
    try:
        contacts = await service.get_trusted_contacts(current_user.user_id)
        return contacts

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.patch(
    "/trusted-contacts/{contact_id}",
    response_model=TrustedContactResponse,
)
async def update_trusted_contact(
    contact_id: str,
    request: TrustedContactUpdate,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Update a trusted contact."""
    service = UserService(db)
    try:
        contact = await service.update_trusted_contact(
            user_id=current_user.user_id,
            contact_id=contact_id,
            name=request.name,
            phone=request.phone,
            relationship=request.relationship,
            priority=request.priority,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return contact

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted contact not found",
        )


@router.delete("/trusted-contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trusted_contact(
    contact_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Delete a trusted contact."""
    service = UserService(db)
    try:
        await service.delete_trusted_contact(
            user_id=current_user.user_id,
            contact_id=contact_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trusted contact not found",
        )



# ─────────────────────────────────────────────────────────────────────────────
# Presence + Nearby
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/me/presence", status_code=status.HTTP_204_NO_CONTENT)
async def update_presence(
    request: PresencePingRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Periodic presence ping from the Android client.

    Persists the user's last-known H3 cells + ``last_seen_at``. The
    ``/users/nearby`` endpoint reads these to assemble proximity-aware
    responder lists.

    Privacy: only the H3 cells are stored. Raw GPS never reaches the
    backend through this endpoint.
    """
    repo = UserRepository(db)
    await repo.update_presence(
        user_id          = current_user.user_id,
        h3_cell_district = request.h3_cell_district,
        h3_cell_block    = request.h3_cell_block,
    )


@router.get("/nearby", response_model=NearbyUsersResponse)
async def nearby_users(
    current_user: AuthenticatedUser,
    db: DBSession,
    cells: str = Query(
        ...,
        description=(
            "Comma-separated list of H3 district cells (resolution 7) to "
            "search. The client computes the k-ring locally and supplies "
            "the result here, so the backend doesn't need an H3 library."
        ),
        min_length=1,
        max_length=4096,
    ),
    max_idle_seconds: int = Query(
        default=600,
        ge=10,
        le=3600,
        description="Drop users whose last presence ping is older than this.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Return active members in the supplied H3 cells.

    Excludes the caller themselves. Filters by:
      * same organization
      * `is_active = TRUE` and `is_suspended = FALSE`
      * `last_seen_at` within [max_idle_seconds]
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to an organization",
        )

    cell_list = [c.strip() for c in cells.split(",") if c.strip()]
    if len(cell_list) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many cells (max 64)",
        )

    repo = UserRepository(db)
    users = await repo.list_active_in_h3_cells(
        organization_id  = current_user.organization_id,
        cells            = cell_list,
        exclude_user_id  = current_user.user_id,
        max_idle_seconds = max_idle_seconds,
        limit            = limit,
    )

    items = [
        NearbyUserResponse(
            user_id          = u.id,
            display_name     = u.full_name or u.username,
            h3_cell_district = u.last_h3_cell_district or "",
            last_seen_at     = u.last_seen_at,  # type: ignore[arg-type]
            is_responder     = "responder" in u.roles,
        )
        for u in users
    ]
    return NearbyUsersResponse(
        items            = items,
        total            = len(items),
        queried_h3_cells = cell_list,
    )
