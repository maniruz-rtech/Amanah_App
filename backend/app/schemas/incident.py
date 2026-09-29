"""
Incident and SOS schemas.
"""

from datetime import datetime

from pydantic import Field, field_validator

from app.db.enums import (
    AssignmentStatus,
    IncidentEventType,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    LocationSource,
)
from app.schemas.common import BaseSchema, PaginatedResponse, TimestampMixin


# ─────────────────────────────────────────────────────────────────────────────
# SOS Creation
# ─────────────────────────────────────────────────────────────────────────────


class SOSCreateRequest(BaseSchema):
    """Create SOS incident request."""

    incident_type: IncidentType = IncidentType.SOS
    severity: IncidentSeverity = IncidentSeverity.HIGH
    silent_mode: bool = False
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: int | None = Field(default=None, ge=0, le=10000)
    h3_cell: str | None = Field(default=None, max_length=16)
    note: str | None = Field(default=None, max_length=1000)
    battery_level: int | None = Field(default=None, ge=0, le=100)

    @field_validator("lat", "lng")
    @classmethod
    def validate_coordinates(cls, v: float) -> float:
        if v == 0:
            raise ValueError("Coordinates cannot be exactly 0")
        return v


class SOSCreateResponse(BaseSchema):
    """SOS creation response."""

    incident_id: str
    status: IncidentStatus
    created_at: datetime
    verification_pin: str | None = None  # admin-issued PIN; optional


# ─────────────────────────────────────────────────────────────────────────────
# Incident Detail
# ─────────────────────────────────────────────────────────────────────────────


class AssignedResponder(BaseSchema):
    """Responder assignment in incident detail."""

    responder_id: str
    responder_name: str
    status: AssignmentStatus
    assigned_at: datetime
    accepted_at: datetime | None
    eta_minutes: int | None
    distance_m: int | None


class IncidentLocation(BaseSchema):
    """Location data in incident detail."""

    lat: float
    lng: float
    accuracy_m: int | None
    captured_at: datetime
    source: LocationSource


class IncidentDetailResponse(BaseSchema, TimestampMixin):
    """Incident detail response."""

    id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    silent_mode: bool
    note: str | None
    created_by_id: str
    created_by_name: str
    region_id: str
    organization_id: str
    started_at: datetime
    resolved_at: datetime | None
    canceled_at: datetime | None
    cancel_reason: str | None
    resolution_note: str | None
    assigned_responders: list[AssignedResponder]
    # Location only included if user has access
    location: IncidentLocation | None = None


class IncidentListItem(BaseSchema, TimestampMixin):
    """Incident list item for responders."""

    incident_id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    distance_m: int  # Rounded to 500m for privacy
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Incident Updates
# ─────────────────────────────────────────────────────────────────────────────


class LocationUpdateRequest(BaseSchema):
    """Update incident location."""

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: int | None = Field(default=None, ge=0, le=10000)
    source: LocationSource = LocationSource.GPS
    battery_level: int | None = Field(default=None, ge=0, le=100)


class LocationUpdateResponse(BaseSchema):
    """Location update response."""

    success: bool = True
    location_id: str
    captured_at: datetime


class CancelIncidentRequest(BaseSchema):
    """Cancel incident request."""

    cancel_reason: str = Field(min_length=1, max_length=255)
    verification_pin: str = Field(min_length=4, max_length=4)

    @field_validator("verification_pin")
    @classmethod
    def validate_pin(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Verification PIN must be numeric")
        return v


class CancelIncidentResponse(BaseSchema):
    """Cancel incident response."""

    success: bool = True
    incident_id: str
    status: IncidentStatus = IncidentStatus.CANCELED
    canceled_at: datetime


class ResolveIncidentRequest(BaseSchema):
    """Resolve incident request."""

    resolution_note: str | None = Field(default=None, max_length=1000)


class ResolveIncidentResponse(BaseSchema):
    """Resolve incident response."""

    success: bool = True
    incident_id: str
    status: IncidentStatus = IncidentStatus.RESOLVED
    resolved_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Responder Actions
# ─────────────────────────────────────────────────────────────────────────────


class AcceptIncidentRequest(BaseSchema):
    """Accept incident assignment."""

    eta_minutes: int = Field(ge=1, le=120)


class AcceptIncidentResponse(BaseSchema):
    """Accept incident response with full location."""

    success: bool = True
    incident_id: str
    assignment_id: str
    location: IncidentLocation  # Full location revealed after acceptance


class DeclineIncidentRequest(BaseSchema):
    """Decline incident assignment."""

    reason: str = Field(min_length=1, max_length=255)


class DeclineIncidentResponse(BaseSchema):
    """Decline incident response."""

    success: bool = True
    incident_id: str
    assignment_id: str


class UpdateStatusRequest(BaseSchema):
    """Update responder status on incident."""

    status: AssignmentStatus


class UpdateStatusResponse(BaseSchema):
    """Update status response."""

    success: bool = True
    incident_id: str
    status: AssignmentStatus


# ─────────────────────────────────────────────────────────────────────────────
# Incident Events
# ─────────────────────────────────────────────────────────────────────────────


class IncidentEventResponse(BaseSchema):
    """Incident event for audit trail."""

    id: str
    event_type: IncidentEventType
    actor_user_id: str | None
    actor_name: str | None
    event_payload: dict | None
    description: str | None
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Admin Incident Management
# ─────────────────────────────────────────────────────────────────────────────


class AdminIncidentListItem(BaseSchema, TimestampMixin):
    """Admin incident list item."""

    id: str
    incident_type: IncidentType
    severity: IncidentSeverity
    status: IncidentStatus
    created_by_id: str
    created_by_name: str
    region_id: str
    region_name: str | None
    assigned_count: int
    accepted_count: int
    started_at: datetime
    resolved_at: datetime | None


class EscalateIncidentRequest(BaseSchema):
    """Escalate incident request."""

    note: str | None = Field(default=None, max_length=500)
    expand_radius_km: float = Field(default=10.0, ge=5, le=50)


class EscalateIncidentResponse(BaseSchema):
    """Escalate incident response."""

    success: bool = True
    incident_id: str
    new_assignments_count: int
    message: str


# Aliases for backward compatibility
IncidentCancelRequest = CancelIncidentRequest
IncidentCancelResponse = CancelIncidentResponse

IncidentListResponse = PaginatedResponse  # Uses common PaginatedResponse
IncidentResolveRequest = ResolveIncidentRequest
SOSRequest = SOSCreateRequest
SOSResponse = SOSCreateResponse
LocationUpdate = LocationUpdateRequest
