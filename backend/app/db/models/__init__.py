"""
Database models package.

All models are imported here for easy access and to ensure proper
relationship loading order.
"""

from app.db.models.admin_approval import AdminApproval
from app.db.models.audit_log import AuditLog
from app.db.models.device import Device
from app.db.models.emergency_location import EmergencyLocation
from app.db.models.incident import Incident
from app.db.models.incident_assignment import IncidentAssignment
from app.db.models.incident_event import IncidentEvent
from app.db.models.notification import Notification
from app.db.models.organization import Organization
from app.db.models.otp_request import OTPRequest
from app.db.models.password_reset_request import PasswordResetRequest
from app.db.models.refresh_token import RefreshToken
from app.db.models.region import Region
from app.db.models.responder_status import ResponderStatus
from app.db.models.role import Role, UserRole
from app.db.models.trusted_contact import TrustedContact
from app.db.models.user import User

__all__ = [
    # Core entities
    "Organization",
    "Region",
    "User",
    "Role",
    "UserRole",
    "Device",
    "TrustedContact",
    # Responder
    "ResponderStatus",
    # Incident
    "Incident",
    "EmergencyLocation",
    "IncidentAssignment",
    "IncidentEvent",
    # Notifications
    "Notification",
    # Auth & Security
    "OTPRequest",
    "PasswordResetRequest",
    "RefreshToken",
    # Admin
    "AdminApproval",
    "AuditLog",
]
