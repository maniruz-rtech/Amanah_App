"""
Integration tests for incident and responder management.

Tests cover:
- SOS incident creation
- Emergency location updates
- Incident status management
- Responder availability
- Responder assignment and response
- Nearby responder matching (geospatial)
- Incident cancellation and resolution
- Event logging and audit trail
"""

import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    IncidentNotFoundError,
    InvalidStateTransitionError,
    ResponderNotFoundError,
)
from app.core.security import hash_password
from app.db.enums import (
    AssignmentStatus,
    DevicePlatform,
    IncidentEventType,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    LocationSource,
    UserStatus,
)
from app.db.models import Incident, ResponderStatus, User
from app.repositories import (
    IncidentRepository,
    IncidentAssignmentRepository,
    ResponderRepository,
)
from app.services.incident import IncidentService
from app.services.responder import ResponderService


@pytest.mark.asyncio
class TestSOSCreation:
    """Tests for SOS incident creation."""

    @pytest.fixture
    async def sos_user(self, db: AsyncSession):
        """Create a user for SOS testing."""
        user = User(
            id="usr_sos_test",
            username="sosuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="SOS Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_create_sos_incident(self, db: AsyncSession, sos_user):
        """Test creating an SOS incident."""
        repo = IncidentRepository(db)

        incident = await repo.create_sos(
            user_id=sos_user.id,
            organization_id=sos_user.organization_id,
            region_id=sos_user.region_id,
            lat=23.8103,
            lng=90.4125,
            silent_mode=False,
            note="Help needed",
        )

        assert incident.id.startswith("inc_")
        assert incident.status == IncidentStatus.BROADCASTING
        assert incident.created_by_id == sos_user.id
        assert incident.silent_mode is False

        # Verify location was created
        await db.refresh(incident)
        assert len(incident.locations) > 0
        location = incident.locations[0]
        assert location.lat == 23.8103
        assert location.lng == 90.4125

    @pytest.mark.asyncio
    async def test_create_silent_sos(self, db: AsyncSession, sos_user):
        """Test creating a silent SOS (no audio alert)."""
        repo = IncidentRepository(db)

        incident = await repo.create_sos(
            user_id=sos_user.id,
            organization_id=sos_user.organization_id,
            region_id=sos_user.region_id,
            lat=23.8103,
            lng=90.4125,
            silent_mode=True,
        )

        assert incident.silent_mode is True

    @pytest.mark.asyncio
    async def test_incident_creation_creates_event(self, db: AsyncSession, sos_user):
        """Test that incident creation logs an event."""
        repo = IncidentRepository(db)

        incident = await repo.create_sos(
            user_id=sos_user.id,
            organization_id=sos_user.organization_id,
            region_id=sos_user.region_id,
            lat=23.8103,
            lng=90.4125,
        )

        await db.refresh(incident)
        assert len(incident.events) > 0
        event = incident.events[0]
        assert event.event_type == IncidentEventType.CREATED
        assert event.actor_user_id == sos_user.id


@pytest.mark.asyncio
class TestEmergencyLocation:
    """Tests for emergency location updates."""

    @pytest.fixture
    async def location_incident(self, db: AsyncSession, sos_user):
        """Create an incident for location testing."""
        repo = IncidentRepository(db)
        incident = await repo.create_sos(
            user_id=sos_user.id,
            organization_id=sos_user.organization_id,
            region_id=sos_user.region_id,
            lat=23.8103,
            lng=90.4125,
        )
        return incident

    @pytest.fixture
    async def sos_user(self, db: AsyncSession):
        user = User(
            id="usr_location_test",
            username="locuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Location Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_update_incident_location(self, db: AsyncSession, location_incident, sos_user):
        """Test updating incident location."""
        repo = IncidentRepository(db)

        location = await repo.add_location(
            incident_id=location_incident.id,
            user_id=sos_user.id,
            lat=23.8110,
            lng=90.4135,
            accuracy_m=50,
            source=LocationSource.GPS,
        )

        assert location.lat == 23.8110
        assert location.lng == 90.4135
        assert location.accuracy_m == 50
        assert location.source == LocationSource.GPS

        # Verify incident has multiple locations
        await db.refresh(location_incident)
        assert len(location_incident.locations) >= 2

    @pytest.mark.asyncio
    async def test_location_has_expiry(self, db: AsyncSession, location_incident, sos_user):
        """Test that locations have proper expiry."""
        repo = IncidentRepository(db)

        location = await repo.add_location(
            incident_id=location_incident.id,
            user_id=sos_user.id,
            lat=23.8120,
            lng=90.4140,
        )

        # Expiry should be set to future date
        assert location.expires_at > datetime.now(UTC)
        assert location.expires_at > location.captured_at


@pytest.mark.asyncio
class TestIncidentStatusManagement:
    """Tests for incident status transitions."""

    @pytest.fixture
    async def status_incident(self, db: AsyncSession):
        user = User(
            id="usr_status_test",
            username="statususer",
            password_hash=hash_password("TestPassword123!"),
            full_name="Status Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        repo = IncidentRepository(db)
        incident = await repo.create_sos(
            user_id=user.id,
            organization_id=user.organization_id,
            region_id=user.region_id,
            lat=23.8103,
            lng=90.4125,
        )
        return incident

    @pytest.mark.asyncio
    async def test_incident_status_transitions(self, db: AsyncSession, status_incident):
        """Test valid incident status transitions."""
        repo = IncidentRepository(db)

        # Start with BROADCASTING
        assert status_incident.status == IncidentStatus.BROADCASTING

        # Transition to ACCEPTED
        incident = await repo.update_status(
            incident_id=status_incident.id,
            new_status=IncidentStatus.ACCEPTED,
        )
        assert incident.status == IncidentStatus.ACCEPTED

        # Transition to EN_ROUTE
        incident = await repo.update_status(
            incident_id=incident.id,
            new_status=IncidentStatus.EN_ROUTE,
        )
        assert incident.status == IncidentStatus.EN_ROUTE

        # Transition to ARRIVED
        incident = await repo.update_status(
            incident_id=incident.id,
            new_status=IncidentStatus.ARRIVED,
        )
        assert incident.status == IncidentStatus.ARRIVED

    @pytest.mark.asyncio
    async def test_cancel_incident(self, db: AsyncSession, status_incident):
        """Test canceling an incident."""
        repo = IncidentRepository(db)

        # Cancellation is a status transition; the reason travels as the note.
        incident = await repo.update_status(
            incident_id=status_incident.id,
            new_status=IncidentStatus.CANCELED,
            note="False alarm",
        )

        assert incident.status == IncidentStatus.CANCELED
        assert incident.cancel_reason == "False alarm"
        assert incident.canceled_at is not None

    @pytest.mark.asyncio
    async def test_resolve_incident(self, db: AsyncSession, status_incident):
        """Test resolving an incident."""
        repo = IncidentRepository(db)

        # RESOLVED is only reachable from ARRIVED (README §8 state machine)
        for step in (IncidentStatus.ACCEPTED, IncidentStatus.EN_ROUTE, IncidentStatus.ARRIVED):
            await repo.update_status(incident_id=status_incident.id, new_status=step)

        # Resolve
        incident = await repo.update_status(
            incident_id=status_incident.id,
            new_status=IncidentStatus.RESOLVED,
            note="Victim transported to hospital",
        )

        assert incident.status == IncidentStatus.RESOLVED
        assert incident.resolved_at is not None
        assert incident.resolution_note == "Victim transported to hospital"


@pytest.mark.asyncio
class TestResponderAvailability:
    """Tests for responder availability management."""

    @pytest.fixture
    async def responder_user(self, db: AsyncSession):
        """Create a responder user."""
        user = User(
            id="usr_responder_test",
            username="responderuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Responder Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_responder_availability_update(self, db: AsyncSession, responder_user):
        """Test updating responder availability."""
        repo = ResponderRepository(db)

        status = await repo.update_availability(
            user_id=responder_user.id,
            is_available=True,
            lat=23.8103,
            lng=90.4125,
            battery_level=85,
        )

        assert status.is_available is True
        assert status.last_lat == 23.8103
        assert status.last_lng == 90.4125
        assert status.battery_level == 85
        assert status.location is not None

    @pytest.mark.asyncio
    async def test_responder_go_offline(self, db: AsyncSession, responder_user):
        """Test responder going offline."""
        repo = ResponderRepository(db)

        # First go online
        await repo.update_availability(
            user_id=responder_user.id,
            is_available=True,
            lat=23.8103,
            lng=90.4125,
        )

        # Then go offline
        status = await repo.update_availability(
            user_id=responder_user.id,
            is_available=False,
        )

        assert status.is_available is False


@pytest.mark.asyncio
class TestResponderAssignment:
    """Tests for responder assignment and response."""

    @pytest.fixture
    async def assignment_setup(self, db: AsyncSession):
        """Setup for assignment tests."""
        # Create incident
        incident_user = User(
            id="usr_assignment_incident",
            username="assignmentincident",
            password_hash=hash_password("TestPassword123!"),
            full_name="Incident Creator",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(incident_user)

        # Create responder
        responder_user = User(
            id="usr_assignment_responder",
            username="assignmentresponder",
            password_hash=hash_password("TestPassword123!"),
            full_name="Responder",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(responder_user)
        await db.flush()

        # Create incident
        incident_repo = IncidentRepository(db)
        incident = await incident_repo.create_sos(
            user_id=incident_user.id,
            organization_id=incident_user.organization_id,
            region_id=incident_user.region_id,
            lat=23.8103,
            lng=90.4125,
        )

        return incident, responder_user, incident_user

    @pytest.mark.asyncio
    async def test_assign_responder(self, db: AsyncSession, assignment_setup):
        """Test assigning a responder to an incident."""
        incident, responder, _ = assignment_setup
        repo = IncidentAssignmentRepository(db)

        assignment = await repo.assign_responder(
            incident_id=incident.id,
            responder_id=responder.id,
            distance_m=1500,
        )

        assert assignment.status == AssignmentStatus.PENDING
        assert assignment.responder_id == responder.id
        assert assignment.distance_m == 1500

    @pytest.mark.asyncio
    async def test_accept_assignment(self, db: AsyncSession, assignment_setup):
        """Test responder accepting assignment."""
        incident, responder, _ = assignment_setup
        repo = IncidentAssignmentRepository(db)

        assignment = await repo.assign_responder(
            incident_id=incident.id,
            responder_id=responder.id,
        )

        # Accept
        accepted = await repo.accept_assignment(
            assignment_id=assignment.id,
            eta_minutes=5,
        )

        assert accepted.status == AssignmentStatus.ACCEPTED
        assert accepted.accepted_at is not None
        assert accepted.eta_minutes == 5

    @pytest.mark.asyncio
    async def test_decline_assignment(self, db: AsyncSession, assignment_setup):
        """Test responder declining assignment."""
        incident, responder, _ = assignment_setup
        repo = IncidentAssignmentRepository(db)

        assignment = await repo.assign_responder(
            incident_id=incident.id,
            responder_id=responder.id,
        )

        # Decline
        declined = await repo.decline_assignment(
            assignment_id=assignment.id,
            reason="Too far away",
        )

        assert declined.status == AssignmentStatus.DECLINED
        assert declined.declined_at is not None
        assert declined.decline_reason == "Too far away"

    @pytest.mark.asyncio
    async def test_assignment_workflow(self, db: AsyncSession, assignment_setup):
        """Test complete assignment workflow."""
        incident, responder, _ = assignment_setup
        repo = IncidentAssignmentRepository(db)

        # Assign
        assignment = await repo.assign_responder(
            incident_id=incident.id,
            responder_id=responder.id,
            distance_m=2000,
        )
        assert assignment.status == AssignmentStatus.PENDING

        # Accept
        assignment = await repo.accept_assignment(
            assignment_id=assignment.id,
            eta_minutes=7,
        )
        assert assignment.status == AssignmentStatus.ACCEPTED

        # En route
        assignment = await repo.update_assignment_status(
            assignment_id=assignment.id, status=AssignmentStatus.EN_ROUTE
        )
        assert assignment.status == AssignmentStatus.EN_ROUTE

        # Arrived
        assignment = await repo.update_assignment_status(
            assignment_id=assignment.id, status=AssignmentStatus.ARRIVED
        )
        assert assignment.status == AssignmentStatus.ARRIVED
        assert assignment.arrived_at is not None


@pytest.mark.asyncio
class TestGeospatialMatching:
    """Tests for geospatial responder matching."""

    @pytest.fixture
    async def matching_setup(self, db: AsyncSession):
        """Setup for geospatial matching tests."""
        # Create multiple responders at different locations
        responders = []
        lats = [23.8103, 23.8110, 23.8120, 23.8150]  # Vary by ~1km each
        lngs = [90.4125, 90.4135, 90.4145, 90.4200]

        for i, (lat, lng) in enumerate(zip(lats, lngs)):
            user = User(
                id=f"usr_matching_{i}",
                username=f"responder{i}",
                password_hash=hash_password("TestPassword123!"),
                full_name=f"Responder {i}",
                organization_id="org_test",
                region_id="reg_test",
                is_active=True,
                is_verified=True,
                status=UserStatus.ACTIVE,
            )
            db.add(user)
            await db.flush()
            responders.append(user)

        # Only holders of the "responder" role are eligible for matching
        from app.db.models import Role, UserRole

        role = Role(id="role_responder_match", name="responder")
        db.add(role)
        await db.flush()
        for user in responders:
            db.add(UserRole(id=f"ur_{user.id}", user_id=user.id, role_id=role.id))
        await db.flush()

        # Create incident
        incident_user = User(
            id="usr_matching_incident",
            username="matchingincident",
            password_hash=hash_password("TestPassword123!"),
            full_name="Incident Creator",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(incident_user)
        await db.flush()

        incident_repo = IncidentRepository(db)
        incident = await incident_repo.create_sos(
            user_id=incident_user.id,
            organization_id=incident_user.organization_id,
            region_id=incident_user.region_id,
            lat=23.8103,
            lng=90.4125,
        )

        return incident, responders

    @pytest.mark.asyncio
    async def test_find_nearby_responders(self, db: AsyncSession, matching_setup):
        """Test finding nearby responders using geospatial queries."""
        incident, responders = matching_setup
        responder_repo = ResponderRepository(db)

        # Make responders available, spaced ~80-110 m apart around the incident
        for i, responder in enumerate(responders):
            await responder_repo.update_availability(
                user_id=responder.id,
                is_available=True,
                lat=23.8103 + i * 0.0007,
                lng=90.4125 + i * 0.001,
            )

        # Find nearby responders (within 2km)
        nearby = await responder_repo.find_nearby_responders(
            lat=23.8103,
            lng=90.4125,
            organization_id="org_test",
            radius_km=2.0,
            limit=10,
        )

        assert len(nearby) > 0
        # Should be sorted by distance
        distances = [d for _, d in nearby]
        assert distances == sorted(distances)


@pytest.mark.asyncio
class TestEventLogging:
    """Tests for incident event logging and audit trail."""

    @pytest.mark.asyncio
    async def test_incident_events_logged(self, db: AsyncSession):
        """Test that incident events are properly logged."""
        user = User(
            id="usr_events_test",
            username="eventsuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Events Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        repo = IncidentRepository(db)

        incident = await repo.create_sos(
            user_id=user.id,
            organization_id=user.organization_id,
            region_id=user.region_id,
            lat=23.8103,
            lng=90.4125,
            note="Help needed",
        )

        await db.refresh(incident)

        # Check events
        assert len(incident.events) >= 1
        created_event = incident.events[0]
        assert created_event.event_type == IncidentEventType.CREATED
        assert created_event.actor_user_id == user.id
        assert created_event.event_payload["lat"] == 23.8103
        assert created_event.event_payload["lng"] == 90.4125

    @pytest.mark.asyncio
    async def test_location_events_logged(self, db: AsyncSession):
        """Test that location updates log events."""
        user = User(
            id="usr_loc_events_test",
            username="loceventsuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Location Events Test",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        repo = IncidentRepository(db)

        incident = await repo.create_sos(
            user_id=user.id,
            organization_id=user.organization_id,
            region_id=user.region_id,
            lat=23.8103,
            lng=90.4125,
        )

        # Add location
        await repo.add_location(
            incident_id=incident.id,
            user_id=user.id,
            lat=23.8110,
            lng=90.4135,
        )

        await db.refresh(incident)

        # Should have CREATED and LOCATION_UPDATED events
        assert len(incident.events) >= 2
        location_event = incident.events[-1]
        assert location_event.event_type == IncidentEventType.LOCATION_UPDATED
