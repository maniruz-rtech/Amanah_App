"""
Geospatial matching logic for finding nearby responders and incidents.

Uses PostGIS for efficient spatial queries with distance calculations,
priority matching, and responder load balancing.
"""

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Incident, ResponderStatus, User
from app.repositories import ResponderRepository, IncidentRepository


@dataclass
class ResponderMatch:
    """Matched responder with distance and other relevant info."""

    responder_user: User
    responder_status: ResponderStatus
    distance_meters: float
    eta_minutes: int | None = None
    available_capacity: int = 1

    def __lt__(self, other: "ResponderMatch") -> bool:
        """Compare responders by distance first, then by capacity."""
        if self.distance_meters != other.distance_meters:
            return self.distance_meters < other.distance_meters
        # Prefer responders with less load
        return self.available_capacity > other.available_capacity


@dataclass
class IncidentMatch:
    """Matched incident with distance and other relevant info."""

    incident: Incident
    distance_meters: float
    minutes_since_created: float

    def __lt__(self, other: "IncidentMatch") -> bool:
        """Compare incidents by distance, then by age."""
        if self.distance_meters != other.distance_meters:
            return self.distance_meters < other.distance_meters
        # Prefer older incidents (need help sooner)
        return self.minutes_since_created > other.minutes_since_created


