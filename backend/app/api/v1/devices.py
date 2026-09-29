"""
Device management API endpoints.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

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
from app.schemas.device import (
    DeviceDetailResponse,
    DevicePushTokenUpdate,
    DeviceRegisterRequest,
    DeviceResponse,
    DeviceRevokeResponse,
)
from app.services.device import DeviceService

logger = structlog.get_logger()

router = APIRouter(prefix="/devices", tags=["Devices"])


# ─────────────────────────────────────────────────────────────────────────────
# Device Registration
# ─────────────────────────────────────────────────────────────────────────────


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    request: DeviceRegisterRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Register or update a device for push notifications.

    The first registered device for a user becomes the primary device.
    """
    service = DeviceService(db)
    try:
        device = await service.register_device(
            user_id=current_user.user_id,
            request=request,
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


# ─────────────────────────────────────────────────────────────────────────────
# Device Listing
# ─────────────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get all devices for the authenticated user.

    Devices are ordered by primary device first, then by last seen time.
    """
    service = DeviceService(db)
    try:
        devices = await service.get_user_devices(current_user.user_id)
        return devices

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.get("/{device_id}", response_model=DeviceDetailResponse)
async def get_device_details(
    device_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get detailed information about a specific device.

    The user can only access their own devices.
    """
    service = DeviceService(db)
    try:
        device = await service.get_device_details(
            device_id=device_id,
            user_id=current_user.user_id,
        )
        return device

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found or does not belong to user",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Push Token Management
# ─────────────────────────────────────────────────────────────────────────────


@router.patch("/{device_id}/token", response_model=DeviceResponse)
async def update_push_token(
    device_id: str,
    request: DevicePushTokenUpdate,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Update or refresh the push token for a device.

    This endpoint is used when the app receives a new push token from FCM/APNS.
    """
    service = DeviceService(db)
    try:
        device = await service.update_push_token(
            device_id=device_id,
            user_id=current_user.user_id,
            request=request,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return device

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found or does not belong to user",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Device Revocation/Deactivation
# ─────────────────────────────────────────────────────────────────────────────


@router.delete("/{device_id}", response_model=DeviceRevokeResponse)
async def revoke_device(
    device_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Revoke/deactivate a device.

    This is a soft delete - the device is marked as inactive and
    its push token is cleared. The device record is retained for audit purposes.
    """
    service = DeviceService(db)
    try:
        await service.revoke_device(
            device_id=device_id,
            user_id=current_user.user_id,
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
            detail="Device not found or does not belong to user",
        )


@router.post("/actions/deactivate-all")
async def deactivate_all_devices(
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Deactivate all devices for the current user.

    This is a security action typically performed after detecting a security breach
    or unauthorized access. All push tokens are cleared.
    """
    service = DeviceService(db)
    try:
        count = await service.deactivate_all(
            user_id=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {
            "success": True,
            "message": f"All {count} device(s) have been deactivated",
            "deactivated_count": count,
        }

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.post("/{device_id}/actions/set-primary", response_model=DeviceResponse)
async def set_primary_device(
    device_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
    ip_address: ClientIP,
    user_agent: UserAgent,
):
    """Set a device as the primary device for the user.

    Only one device can be primary at a time. Setting a new primary device
    automatically removes the primary status from the previous one.
    """
    service = DeviceService(db)
    try:
        device = await service.set_primary_device(
            device_id=device_id,
            user_id=current_user.user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return device

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except DeviceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found or does not belong to user",
        )
