"""
Amanah Backend Application Configuration

Uses pydantic-settings for environment-based configuration with validation.
All secrets should be loaded from environment variables or Vault.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Application
    # ─────────────────────────────────────────────────────────────────────────
    app_name: str = "Amanah API"
    app_version: str = "1.0.0"
    environment: Literal["local", "dev", "staging", "production"] = "local"
    debug: bool = False
    log_level: str = "INFO"

    # ─────────────────────────────────────────────────────────────────────────
    # Database
    # ─────────────────────────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://amanah:amanah@localhost:5432/amanah"
    )
    # Per-process pool. 10+10 keeps API + 2 Celery workers well under
    # PostgreSQL's default max_connections=100; raise via env for busy deployments.
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Redis
    # ─────────────────────────────────────────────────────────────────────────
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_pool_size: int = 20

    # ─────────────────────────────────────────────────────────────────────────
    # JWT Configuration
    # ─────────────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(default="CHANGE-ME-IN-PRODUCTION-USE-VAULT")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ─────────────────────────────────────────────────────────────────────────
    # Encryption
    # ─────────────────────────────────────────────────────────────────────────
    encryption_key: str = Field(default="CHANGE-ME-32-BYTE-KEY-FOR-AES256")

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("Encryption key must be at least 32 bytes")
        return v[:32]  # Ensure exactly 32 bytes

    @model_validator(mode="after")
    def reject_insecure_defaults_outside_dev(self) -> "Settings":
        """Refuse to boot staging/production with placeholder secrets or debug on."""
        if self.environment in ("staging", "production"):
            weak = ("change-me", "dev-only", "dev-secret", "dev-encryption")
            problems = [
                name
                for name, value in (
                    ("JWT_SECRET_KEY", self.jwt_secret_key),
                    ("ENCRYPTION_KEY", self.encryption_key),
                )
                if len(value) < 32 or any(w in value.lower() for w in weak)
            ]
            if problems:
                raise ValueError(f"Insecure/placeholder secret(s) in {self.environment}: {', '.join(problems)}")
            if self.debug:
                raise ValueError(f"DEBUG must be false in {self.environment}")
        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Security
    # ─────────────────────────────────────────────────────────────────────────
    password_min_length: int = 12
    otp_expire_minutes: int = 10
    otp_max_attempts: int = 3
    account_lockout_attempts: int = 5
    account_lockout_window_minutes: int = 15
    account_lockout_duration_minutes: int = 30

    # ─────────────────────────────────────────────────────────────────────────
    # Rate Limiting
    # ─────────────────────────────────────────────────────────────────────────
    rate_limit_auth: str = "5/minute"
    rate_limit_api: str = "60/minute"
    rate_limit_sos: str = "1/minute"

    # ─────────────────────────────────────────────────────────────────────────
    # CORS
    # ─────────────────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(default=["http://localhost:3000"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default=["*"])
    cors_allow_headers: list[str] = Field(default=["*"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ─────────────────────────────────────────────────────────────────────────
    # Firebase / Push Notifications
    # ─────────────────────────────────────────────────────────────────────────
    firebase_credentials_path: str | None = None
    fcm_enabled: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # SMS Provider (Twilio)
    # ─────────────────────────────────────────────────────────────────────────
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    sms_enabled: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Incident Settings
    # ─────────────────────────────────────────────────────────────────────────
    incident_escalation_timeout_seconds: int = 90
    incident_location_expiry_days: int = 90
    responder_search_radius_km: float = 5.0
    responder_search_radius_max_km: float = 10.0
    responder_max_assignments: int = 10
    # Max responders notified on the initial SOS broadcast (IncidentService).
    broadcast_responder_limit: int = 25

    # ─────────────────────────────────────────────────────────────────────────
    # Celery
    # ─────────────────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ─────────────────────────────────────────────────────────────────────────
    # Data Retention (days)
    # ─────────────────────────────────────────────────────────────────────────
    retention_audit_logs_days: int = 730  # 24 months
    retention_incidents_days: int = 730  # 24 months
    retention_locations_days: int = 90  # 90 days
    retention_notifications_days: int = 180  # 6 months

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment in ("local", "dev")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
