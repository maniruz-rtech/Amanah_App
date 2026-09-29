"""
Incident/SOS API endpoints.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import (
    AuthenticatedUser,
    DBSession,
    require_any_permission,
)
from app.core.exceptions import (
    IncidentNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
)
from app.core.permissions import Permission
from app.schemas.common import PaginatedResponse
from app.schemas.incident import (
    IncidentCancelRequest,
    IncidentDetailResponse,
    IncidentListResponse,
    IncidentResolveRequest,
    LocationUpdate,
    SOSRequest,
    SOSResponse,
)
from app.services import IncidentService

logger = structlog.get_logger()

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.post("/sos", response_model=SOSResponse, status_code=status.HTTP_201_CREATED)
async def create_sos(
    request: SOSRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Create an SOS emergency incident.

    Immediately broadcasts to nearby responders.
    """
    if not current_user.organization_id or not current_user.region_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must be assigned to an organization and region",
        )

    incident_service = IncidentService(db)

    return await incident_service.create_sos(
        user_id=current_user.user_id,
        organization_id=current_user.organization_id,
        region_id=current_user.region_id,
        request=request,
    )


@router.get("/my/active", response_model=list[IncidentListResponse])
async def get_my_active_incidents(
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """Get user's active (non-resolved) incidents."""
    incident_service = IncidentService(db)
    incidents = await incident_service.get_user_active_incidents(current_user.user_id)
    return [IncidentListResponse.model_validate(i) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Get incident details.

    Accessible by incident creator, assigned responders, or admins.
    """
    incident_service = IncidentService(db)

    try:
        return await incident_service.get_incident(
            incident_id=incident_id,
            user_id=current_user.user_id,
        )

    except IncidentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )


@router.post("/{incident_id}/location", status_code=status.HTTP_204_NO_CONTENT)
async def update_location(
    incident_id: str,
    location: LocationUpdate,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Add location update to incident.

    Called periodically during active incident to track location.
    """
    incident_service = IncidentService(db)

    try:
        await incident_service.update_location(
            incident_id=incident_id,
            user_id=current_user.user_id,
            location=location,
        )

    except IncidentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    except PermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.post("/{incident_id}/cancel", response_model=IncidentDetailResponse)
async def cancel_incident(
    incident_id: str,
    request: IncidentCancelRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Cancel an SOS incident.

    Only the incident creator can cancel.
    """
    incident_service = IncidentService(db)

    try:
        incident = await incident_service.cancel_sos(
            incident_id=incident_id,
            user_id=current_user.user_id,
            reason=request.reason,
        )
        return IncidentDetailResponse.model_validate(incident)

    except IncidentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    except PermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{incident_id}/resolve", response_model=IncidentDetailResponse)
async def resolve_incident(
    incident_id: str,
    request: IncidentResolveRequest,
    current_user: AuthenticatedUser,
    db: DBSession,
):
    """
    Resolve an incident.

    Can be done by creator or arrived responder.
    """
    incident_service = IncidentService(db)

    try:
        incident = await incident_service.resolve_incident(
            incident_id=incident_id,
            user_id=current_user.user_id,
            resolution_note=request.resolution_note,
        )
        return IncidentDetailResponse.model_validate(incident)

    except IncidentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    except PermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Admin endpoints
@router.get(
    "/region/{region_id}",
    response_model=PaginatedResponse,
    dependencies=[Depends(require_any_permission(Permission.VIEW_ALL_INCIDENTS, Permission.VIEW_ALL_INCIDENTS))],
)
async def get_region_incidents(
    region_id: str,
    current_user: AuthenticatedUser,
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """
    Get active incidents for a region (admin view).

    Requires VIEW_INCIDENTS or MANAGE_INCIDENTS permission.
    """
    # Regional admins can only see their own region
    from app.core.permissions import has_permission, Role

    if not has_permission(current_user.roles, Permission.MANAGE_ALL_REGIONS):
        if current_user.region_id != region_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot view incidents outside your region",
            )

    incident_service = IncidentService(db)
    incidents, total = await incident_service.get_region_active_incidents(
        region_id=region_id,
        skip=skip,
        limit=limit,
    )

    return PaginatedResponse(
        items=[IncidentListResponse.model_validate(i) for i in incidents],
        total=total,
        skip=skip,
        limit=limit,
    )
