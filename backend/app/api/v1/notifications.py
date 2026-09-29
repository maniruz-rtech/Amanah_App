"""
Notification API endpoints.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AuthenticatedUser, DBSession
from app.schemas.common import PaginatedResponse
from app.schemas.notification import (
    MarkReadRequest,
    NotificationResponse,
)
from app.services import NotificationService

logger = structlog.get_logger()

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedResponse)
async def get_notifications(
    current_user: AuthenticatedUser,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    unread_only: Annotated[bool, Query()] = False,
):
    """Get user's notifications."""
    notification_service = NotificationService(db)

    notifications, total = await notification_service.get_user_notifications(
        user_id=current_user.user_id,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
    )

    return PaginatedResponse(
        items=notifications,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(
    request: MarkReadRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Mark specific notifications as read."""
    notification_service = NotificationService(db)

    await notification_service.mark_read(
        user_id=current_user.user_id,
        notification_ids=request.notification_ids,
    )


@router.post("/mark-all-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Mark all notifications as read."""
    notification_service = NotificationService(db)
    await notification_service.mark_all_read(current_user.user_id)


@router.get("/unread-count")
async def get_unread_count(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get count of unread notifications."""
    notification_service = NotificationService(db)

    _, total = await notification_service.get_user_notifications(
        user_id=current_user.user_id,
        unread_only=True,
        limit=1,
    )

    return {"unread_count": total}