class GeospatialMatcher:
    """Handles geospatial matching of responders and incidents."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.responder_repo = ResponderRepository(db)
        self.incident_repo = IncidentRepository(db)

    async def find_nearby_responders(
        self,
        lat: float,
        lng: float,
        organization_id: str,
        region_id: str | None = None,
        radius_km: float | None = None,
        limit: int = 25,
        exclude_user_ids: list[str] | None = None,
        max_responders_per_incident: int = 10,
    ) -> list[ResponderMatch]:
        """
        Find nearby responders sorted by distance and capacity.

        Args:
            lat: Incident latitude
            lng: Incident longitude
            organization_id: Organization to search within
            region_id: Optional region filter
            radius_km: Search radius in kilometers
            limit: Maximum number of responders to return
            exclude_user_ids: List of user IDs to exclude
            max_responders_per_incident: Max responders to assign per incident

        Returns:
            List of ResponderMatch objects sorted by priority.
        """
        raw_matches = await self.responder_repo.find_nearby_responders(
            lat=lat,
            lng=lng,
            organization_id=organization_id,
            region_id=region_id,
            radius_km=radius_km,
            limit=limit,
            exclude_user_ids=exclude_user_ids,
        )

        matches = []
        for responder_status, distance_m in raw_matches:
            # Get responder user
            from app.repositories import UserRepository
            user_repo = UserRepository(self.db)
            user = await user_repo.get_by_id(responder_status.user_id)

            if not user:
                continue

            # Calculate available capacity (max 10 incidents per responder)
            available_capacity = max_responders_per_incident - responder_status.active_incident_count

            # Estimate ETA based on distance (assume ~60km/h = 1km/min)
            eta_minutes = int(distance_m / 1000 / 1.0) if distance_m > 0 else 1

            match = ResponderMatch(
                responder_user=user,
                responder_status=responder_status,
                distance_meters=distance_m,
                eta_minutes=eta_minutes,
                available_capacity=available_capacity,
            )
            matches.append(match)

        # Sort by distance, then by available capacity
        return sorted(matches)[:limit]

    async def find_nearby_incidents(
        self,
        responder_user_id: str,
        lat: float,
        lng: float,
        organization_id: str,
        radius_km: float | None = None,
        limit: int = 20,
    ) -> list[IncidentMatch]:
        """
        Find nearby active incidents for a responder.

        Args:
            responder_user_id: Responder user ID
            lat: Responder's current latitude
            lng: Responder's current longitude
            organization_id: Organization to search within
            radius_km: Search radius in kilometers
            limit: Maximum number of incidents to return

        Returns:
            List of IncidentMatch objects sorted by priority.
        """
        from datetime import UTC, datetime

        raw_matches = await self.responder_repo.get_nearby_incidents_for_responder(
            user_id=responder_user_id,
            lat=lat,
            lng=lng,
            organization_id=organization_id,
            radius_km=radius_km,
            limit=limit,
        )

        matches = []
        now = datetime.now(UTC)

        for incident, distance_m in raw_matches:
            minutes_since_created = (now - incident.started_at).total_seconds() / 60

            match = IncidentMatch(
                incident=incident,
                distance_meters=distance_m,
                minutes_since_created=minutes_since_created,
            )
            matches.append(match)

        # Sort by distance, then by age (older is higher priority)
        return sorted(matches)[:limit]

    async def suggest_responders_for_incident(
        self,
        incident_id: str,
        organization_id: str,
        region_id: str | None = None,
        radius_km: float | None = None,
        count: int = 10,
    ) -> list[ResponderMatch]:
        """
        Suggest responders for a specific incident.

        Considers:
        - Proximity to incident location
        - Responder availability status
        - Current workload
        - Battery level

        Args:
            incident_id: Incident to find responders for
            organization_id: Organization context
            region_id: Optional region filter
            radius_km: Search radius in km
            count: Number of responders to suggest

        Returns:
            List of ResponderMatch objects, most suitable first.
        """
        from app.repositories import IncidentRepository
        incident_repo = IncidentRepository(self.db)
        incident = await incident_repo.get_with_details(incident_id)

        if not incident or not incident.latest_location:
            return []

        # Get nearby responders
        matches = await self.find_nearby_responders(
            lat=incident.latest_location.lat,
            lng=incident.latest_location.lng,
            organization_id=organization_id,
            region_id=region_id or incident.region_id,
            radius_km=radius_km,
            limit=count * 2,  # Get more to filter
        )

        # Filter: prefer high battery, adequate capacity
        suitable = [
            m
            for m in matches
            if (
                m.responder_status.battery_level is None
                or m.responder_status.battery_level >= 20
            )  # At least 20% battery
            and m.available_capacity > 0  # Has capacity
        ]

        return suitable[:count]

    async def calculate_responder_scores(
        self,
        matches: Iterable[ResponderMatch],
        incident_lat: float,
        incident_lng: float,
    ) -> list[tuple[ResponderMatch, float]]:
        """
        Calculate priority scores for responders.

        Score considers:
        - Distance (closer is better)
        - Battery level (higher is better)
        - Workload (lower is better)

        Args:
            matches: Iterable of ResponderMatch objects
            incident_lat: Incident latitude (for distance normalization)
            incident_lng: Incident longitude

        Returns:
            List of (match, score) tuples sorted by score descending.
        """
        scores = []

        for match in matches:
            # Normalize distance (0-10 points, max 5km)
            distance_score = max(0, 10 * (1 - match.distance_meters / 5000))

            # Battery score (0-5 points)
            battery_level = match.responder_status.battery_level or 50
            battery_score = (battery_level / 100) * 5

            # Workload score (0-10 points, max 5 incidents)
            workload_score = max(0, 10 * (1 - match.responder_status.active_incident_count / 5))

            # Combined score (weighted)
            total_score = (distance_score * 0.5) + (battery_score * 0.2) + (workload_score * 0.3)

            scores.append((match, total_score))

        # Sort by score descending
        return sorted(scores, key=lambda x: x[1], reverse=True)

    async def get_responder_availability_summary(
        self,
        organization_id: str,
        region_id: str | None = None,
    ) -> dict:
        """
        Get summary of responder availability in organization/region.

        Returns:
            Dict with counts of available/offline responders and stats.
        """
        from sqlalchemy import and_, func, select
        from app.db.models import ResponderStatus, User

        query = select(
            func.sum(ResponderStatus.is_available.cast(int)).label("available_count"),
            func.count(ResponderStatus.id).label("total_count"),
            func.avg(ResponderStatus.active_incident_count).label("avg_workload"),
        ).join(User)

        filters = [User.organization_id == organization_id]
        if region_id:
            filters.append(User.region_id == region_id)

        query = query.where(and_(*filters))

        result = await self.db.execute(query)
        row = result.first()

        available_count = row.available_count or 0
        total_count = row.total_count or 0
        avg_workload = row.avg_workload or 0

        return {
            "available_count": available_count,
            "offline_count": total_count - available_count,
            "total_count": total_count,
            "availability_percentage": (available_count / total_count * 100) if total_count > 0 else 0,
            "average_workload": round(avg_workload, 2),
        }
