"""
Security utilities for authentication, password hashing, and JWT tokens.

Uses:
- Argon2id for password hashing (NOT bcrypt)
- JWT for access and refresh tokens
- AES-256-GCM for field-level encryption
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# Password Hashing (Argon2id)
# ─────────────────────────────────────────────────────────────────────────────

_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        _password_hasher.verify(hashed_password, plain_password)
        return True
    except VerifyMismatchError:
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """Check if password hash needs updating to current parameters."""
    return _password_hasher.check_needs_rehash(hashed_password)


# ─────────────────────────────────────────────────────────────────────────────
# JWT Tokens
# ─────────────────────────────────────────────────────────────────────────────


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str  # Subject (user_id)
    exp: datetime  # Expiration
    iat: datetime  # Issued at
    type: str  # Token type: "access" or "refresh"
    roles: list[str] = []
    jti: str | None = None  # JWT ID for refresh tokens
    device_id: str | None = None  # Device binding


def create_access_token(
    user_id: str,
    roles: list[str] | None = None,
    device_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create JWT access token (15 min TTL by default)."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)

    now = datetime.now(UTC)
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "type": "access",
        "roles": roles or [],
        "device_id": device_id,
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    jti: str | None = None,
    device_id: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create JWT refresh token (30 day TTL by default).

    Args:
        user_id: User identifier
        jti: JWT ID (unique identifier for tracking). Generated if not provided.
        device_id: Optional device binding
        expires_delta: Custom expiration delta

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.jwt_refresh_token_expire_days)

    if jti is None:
        jti = secrets.token_urlsafe(32)

    now = datetime.now(UTC)
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "jti": jti,
        "device_id": device_id,
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate JWT token.

    Raises:
        JWTError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**payload)
    except JWTError as e:
        raise JWTError(f"Invalid token: {e}") from e


def verify_token(token: str, token_type: str = "access") -> TokenPayload:
    """
    Verify token and check type.

    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")

    Raises:
        JWTError: If token is invalid, expired, or wrong type.
    """
    payload = decode_token(token)
    if payload.type != token_type:
        raise JWTError(f"Invalid token type: expected {token_type}")
    return payload


def verify_access_token(token: str) -> TokenPayload:
    """Verify access token."""
    return verify_token(token, token_type="access")


def verify_refresh_token(token: str) -> dict[str, Any]:
    """Verify refresh token and return payload as dict."""
    payload = verify_token(token, token_type="refresh")
    return payload.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# Field-Level Encryption (AES-256-GCM)
# ─────────────────────────────────────────────────────────────────────────────

_encryption_key = settings.encryption_key.encode()[:32]
_aesgcm = AESGCM(_encryption_key)


def hash_contact(value: str) -> str:
    """Deterministic keyed lookup hash for a phone number / email address.

    Encrypted PII cannot be searched (AES-GCM uses a random nonce) and Argon2
    hashes are salted, so exact-match lookups (``users.phone_hash``,
    ``users.email_hash``, ``otp_requests.destination_hash``) use HMAC-SHA256
    keyed with the server's encryption key: deterministic, but — unlike a bare
    SHA-256 of a phone number — not brute-forceable without the key.
    """
    return hmac.new(
        settings.encryption_key.encode(), value.strip().lower().encode(), hashlib.sha256
    ).hexdigest()


def encrypt_field(plaintext: str) -> bytes:
    """Encrypt a field value using AES-256-GCM."""
    nonce = secrets.token_bytes(12)  # 96-bit nonce
    ciphertext = _aesgcm.encrypt(nonce, plaintext.encode(), None)
    return nonce + ciphertext


def decrypt_field(encrypted: bytes) -> str:
    """Decrypt a field value encrypted with AES-256-GCM."""
    nonce = encrypted[:12]
    ciphertext = encrypted[12:]
    plaintext = _aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


# ─────────────────────────────────────────────────────────────────────────────
# OTP Generation
# ─────────────────────────────────────────────────────────────────────────────


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP code."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_verification_pin() -> str:
    """Generate a 4-digit verification PIN."""
    return str(secrets.randbelow(9000) + 1000)


def hash_otp(value: str) -> str:
    """
    Hash an OTP or destination value using Argon2id.

    Used for storing OTP codes and destinations in secure way.
    """
    from argon2 import PasswordHasher
    hasher = PasswordHasher(
        time_cost=2,
        memory_cost=19456,
        parallelism=1,
    )
    return hasher.hash(value)


def verify_otp_hash(plain_value: str, hashed_value: str) -> bool:
    """
    Verify OTP or destination value against hash.
    """
    try:
        _password_hasher.verify(hashed_value, plain_value)
        return True
    except VerifyMismatchError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TOTP (Time-based One-Time Password) for MFA
# ─────────────────────────────────────────────────────────────────────────────

import pyotp


def generate_totp_secret() -> str:
    """Generate a random TOTP secret for MFA setup."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str, issuer: str = "Amanah") -> str:
    """Generate TOTP provisioning URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code against the secret."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# Alias for consistency with naming
verify_totp_code = verify_totp


# ─────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────────────────


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_password(length: int = 16) -> str:
    """
    Generate a strong random password.
    
    Includes uppercase, lowercase, digits, and special characters.
    """
    import string
    
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    # Fill the rest
    password.extend(secrets.choice(chars) for _ in range(length - 4))
    # Shuffle
    password_list = list(password)
    secrets.SystemRandom().shuffle(password_list)
    return "".join(password_list)


def mask_email(email: str) -> str:
    """Mask email for display (e.g., u***@example.com)."""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """Mask phone number for display (e.g., +8801****67890)."""
    if len(phone) < 8:
        return "***"
    return phone[:5] + "****" + phone[-5:]
