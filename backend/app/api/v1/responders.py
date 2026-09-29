"""
Responder API endpoints.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AuthenticatedUser, DBSession, require_permission
from app.core.exceptions import (
    IncidentNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ResponderNotFoundError,
)
from app.core.permissions import Permission
from app.schemas.responder import (
    AvailabilityResponse,
    AvailabilityUpdate,
    IncidentAcceptRequest,
    IncidentDeclineRequest,
    NearbyIncidentResponse,
    ResponderAssignmentResponse,
)
from app.services import ResponderService

logger = structlog.get_logger()

router = APIRouter(prefix="/responders", tags=["Responders"])


@router.get(
    "/availability",
    response_model=AvailabilityResponse,
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def get_availability(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get current responder availability status."""
    responder_service = ResponderService(db)
    return await responder_service.get_availability(current_user.user_id)


@router.put(
    "/availability",
    response_model=AvailabilityResponse,
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def update_availability(
    update: AvailabilityUpdate,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Update responder availability and location.

    Call this when going on/off duty and periodically while available
    to update location.
    """
    responder_service = ResponderService(db)

    return await responder_service.update_availability(
        user_id=current_user.user_id,
        update=update,
    )


@router.get(
    "/nearby-incidents",
    response_model=list[NearbyIncidentResponse],
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def get_nearby_incidents(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    current_user: AuthenticatedUser,
    db: DBSession,
    radius_km: Annotated[float | None, Query(ge=0.1, le=100)] = None,
):
    """
    Get nearby active incidents.

    Returns incidents within radius sorted by distance.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be assigned to an organization",
        )

    responder_service = ResponderService(db)

    return await responder_service.get_nearby_incidents(
        user_id=current_user.user_id,
        organization_id=current_user.organization_id,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
    )


@router.post(
    "/incidents/{incident_id}/accept",
    response_model=ResponderAssignmentResponse,
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def accept_incident(
    incident_id: str,
    request: IncidentAcceptRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Accept an incident assignment.

    Provide estimated time of arrival in minutes.
    """
    responder_service = ResponderService(db)

    try:
        assignment = await responder_service.accept_incident(
            user_id=current_user.user_id,
            incident_id=incident_id,
            eta_minutes=request.eta_minutes,
        )
        return ResponderAssignmentResponse.model_validate(assignment)

    except ResponderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/incidents/{incident_id}/decline",
    response_model=ResponderAssignmentResponse,
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def decline_incident(
    incident_id: str,
    request: IncidentDeclineRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Decline an incident assignment with reason."""
    responder_service = ResponderService(db)

    try:
        assignment = await responder_service.decline_incident(
            user_id=current_user.user_id,
            incident_id=incident_id,
            reason=request.reason,
        )
        return ResponderAssignmentResponse.model_validate(assignment)

    except ResponderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/incidents/{incident_id}/en-route",
    response_model=ResponderAssignmentResponse,
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def mark_en_route(
    incident_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Mark responder as en route to incident."""
    responder_service = ResponderService(db)

    try:
        assignment = await responder_service.update_en_route(
            user_id=current_user.user_id,
            incident_id=incident_id,
        )
        return ResponderAssignmentResponse.model_validate(assignment)

    except ResponderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/incidents/{incident_id}/arrived",
    response_model=ResponderAssignmentResponse,
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def mark_arrived(
    incident_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Mark responder as arrived at incident location."""
    responder_service = ResponderService(db)

    try:
        assignment = await responder_service.update_arrived(
            user_id=current_user.user_id,
            incident_id=incident_id,
        )
        return ResponderAssignmentResponse.model_validate(assignment)

    except ResponderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/my-assignments",
    response_model=list[ResponderAssignmentResponse],
    dependencies=[Depends(require_permission(Permission.ACCEPT_INCIDENTS))],
)
async def get_my_assignments(
    current_user: AuthenticatedUser,
    db: DBSession,
    active_only: Annotated[bool, Query()] = True,
):
    """Get responder's incident assignments."""
    responder_service = ResponderService(db)

    assignments = await responder_service.get_my_assignments(
        user_id=current_user.user_id,
        active_only=active_only,
    )

    return [ResponderAssignmentResponse.model_validate(a) for a in assignments]
