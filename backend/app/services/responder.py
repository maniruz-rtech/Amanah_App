"""
Responder service for availability and incident response.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    IncidentNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ResponderNotFoundError,
)
from app.db.enums import (
    AssignmentStatus,
    IncidentStatus,
    NotificationType,
    is_valid_transition,
)
from app.db.models import Incident, IncidentAssignment, ResponderStatus
from app.repositories import (
    AuditLogRepository,
    IncidentAssignmentRepository,
    IncidentRepository,
    NotificationRepository,
    ResponderRepository,
)
from app.schemas.responder import (
    AvailabilityResponse,
    AvailabilityUpdateRequest as AvailabilityUpdate,
    NearbyIncidentsResponse as NearbyIncidentResponse,
)

logger = structlog.get_logger()


class ResponderService:
    """Service for responder operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.responder_repo = ResponderRepository(db)
        self.incident_repo = IncidentRepository(db)
        self.assignment_repo = IncidentAssignmentRepository(db)
        self.notification_repo = NotificationRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def get_availability(self, user_id: str) -> AvailabilityResponse:
        """Get responder availability status."""
        status = await self.responder_repo.get_or_create(user_id)
        return AvailabilityResponse(
            is_available=status.is_available,
            last_lat=status.last_lat,
            last_lng=status.last_lng,
            last_location_at=status.last_location_at,
            active_incident_count=status.active_incident_count,
            battery_level=status.battery_level,
        )

    async def update_availability(
        self,
        user_id: str,
        update: AvailabilityUpdate,
    ) -> AvailabilityResponse:
        """Update responder availability and location."""
        status = await self.responder_repo.update_availability(
            user_id=user_id,
            is_available=update.is_available,
            lat=update.lat,
            lng=update.lng,
            battery_level=update.battery_level,
        )

        await logger.ainfo(
            "availability_updated",
            user_id=user_id,
            is_available=update.is_available,
        )

        return AvailabilityResponse(
            is_available=status.is_available,
            last_lat=status.last_lat,
            last_lng=status.last_lng,
            last_location_at=status.last_location_at,
            active_incident_count=status.active_incident_count,
            battery_level=status.battery_level,
        )

    async def get_nearby_incidents(
        self,
        user_id: str,
        organization_id: str,
        lat: float,
        lng: float,
        radius_km: float | None = None,
    ) -> list[NearbyIncidentResponse]:
        """Get nearby active incidents for responder."""
        incidents = await self.responder_repo.get_nearby_incidents_for_responder(
            user_id=user_id,
            lat=lat,
            lng=lng,
            organization_id=organization_id,
            radius_km=radius_km,
        )

        return [
            NearbyIncidentResponse(
                incident_id=incident.id,
                incident_type=incident.incident_type,
                severity=incident.severity,
                status=incident.status,
                distance_m=int(distance_m) if distance_m else None,
                created_at=incident.created_at,
            )
            for incident, distance_m in incidents
        ]

    async def accept_incident(
        self,
        user_id: str,
        incident_id: str,
        eta_minutes: int,
    ) -> IncidentAssignment:
        """Accept an incident assignment."""
        # Get assignment
        assignment = await self.assignment_repo.get_assignment(incident_id, user_id)
        if not assignment:
            raise ResponderNotFoundError("No assignment found for this incident")

        if assignment.status != AssignmentStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot accept assignment in {assignment.status} status"
            )

        # Get incident
        incident = await self.incident_repo.get_by_id(incident_id)
        if not incident:
            raise IncidentNotFoundError()

        # Accept assignment
        assignment = await self.assignment_repo.accept_assignment(
            assignment_id=assignment.id,
            eta_minutes=eta_minutes,
        )

        # Update incident status if this is first accept
        if incident.status == IncidentStatus.BROADCASTING:
            await self.incident_repo.update_status(
                incident_id=incident_id,
                new_status=IncidentStatus.ACCEPTED,
                actor_user_id=user_id,
            )

        # Increment active incident count
        await self.responder_repo.increment_active_incident_count(user_id)

        # Notify incident creator
        await self.notification_repo.create_notification(
            user_id=incident.created_by_id,
            notification_type=NotificationType.RESPONDER_ACCEPTED,
            title="Help is on the way!",
            body=f"A responder has accepted and will arrive in ~{eta_minutes} minutes.",
            incident_id=incident_id,
        )

        await self.audit_repo.log_action(
            action="incident_accepted",
            resource_type="incident_assignment",
            resource_id=assignment.id,
            actor_user_id=user_id,
            metadata={"incident_id": incident_id, "eta_minutes": eta_minutes},
        )

        await logger.ainfo(
            "incident_accepted",
            incident_id=incident_id,
            responder_id=user_id,
            eta_minutes=eta_minutes,
        )

        return assignment

    async def decline_incident(
        self,
        user_id: str,
        incident_id: str,
        reason: str,
    ) -> IncidentAssignment:
        """Decline an incident assignment."""
        assignment = await self.assignment_repo.get_assignment(incident_id, user_id)
        if not assignment:
            raise ResponderNotFoundError("No assignment found for this incident")

        if assignment.status != AssignmentStatus.PENDING:
            raise InvalidStateTransitionError(
                f"Cannot decline assignment in {assignment.status} status"
            )

        assignment = await self.assignment_repo.decline_assignment(
            assignment_id=assignment.id,
            reason=reason,
        )

        await self.audit_repo.log_action(
            action="incident_declined",
            resource_type="incident_assignment",
            resource_id=assignment.id,
            actor_user_id=user_id,
            metadata={"incident_id": incident_id, "reason": reason},
        )

        await logger.ainfo(
            "incident_declined",
            incident_id=incident_id,
            responder_id=user_id,
            reason=reason,
        )

        return assignment

    async def update_en_route(
        self,
        user_id: str,
        incident_id: str,
    ) -> IncidentAssignment:
        """Mark responder as en route."""
        assignment = await self.assignment_repo.get_assignment(incident_id, user_id)
        if not assignment:
            raise ResponderNotFoundError("No assignment found for this incident")

        if assignment.status != AssignmentStatus.ACCEPTED:
            raise InvalidStateTransitionError(
                f"Cannot mark en_route from {assignment.status} status"
            )

        assignment = await self.assignment_repo.update_assignment_status(
            assignment_id=assignment.id,
            status=AssignmentStatus.EN_ROUTE,
        )

        # Update incident status
        incident = await self.incident_repo.get_by_id(incident_id)
        if incident and incident.status == IncidentStatus.ACCEPTED:
            await self.incident_repo.update_status(
                incident_id=incident_id,
                new_status=IncidentStatus.EN_ROUTE,
                actor_user_id=user_id,
            )

        # Notify incident creator
        await self.notification_repo.create_notification(
            user_id=incident.created_by_id,
            notification_type=NotificationType.INCIDENT_UPDATE,
            title="Responder en route",
            body="A responder is now on their way to your location.",
            incident_id=incident_id,
        )

        await logger.ainfo(
            "responder_en_route",
            incident_id=incident_id,
            responder_id=user_id,
        )

        return assignment

    async def update_arrived(
        self,
        user_id: str,
        incident_id: str,
    ) -> IncidentAssignment:
        """Mark responder as arrived."""
        assignment = await self.assignment_repo.get_assignment(incident_id, user_id)
        if not assignment:
            raise ResponderNotFoundError("No assignment found for this incident")

        if assignment.status != AssignmentStatus.EN_ROUTE:
            raise InvalidStateTransitionError(
                f"Cannot mark arrived from {assignment.status} status"
            )

        assignment = await self.assignment_repo.update_assignment_status(
            assignment_id=assignment.id,
            status=AssignmentStatus.ARRIVED,
        )

        # Update incident status
        incident = await self.incident_repo.get_by_id(incident_id)
        if incident and incident.status == IncidentStatus.EN_ROUTE:
            await self.incident_repo.update_status(
                incident_id=incident_id,
                new_status=IncidentStatus.ARRIVED,
                actor_user_id=user_id,
            )

        # Notify incident creator
        await self.notification_repo.create_notification(
            user_id=incident.created_by_id,
            notification_type=NotificationType.RESPONDER_ARRIVED,
            title="Responder arrived",
            body="A responder has arrived at your location.",
            incident_id=incident_id,
        )

        await logger.ainfo(
            "responder_arrived",
            incident_id=incident_id,
            responder_id=user_id,
        )

        return assignment

    async def get_my_assignments(
        self,
        user_id: str,
        active_only: bool = True,
    ) -> list[IncidentAssignment]:
        """Get responder's incident assignments."""
        from sqlalchemy import select
        from app.db.models import IncidentAssignment

        query = select(IncidentAssignment).where(
            IncidentAssignment.responder_id == user_id
        )

        if active_only:
            active_statuses = [
                AssignmentStatus.PENDING,
                AssignmentStatus.ACCEPTED,
                AssignmentStatus.EN_ROUTE,
                AssignmentStatus.ARRIVED,
            ]
            query = query.where(IncidentAssignment.status.in_(active_statuses))

        query = query.order_by(IncidentAssignment.assigned_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())
