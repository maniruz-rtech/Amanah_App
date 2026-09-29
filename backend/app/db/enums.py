"""
Database enums for status fields.

These match the PostgreSQL ENUMs defined in the schema.
"""

from enum import Enum


class OrganizationStatus(str, Enum):
    """Organization status values."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class RegionStatus(str, Enum):
    """Region status values."""

    ACTIVE = "active"
    INACTIVE = "inactive"


def enum_value(value):
    """Return the raw value of an Enum member, or the value itself if already raw.

    Request schemas use ``use_enum_values=True`` so validated fields arrive as
    plain strings, while ORM attributes are real Enum members; code that must
    accept both should go through this helper instead of calling ``.value``.
    """
    return value.value if isinstance(value, Enum) else value


class UserStatus(str, Enum):
    """User status values."""

    PENDING_VERIFICATION = "pending_verification"
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class DevicePlatform(str, Enum):
    """Device platform values."""

    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class IncidentType(str, Enum):
    """Incident type values."""

    SOS = "sos"
    MEDICAL = "medical"
    SAFETY = "safety"
    OTHER = "other"


class IncidentSeverity(str, Enum):
    """Incident severity values."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    """Incident status values per README Section 8."""

    DRAFT = "draft"
    ACTIVE = "active"
    BROADCASTING = "broadcasting"
    ACCEPTED = "accepted"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    RESOLVED = "resolved"
    CANCELED = "canceled"
    EXPIRED = "expired"


class AssignmentStatus(str, Enum):
    """Incident assignment status values."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELED = "canceled"


class LocationSource(str, Enum):
    """Location source values."""

    GPS = "gps"
    NETWORK = "network"
    MANUAL = "manual"
    LAST_KNOWN = "last_known"


class NotificationType(str, Enum):
    """Notification type values."""

    RESPONDER_ASSIGNMENT = "responder_assignment"
    INCIDENT_ASSIGNED = "incident_assigned"  # Alias for responder assignment
    TRUSTED_CONTACT_ALERT = "trusted_contact_alert"
    INCIDENT_UPDATE = "incident_update"
    INCIDENT_RESOLUTION = "incident_resolution"
    RESPONDER_ACCEPTED = "responder_accepted"
    RESPONDER_ARRIVED = "responder_arrived"
    ADMIN_ALERT = "admin_alert"
    PASSWORD_RESET = "password_reset"
    ACCOUNT_ACTIVATION = "account_activation"
    SYSTEM = "system"


class DeliveryStatus(str, Enum):
    """Notification delivery status values."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


class OTPChannel(str, Enum):
    """OTP delivery channel values."""

    SMS = "sms"
    EMAIL = "email"


class OTPPurpose(str, Enum):
    """OTP purpose values."""

    PHONE_VERIFICATION = "phone_verification"
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    LOGIN_MFA = "login_mfa"


class ApprovalStatus(str, Enum):
    """Approval status values."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequestType(str, Enum):
    """Approval request type values."""

    USER_ACTIVATION = "user_activation"
    PASSWORD_RESET = "password_reset"
    ROLE_CHANGE = "role_change"


class IncidentEventType(str, Enum):
    """Incident event type values for audit trail."""

    CREATED = "created"
    STATUS_UPDATED = "status_updated"
    LOCATION_UPDATED = "location_updated"
    RESPONDER_ASSIGNED = "responder_assigned"
    RESPONDER_ACCEPTED = "responder_accepted"
    RESPONDER_DECLINED = "responder_declined"
    RESPONDER_EN_ROUTE = "responder_en_route"
    RESPONDER_ARRIVED = "responder_arrived"
    RESPONDER_COMPLETED = "responder_completed"
    ESCALATED = "escalated"
    CANCELED = "canceled"
    RESOLVED = "resolved"
    NOTE_ADDED = "note_added"


# Valid status transitions per README Section 8
VALID_INCIDENT_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.DRAFT: {IncidentStatus.ACTIVE},
    IncidentStatus.ACTIVE: {IncidentStatus.BROADCASTING, IncidentStatus.EXPIRED},
    IncidentStatus.BROADCASTING: {
        IncidentStatus.ACCEPTED,
        IncidentStatus.CANCELED,
        IncidentStatus.EXPIRED,
    },
    IncidentStatus.ACCEPTED: {
        IncidentStatus.EN_ROUTE,
        IncidentStatus.CANCELED,
    },
    IncidentStatus.EN_ROUTE: {
        IncidentStatus.ARRIVED,
        IncidentStatus.CANCELED,
    },
    IncidentStatus.ARRIVED: {IncidentStatus.RESOLVED},
    IncidentStatus.RESOLVED: set(),  # Terminal state
    IncidentStatus.CANCELED: set(),  # Terminal state
    IncidentStatus.EXPIRED: set(),  # Terminal state
}


def is_valid_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    """Check if a status transition is valid."""
    return target in VALID_INCIDENT_TRANSITIONS.get(current, set())


def is_terminal_status(status: IncidentStatus) -> bool:
    """Check if a status is terminal (no further transitions)."""
    return status in {IncidentStatus.RESOLVED, IncidentStatus.CANCELED, IncidentStatus.EXPIRED}


def is_active_status(status: IncidentStatus) -> bool:
    """Check if an incident is in an active (non-terminal) state."""
    return status not in {IncidentStatus.RESOLVED, IncidentStatus.CANCELED, IncidentStatus.EXPIRED}
