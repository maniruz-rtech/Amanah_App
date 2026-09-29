"""
Incident repository for incident-related database operations.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint, ST_SetSRID
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.enums import enum_value
from app.db.base import generate_ulid
from app.db.enums import (
    AssignmentStatus,
    IncidentEventType,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    LocationSource,
    is_valid_transition,
)
from app.db.models import (
    EmergencyLocation,
    Incident,
    IncidentAssignment,
    IncidentEvent,
    ResponderStatus,
    User,
)
from app.repositories.base import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    """Repository for Incident operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(Incident, db)

    async def create_sos(
        self,
        user_id: str,
        organization_id: str,
        region_id: str,
        lat: float,
        lng: float,
        incident_type: IncidentType = IncidentType.SOS,
        severity: IncidentSeverity = IncidentSeverity.HIGH,
        silent_mode: bool = False,
        note: str | None = None,
        accuracy_m: int | None = None,
        battery_level: int | None = None,
    ) -> Incident:
        """Create a new SOS incident with initial location."""
        now = datetime.now(UTC)

        # Create incident
        incident = Incident(
            id=generate_ulid("inc_"),
            organization_id=organization_id,
            region_id=region_id,
            created_by_id=user_id,
            incident_type=incident_type,
            severity=severity,
            status=IncidentStatus.BROADCASTING,
            silent_mode=silent_mode,
            note=note,
            started_at=now,
        )
        self.db.add(incident)
        await self.db.flush()

        # Create initial location
        location = EmergencyLocation(
            id=generate_ulid("loc_"),
            incident_id=incident.id,
            user_id=user_id,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            location=ST_SetSRID(ST_MakePoint(lng, lat), 4326),
            source=LocationSource.GPS,
            captured_at=now,
            expires_at=now + timedelta(days=settings.incident_location_expiry_days),
            battery_level=battery_level,
        )
        self.db.add(location)

        # Create event
        event = IncidentEvent(
            id=generate_ulid("evt_"),
            incident_id=incident.id,
            actor_user_id=user_id,
            event_type=IncidentEventType.CREATED,
            event_payload={"lat": lat, "lng": lng, "silent_mode": silent_mode},
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(incident)
        return incident

    async def get_with_details(self, incident_id: str) -> Incident | None:
        """Get incident with all relations loaded."""
        result = await self.db.execute(
            select(Incident)
            .options(
                selectinload(Incident.created_by),
                selectinload(Incident.region),
                selectinload(Incident.organization),
                selectinload(Incident.locations),
                selectinload(Incident.assignments).selectinload(IncidentAssignment.responder),
                selectinload(Incident.events),
            )
            .where(Incident.id == incident_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        incident_id: str,
        new_status: IncidentStatus,
        actor_user_id: str | None = None,
        note: str | None = None,
    ) -> Incident | None:
        """Update incident status with validation."""
        incident = await self.get_by_id(incident_id)
        if not incident:
            return None

        # Validate transition
        if not is_valid_transition(incident.status, new_status):
            raise ValueError(f"Invalid transition from {incident.status} to {new_status}")

        now = datetime.now(UTC)
        old_status = incident.status
        incident.status = new_status

        if new_status == IncidentStatus.RESOLVED:
            incident.resolved_at = now
            incident.resolution_note = note
        elif new_status == IncidentStatus.CANCELED:
            incident.canceled_at = now
            incident.cancel_reason = note

        # Log event
        event = IncidentEvent(
            id=generate_ulid("evt_"),
            incident_id=incident_id,
            actor_user_id=actor_user_id,
            event_type=IncidentEventType.STATUS_UPDATED,
            event_payload={"old_status": enum_value(old_status), "new_status": enum_value(new_status)},
            description=note,
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(incident)
        return incident

    async def add_location(
        self,
        incident_id: str,
        user_id: str,
        lat: float,
        lng: float,
        accuracy_m: int | None = None,
        source: LocationSource = LocationSource.GPS,
        battery_level: int | None = None,
    ) -> EmergencyLocation:
        """Add a location update to an incident."""
        now = datetime.now(UTC)

        location = EmergencyLocation(
            id=generate_ulid("loc_"),
            incident_id=incident_id,
            user_id=user_id,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            location=ST_SetSRID(ST_MakePoint(lng, lat), 4326),
            source=source,
            captured_at=now,
            expires_at=now + timedelta(days=settings.incident_location_expiry_days),
            battery_level=battery_level,
        )
        self.db.add(location)

        # Log event
        event = IncidentEvent(
            id=generate_ulid("evt_"),
            incident_id=incident_id,
            actor_user_id=user_id,
            event_type=IncidentEventType.LOCATION_UPDATED,
            event_payload={"lat": lat, "lng": lng, "accuracy_m": accuracy_m},
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(location)
        return location

    async def get_active_incidents_for_region(
        self,
        region_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Incident], int]:
        """Get active incidents for a region."""
        active_statuses = [
            IncidentStatus.BROADCASTING,
            IncidentStatus.ACCEPTED,
            IncidentStatus.EN_ROUTE,
            IncidentStatus.ARRIVED,
        ]

        query = (
            select(Incident)
            .options(
                selectinload(Incident.created_by),
                selectinload(Incident.assignments),
            )
            .where(
                and_(
                    Incident.region_id == region_id,
                    Incident.status.in_(active_statuses),
                )
            )
            .order_by(Incident.created_at.desc())
        )

        # Count
        count_query = select(func.count(Incident.id)).where(
            and_(
                Incident.region_id == region_id,
                Incident.status.in_(active_statuses),
            )
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        incidents = list(result.scalars().all())

        return incidents, total

    async def get_expired_broadcasting_incidents(
        self,
        timeout_seconds: int | None = None,
    ) -> list[Incident]:
        """Get incidents that have been broadcasting beyond timeout."""
        if timeout_seconds is None:
            timeout_seconds = settings.incident_escalation_timeout_seconds

        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)

        result = await self.db.execute(
            select(Incident)
            .where(
                and_(
                    Incident.status == IncidentStatus.BROADCASTING,
                    Incident.started_at < cutoff,
                )
            )
        )
        return list(result.scalars().all())


class IncidentAssignmentRepository(BaseRepository[IncidentAssignment]):
    """Repository for IncidentAssignment operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(IncidentAssignment, db)

    async def assign_responder(
        self,
        incident_id: str,
        responder_id: str,
        distance_m: int | None = None,
    ) -> IncidentAssignment:
        """Assign a responder to an incident."""
        assignment = IncidentAssignment(
            id=generate_ulid("asgn_"),
            incident_id=incident_id,
            responder_id=responder_id,
            status=AssignmentStatus.PENDING,
            assigned_at=datetime.now(UTC),
            distance_m=distance_m,
        )
        self.db.add(assignment)

        # Log event
        event = IncidentEvent(
            id=generate_ulid("evt_"),
            incident_id=incident_id,
            actor_user_id=None,  # System action
            event_type=IncidentEventType.RESPONDER_ASSIGNED,
            event_payload={"responder_id": responder_id, "distance_m": distance_m},
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def get_assignment(
        self,
        incident_id: str,
        responder_id: str,
    ) -> IncidentAssignment | None:
        """Get specific assignment."""
        result = await self.db.execute(
            select(IncidentAssignment).where(
                and_(
                    IncidentAssignment.incident_id == incident_id,
                    IncidentAssignment.responder_id == responder_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def accept_assignment(
        self,
        assignment_id: str,
        eta_minutes: int,
    ) -> IncidentAssignment | None:
        """Accept an incident assignment."""
        assignment = await self.get_by_id(assignment_id)
        if not assignment:
            return None

        now = datetime.now(UTC)
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.accepted_at = now
        assignment.eta_minutes = eta_minutes

        # Log event
        event = IncidentEvent(
            id=generate_ulid("evt_"),
            incident_id=assignment.incident_id,
            actor_user_id=assignment.responder_id,
            event_type=IncidentEventType.RESPONDER_ACCEPTED,
            event_payload={"eta_minutes": eta_minutes},
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def decline_assignment(
        self,
        assignment_id: str,
        reason: str,
    ) -> IncidentAssignment | None:
        """Decline an incident assignment."""
        assignment = await self.get_by_id(assignment_id)
        if not assignment:
            return None

        assignment.status = AssignmentStatus.DECLINED
        assignment.declined_at = datetime.now(UTC)
        assignment.decline_reason = reason

        # Log event
        event = IncidentEvent(
            id=generate_ulid("evt_"),
            incident_id=assignment.incident_id,
            actor_user_id=assignment.responder_id,
            event_type=IncidentEventType.RESPONDER_DECLINED,
            event_payload={"reason": reason},
        )
        self.db.add(event)

        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment

    async def update_assignment_status(
        self,
        assignment_id: str,
        status: AssignmentStatus,
    ) -> IncidentAssignment | None:
        """Update assignment status (en_route, arrived, etc.)."""
        assignment = await self.get_by_id(assignment_id)
        if not assignment:
            return None

        assignment.status = status

        if status == AssignmentStatus.ARRIVED:
            assignment.arrived_at = datetime.now(UTC)
        elif status == AssignmentStatus.COMPLETED:
            assignment.completed_at = datetime.now(UTC)

        # Map status to event type
        event_type_map = {
            AssignmentStatus.EN_ROUTE: IncidentEventType.RESPONDER_EN_ROUTE,
            AssignmentStatus.ARRIVED: IncidentEventType.RESPONDER_ARRIVED,
            AssignmentStatus.COMPLETED: IncidentEventType.RESPONDER_COMPLETED,
        }

        if status in event_type_map:
            event = IncidentEvent(
                id=generate_ulid("evt_"),
                incident_id=assignment.incident_id,
                actor_user_id=assignment.responder_id,
                event_type=event_type_map[status],
                event_payload={"status": status},
            )
            self.db.add(event)

        await self.db.flush()
        await self.db.refresh(assignment)
        return assignment
