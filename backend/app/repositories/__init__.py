"""
Repositories package exports.
"""

from app.repositories.admin import (
    AdminIncidentRepository,
    AdminRepository,
    AdminUserRepository,
)
from app.repositories.auth import RefreshTokenRepository
from app.repositories.base import BaseRepository
from app.repositories.device import DeviceRepository
from app.repositories.incident import IncidentAssignmentRepository, IncidentRepository
from app.repositories.notification import (
    AuditLogRepository,
    NotificationRepository,
    TrustedContactRepository,
)
from app.repositories.otp import OTPRepository
from app.repositories.password_reset import PasswordResetRepository
from app.repositories.responder import ResponderRepository
from app.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    # User
    "UserRepository",
    # Device
    "DeviceRepository",
    # Auth
    "RefreshTokenRepository",
    # OTP
    "OTPRepository",
    # Password Reset
    "PasswordResetRepository",
    # Incident
    "IncidentRepository",
    "IncidentAssignmentRepository",
    # Responder
    "ResponderRepository",
    # Notification
    "NotificationRepository",
    "AuditLogRepository",
    "TrustedContactRepository",
    # Admin
    "AdminRepository",
    "AdminIncidentRepository",
    "AdminUserRepository",
]
