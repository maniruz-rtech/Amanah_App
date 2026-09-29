"""
Responder availability and status schemas.
"""

from datetime import datetime

from pydantic import Field

from app.schemas.common import BaseSchema, TimestampMixin


# ─────────────────────────────────────────────────────────────────────────────
# Availability
# ─────────────────────────────────────────────────────────────────────────────


class AvailabilityUpdateRequest(BaseSchema):
    """Update responder availability."""

    is_available: bool
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    battery_level: int | None = Field(default=None, ge=0, le=100)


class AvailabilityResponse(BaseSchema):
    """Responder availability status."""

    user_id: str
    is_available: bool
    last_lat: float | None
    last_lng: float | None
    last_location_at: datetime | None
    battery_level: int | None
    active_incident_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Nearby Incidents
# ─────────────────────────────────────────────────────────────────────────────


class NearbyIncidentItem(BaseSchema):
    """Nearby incident for responder."""

    incident_id: str
    distance_m: int  # Rounded to 500m for privacy before acceptance
    severity: str
    incident_type: str
    created_at: datetime


class NearbyIncidentsResponse(BaseSchema):
    """List of nearby incidents for responder."""

    items: list[NearbyIncidentItem]
    total: int


# Aliases for backward compatibility
AvailabilityUpdate = AvailabilityUpdateRequest
NearbyIncidentResponse = NearbyIncidentsResponse

# Import incident-related schemas that are used in responder endpoints
from app.schemas.incident import (
    AcceptIncidentRequest as IncidentAcceptRequest,
    AcceptIncidentResponse,
    DeclineIncidentRequest as IncidentDeclineRequest,
    DeclineIncidentResponse,
)

# Create ResponderAssignmentResponse alias
class ResponderAssignmentResponse(BaseSchema):
    """Response for responder assignment to incident."""
    incident_id: str
    responder_id: str
    status: str
    message: str = "Successfully assigned to incident"
