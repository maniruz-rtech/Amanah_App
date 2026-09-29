"""
Incident service for SOS/emergency operations.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    IncidentNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ResponderNotFoundError,
)
from app.db.enums import (
    AssignmentStatus,
    IncidentEventType,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    LocationSource,
    NotificationType,
    is_valid_transition,
)
from app.db.models import Incident, IncidentAssignment
from app.repositories import (
    AuditLogRepository,
    IncidentAssignmentRepository,
    IncidentRepository,
    NotificationRepository,
    ResponderRepository,
)
from app.schemas.incident import (
    IncidentDetailResponse,
    LocationUpdateRequest,
    SOSCreateRequest as SOSRequest,
    SOSCreateResponse as SOSResponse,
)

logger = structlog.get_logger()


class IncidentService:
    """Service for incident/emergency operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_repo = IncidentRepository(db)
        self.assignment_repo = IncidentAssignmentRepository(db)
        self.responder_repo = ResponderRepository(db)
        self.notification_repo = NotificationRepository(db)
        self.audit_repo = AuditLogRepository(db)

    async def create_sos(
        self,
        user_id: str,
        organization_id: str,
        region_id: str,
        request: SOSRequest,
    ) -> SOSResponse:
        """Create a new SOS incident."""
        incident = await self.incident_repo.create_sos(
            user_id=user_id,
            organization_id=organization_id,
            region_id=region_id,
            lat=request.lat,
            lng=request.lng,
            incident_type=request.incident_type or IncidentType.SOS,
            severity=request.severity or IncidentSeverity.HIGH,
            silent_mode=request.silent_mode or False,
            note=request.note,
            accuracy_m=request.accuracy_m,
            battery_level=request.battery_level,
        )

        await self.audit_repo.log_action(
            action="sos_created",
            resource_type="incident",
            resource_id=incident.id,
            actor_user_id=user_id,
            metadata={
                "lat": request.lat,
                "lng": request.lng,
                "silent_mode": request.silent_mode,
            },
        )

        await logger.ainfo(
            "sos_created",
            incident_id=incident.id,
            user_id=user_id,
            lat=request.lat,
            lng=request.lng,
        )

        # Broadcast to nearby responders (async task in production)
        await self._broadcast_to_responders(incident)

        return SOSResponse(
            incident_id=incident.id,
            status=incident.status,
            created_at=incident.created_at,
        )

    async def get_incident(
        self,
        incident_id: str,
        user_id: str,
    ) -> IncidentDetailResponse:
        """Get incident details."""
        incident = await self.incident_repo.get_with_details(incident_id)
        if not incident:
            raise IncidentNotFoundError()

        # Check access - creator, assigned responder, or admin
        has_access = incident.created_by_id == user_id
        if not has_access and incident.assignments:
            has_access = any(a.responder_id == user_id for a in incident.assignments)

        # Admins checked at router level

        return IncidentDetailResponse.model_validate(incident)

    async def update_location(
        self,
        incident_id: str,
        user_id: str,
        location: LocationUpdateRequest,
    ) -> None:
        """Add location update to incident."""
        incident = await self.incident_repo.get_by_id(incident_id)
        if not incident:
            raise IncidentNotFoundError()

        # Only creator or assigned responder can update location
        if incident.created_by_id != user_id:
            # Check if responder
            assignment = await self.assignment_repo.get_assignment(incident_id, user_id)
            if not assignment or assignment.status not in [
                AssignmentStatus.ACCEPTED,
                AssignmentStatus.EN_ROUTE,
                AssignmentStatus.ARRIVED,
            ]:
                raise PermissionDeniedError("Not authorized to update location")

        await self.incident_repo.add_location(
            incident_id=incident_id,
            user_id=user_id,
            lat=location.lat,
            lng=location.lng,
            accuracy_m=location.accuracy_m,
            source=location.source or LocationSource.GPS,
            battery_level=location.battery_level,
        )

        await logger.ainfo(
            "location_updated",
            incident_id=incident_id,
            user_id=user_id,
        )

    async def cancel_sos(
        self,
        incident_id: str,
        user_id: str,
        reason: str | None = None,
    ) -> Incident:
        """Cancel an SOS incident."""
        incident = await self.incident_repo.get_by_id(incident_id)
        if not incident:
            raise IncidentNotFoundError()

        # Only creator can cancel
        if incident.created_by_id != user_id:
            raise PermissionDeniedError("Only creator can cancel incident")

        if not is_valid_transition(incident.status, IncidentStatus.CANCELED):
            raise InvalidStateTransitionError(
                f"Cannot cancel incident in {incident.status} status"
            )

        incident = await self.incident_repo.update_status(
            incident_id=incident_id,
            new_status=IncidentStatus.CANCELED,
            actor_user_id=user_id,
            note=reason,
        )

        # Notify assigned responders
        await self._notify_responders_of_cancellation(incident)

        await self.audit_repo.log_action(
            action="sos_canceled",
            resource_type="incident",
            resource_id=incident_id,
            actor_user_id=user_id,
            metadata={"reason": reason},
        )

        await logger.ainfo("sos_canceled", incident_id=incident_id, user_id=user_id)
        return incident

    async def resolve_incident(
        self,
        incident_id: str,
        user_id: str,
        resolution_note: str | None = None,
    ) -> Incident:
        """Resolve an incident."""
        incident = await self.incident_repo.get_by_id(incident_id)
        if not incident:
            raise IncidentNotFoundError()

        # Creator or assigned responder can resolve
        can_resolve = incident.created_by_id == user_id
        if not can_resolve:
            assignment = await self.assignment_repo.get_assignment(incident_id, user_id)
            can_resolve = assignment and assignment.status == AssignmentStatus.ARRIVED

        if not can_resolve:
            raise PermissionDeniedError("Not authorized to resolve incident")

        if not is_valid_transition(incident.status, IncidentStatus.RESOLVED):
            raise InvalidStateTransitionError(
                f"Cannot resolve incident in {incident.status} status"
            )

        incident = await self.incident_repo.update_status(
            incident_id=incident_id,
            new_status=IncidentStatus.RESOLVED,
            actor_user_id=user_id,
            note=resolution_note,
        )

        # Update responder stats
        if incident.assignments:
            for assignment in incident.assignments:
                if assignment.status == AssignmentStatus.ARRIVED:
                    await self.responder_repo.decrement_active_incident_count(
                        assignment.responder_id
                    )

        await self.audit_repo.log_action(
            action="incident_resolved",
            resource_type="incident",
            resource_id=incident_id,
            actor_user_id=user_id,
            metadata={"resolution_note": resolution_note},
        )

        await logger.ainfo("incident_resolved", incident_id=incident_id, user_id=user_id)
        return incident

    async def get_user_active_incidents(
        self,
        user_id: str,
    ) -> list[Incident]:
        """Get active incidents created by user."""
        active_statuses = [
            IncidentStatus.BROADCASTING,
            IncidentStatus.ACCEPTED,
            IncidentStatus.EN_ROUTE,
            IncidentStatus.ARRIVED,
        ]

        incidents = await self.incident_repo.list(
            filters={
                "created_by_id": user_id,
            },
            order_by="created_at",
            order_desc=True,
        )

        return [i for i in incidents if i.status in active_statuses]

    async def get_region_active_incidents(
        self,
        region_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Incident], int]:
        """Get active incidents for a region (admin view)."""
        return await self.incident_repo.get_active_incidents_for_region(
            region_id=region_id,
            skip=skip,
            limit=limit,
        )

    async def _broadcast_to_responders(self, incident: Incident) -> None:
        """Find and notify nearby responders."""
        # Get latest location
        # For initial SOS, the location is created with the incident
        from sqlalchemy import select
        from app.db.models import EmergencyLocation

        result = await self.db.execute(
            select(EmergencyLocation)
            .where(EmergencyLocation.incident_id == incident.id)
            .order_by(EmergencyLocation.captured_at.desc())
            .limit(1)
        )
        location = result.scalar_one_or_none()

        if not location:
            await logger.awarning("no_location_for_broadcast", incident_id=incident.id)
            return

        # Find nearby responders
        nearby_responders = await self.responder_repo.find_nearby_responders(
            lat=location.lat,
            lng=location.lng,
            organization_id=incident.organization_id,
            region_id=incident.region_id,
            limit=settings.broadcast_responder_limit,
        )

        if not nearby_responders:
            await logger.awarning("no_nearby_responders", incident_id=incident.id)
            # TODO: Escalate to authorities if configured
            return

        # Create assignments and notifications
        for responder_status, distance_m in nearby_responders:
            await self.assignment_repo.assign_responder(
                incident_id=incident.id,
                responder_id=responder_status.user_id,
                distance_m=int(distance_m) if distance_m else None,
            )

            await self.notification_repo.create_notification(
                user_id=responder_status.user_id,
                notification_type=NotificationType.INCIDENT_ASSIGNED,
                title="Emergency Alert",
                body="Someone nearby needs help. Tap to respond.",
                incident_id=incident.id,
            )

        await logger.ainfo(
            "broadcast_sent",
            incident_id=incident.id,
            responder_count=len(nearby_responders),
        )

    async def _notify_responders_of_cancellation(self, incident: Incident) -> None:
        """Notify assigned responders that incident was canceled."""
        incident_with_assignments = await self.incident_repo.get_with_details(incident.id)
        if not incident_with_assignments or not incident_with_assignments.assignments:
            return

        for assignment in incident_with_assignments.assignments:
            if assignment.status in [
                AssignmentStatus.PENDING,
                AssignmentStatus.ACCEPTED,
                AssignmentStatus.EN_ROUTE,
            ]:
                await self.notification_repo.create_notification(
                    user_id=assignment.responder_id,
                    notification_type=NotificationType.INCIDENT_UPDATE,
                    title="Incident Canceled",
                    body="The emergency has been canceled by the requester.",
                    incident_id=incident.id,
                )
