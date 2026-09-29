"""
Responder repository for availability and nearby queries.
"""

from datetime import UTC, datetime

from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint, ST_SetSRID
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.base import generate_ulid
from app.db.enums import AssignmentStatus, IncidentStatus
from app.db.models import (
    EmergencyLocation,
    Incident,
    IncidentAssignment,
    ResponderStatus,
    Role,
    User,
    UserRole,
)
from app.repositories.base import BaseRepository


class ResponderRepository(BaseRepository[ResponderStatus]):
    """Repository for Responder operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(ResponderStatus, db)

    async def get_or_create(self, user_id: str) -> ResponderStatus:
        """Get or create responder status for a user."""
        result = await self.db.execute(
            select(ResponderStatus).where(ResponderStatus.user_id == user_id)
        )
        status = result.scalar_one_or_none()

        if not status:
            status = ResponderStatus(
                id=generate_ulid("rstat_"),
                user_id=user_id,
                is_available=False,
            )
            self.db.add(status)
            await self.db.flush()
            await self.db.refresh(status)

        return status

    async def update_availability(
        self,
        user_id: str,
        is_available: bool,
        lat: float | None = None,
        lng: float | None = None,
        battery_level: int | None = None,
    ) -> ResponderStatus:
        """Update responder availability and location."""
        status = await self.get_or_create(user_id)

        status.is_available = is_available

        if lat is not None and lng is not None:
            status.last_lat = lat
            status.last_lng = lng
            status.location = ST_SetSRID(ST_MakePoint(lng, lat), 4326)
            status.last_location_at = datetime.now(UTC)

        if battery_level is not None:
            status.battery_level = battery_level

        await self.db.flush()
        await self.db.refresh(status)
        return status

    async def find_nearby_responders(
        self,
        lat: float,
        lng: float,
        organization_id: str,
        region_id: str | None = None,
        radius_km: float | None = None,
        limit: int = 25,
        exclude_user_ids: list[str] | None = None,
    ) -> list[tuple[ResponderStatus, float]]:
        """
        Find nearby available responders using PostGIS.

        Returns list of (ResponderStatus, distance_meters) tuples sorted by distance.
        """
        if radius_km is None:
            radius_km = settings.responder_search_radius_km

        radius_m = radius_km * 1000
        point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)

        # Build query
        query = (
            select(
                ResponderStatus,
                ST_Distance(ResponderStatus.location, point).label("distance_m"),
            )
            .join(User, User.id == ResponderStatus.user_id)
            .where(
                and_(
                    ResponderStatus.is_available == True,
                    ResponderStatus.location.isnot(None),
                    User.is_active == True,
                    User.is_suspended == False,
                    User.organization_id == organization_id,
                    # Only users holding the "responder" role (EXISTS keeps one row per user)
                    exists().where(
                        and_(
                            UserRole.user_id == User.id,
                            UserRole.role_id == Role.id,
                            Role.name == "responder",
                        )
                    ),
                    # Within radius
                    ST_DWithin(ResponderStatus.location, point, radius_m),
                )
            )
        )

        # Optionally filter by region
        if region_id:
            query = query.where(User.region_id == region_id)

        # Exclude specific users
        if exclude_user_ids:
            query = query.where(~ResponderStatus.user_id.in_(exclude_user_ids))

        # Order by distance, then by location freshness
        query = (
            query
            .order_by(
                ST_Distance(ResponderStatus.location, point),
                ResponderStatus.last_location_at.desc(),
            )
            .limit(limit)
        )

        result = await self.db.execute(query)
        return [(row.ResponderStatus, row.distance_m) for row in result.all()]

    async def get_nearby_incidents_for_responder(
        self,
        user_id: str,
        lat: float,
        lng: float,
        organization_id: str,
        radius_km: float | None = None,
        limit: int = 20,
    ) -> list[tuple[Incident, float]]:
        """
        Find nearby active incidents for a responder.

        Returns list of (Incident, distance_meters) tuples.
        """
        if radius_km is None:
            radius_km = settings.responder_search_radius_km

        radius_m = radius_km * 1000
        point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)

        # Active incident statuses
        active_statuses = [
            IncidentStatus.BROADCASTING,
            IncidentStatus.ACCEPTED,
        ]

        # Subquery to get latest location for each incident
        latest_location = (
            select(
                EmergencyLocation.incident_id,
                func.max(EmergencyLocation.captured_at).label("latest_captured"),
            )
            .group_by(EmergencyLocation.incident_id)
            .subquery()
        )

        # Main query
        query = (
            select(
                Incident,
                ST_Distance(EmergencyLocation.location, point).label("distance_m"),
            )
            .join(
                EmergencyLocation,
                EmergencyLocation.incident_id == Incident.id,
            )
            .join(
                latest_location,
                and_(
                    EmergencyLocation.incident_id == latest_location.c.incident_id,
                    EmergencyLocation.captured_at == latest_location.c.latest_captured,
                ),
            )
            .where(
                and_(
                    Incident.organization_id == organization_id,
                    Incident.status.in_(active_statuses),
                    Incident.created_by_id != user_id,  # Cannot accept own incident
                    ST_DWithin(EmergencyLocation.location, point, radius_m),
                )
            )
            .order_by(ST_Distance(EmergencyLocation.location, point))
            .limit(limit)
        )

        result = await self.db.execute(query)
        return [(row.Incident, row.distance_m) for row in result.all()]

    async def increment_active_incident_count(self, user_id: str) -> None:
        """Increment active incident count for responder."""
        status = await self.get_or_create(user_id)
        status.active_incident_count += 1
        await self.db.flush()

    async def decrement_active_incident_count(self, user_id: str) -> None:
        """Decrement active incident count for responder."""
        status = await self.get_or_create(user_id)
        if status.active_incident_count > 0:
            status.active_incident_count -= 1
        await self.db.flush()
