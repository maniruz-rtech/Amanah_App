"""
Integration tests for authentication module.

Tests cover:
- Login with valid/invalid credentials
- Password hashing (Argon2id)
- Token generation and refresh
- MFA flow
- OTP request and verification
- Password reset flow
- Account lockout
- Logout
"""

import pytest
from datetime import UTC, datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountLockedError,
    AccountSuspendedError,
    InvalidCredentialsError,
    InvalidOTPError,
    InvalidTokenError,
    MFARequiredError,
    OTPExpiredError,
    RateLimitError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    encrypt_field,
    generate_otp,
    generate_totp_secret,
    hash_otp,
    hash_password,
    verify_access_token,
    verify_otp_hash,
    verify_password,
    verify_refresh_token,
    verify_totp,
)
from app.db.enums import OTPChannel, OTPPurpose, UserStatus
from app.db.models import User
from app.services.auth import AuthService


@pytest.mark.asyncio
class TestPasswordHashing:
    """Tests for Argon2id password hashing."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "SecurePassword123!"
        hashed = hash_password(password)

        # Hash should not contain plaintext
        assert password not in hashed
        # Hash should be deterministic for same password
        assert verify_password(password, hashed)

    def test_verify_password_success(self):
        """Test successful password verification."""
        password = "MyPassword123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_verify_password_failure(self):
        """Test failed password verification."""
        password = "MyPassword123!"
        hashed = hash_password(password)
        assert not verify_password("WrongPassword!", hashed)


@pytest.mark.asyncio
class TestTokenGeneration:
    """Tests for JWT token generation and verification."""

    def test_create_access_token(self):
        """Test access token creation."""
        user_id = "usr_test123"
        token = create_access_token(user_id=user_id)

        assert isinstance(token, str)
        payload = verify_access_token(token)
        assert payload.sub == user_id
        assert payload.type == "access"

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        user_id = "usr_test123"
        token = create_refresh_token(user_id=user_id)

        assert isinstance(token, str)
        payload = verify_refresh_token(token)
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_refresh_token_with_custom_jti(self):
        """Test refresh token with custom JTI."""
        user_id = "usr_test123"
        jti = "custom_jti_123"
        token = create_refresh_token(user_id=user_id, jti=jti)

        payload = verify_refresh_token(token)
        assert payload["jti"] == jti

    def test_access_token_expiration(self):
        """Test access token expiration validation."""
        from datetime import timedelta
        user_id = "usr_test123"
        token = create_access_token(
            user_id=user_id,
            expires_delta=timedelta(seconds=-1),  # Expired
        )

        from jose import JWTError
        with pytest.raises(JWTError):
            verify_access_token(token)


@pytest.mark.asyncio
class TestOTPOperations:
    """Tests for OTP generation and verification."""

    def test_generate_otp(self):
        """Test OTP generation."""
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_hash_otp(self):
        """Test OTP hashing."""
        otp = "123456"
        hashed = hash_otp(otp)

        assert otp not in hashed
        assert verify_otp_hash(otp, hashed)

    def test_verify_otp_failure(self):
        """Test OTP verification failure."""
        otp = "123456"
        hashed = hash_otp(otp)

        assert not verify_otp_hash("654321", hashed)

    def test_hash_destination(self):
        """Test hashing of phone numbers and email."""
        phone = "+880123456789"
        hashed = hash_otp(phone)

        assert phone not in hashed
        assert verify_otp_hash(phone, hashed)


@pytest.mark.asyncio
class TestTOTPOperations:
    """Tests for TOTP (Time-based OTP) for MFA."""

    def test_generate_totp_secret(self):
        """Test TOTP secret generation."""
        secret = generate_totp_secret()
        assert len(secret) > 0
        assert isinstance(secret, str)

    def test_verify_totp(self):
        """Test TOTP code verification."""
        import pyotp
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        assert verify_totp(secret, code)

    def test_verify_totp_invalid(self):
        """Test TOTP verification with invalid code."""
        secret = generate_totp_secret()
        assert not verify_totp(secret, "000000")


@pytest.mark.asyncio
class TestLogin:
    """Tests for login endpoint and flow."""

    @pytest.fixture
    async def test_user(self, db: AsyncSession):
        """Create a test user."""
        user = User(
            id="usr_test1",
            username="testuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Test User",
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
    async def test_login_success(self, db: AsyncSession, test_user):
        """Test successful login."""
        auth_service = AuthService(db)
        tokens, user = await auth_service.login(
            username="testuser",
            password="TestPassword123!",
        )

        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.token_type == "bearer"
        assert user.id == test_user.id
        assert user.last_login_at is not None

    @pytest.mark.asyncio
    async def test_login_invalid_username(self, db: AsyncSession):
        """Test login with non-existent user."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                username="nonexistent",
                password="Password123!",
            )

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, db: AsyncSession, test_user):
        """Test login with wrong password."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                username="testuser",
                password="WrongPassword!",
            )

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, db: AsyncSession, test_user):
        """Test login with inactive user."""
        test_user.is_active = False
        await db.flush()

        auth_service = AuthService(db)
        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                username="testuser",
                password="TestPassword123!",
            )

    @pytest.mark.asyncio
    async def test_login_suspended_user(self, db: AsyncSession, test_user):
        """Test login with suspended user."""
        test_user.is_suspended = True
        await db.flush()

        auth_service = AuthService(db)
        with pytest.raises(AccountSuspendedError):
            await auth_service.login(
                username="testuser",
                password="TestPassword123!",
            )


@pytest.mark.asyncio
class TestAccountLockout:
    """Tests for account lockout after failed login attempts."""

    @pytest.fixture
    async def lockout_user(self, db: AsyncSession):
        """Create a user for lockout testing."""
        user = User(
            id="usr_lockout",
            username="lockoutuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Lockout Test",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
            failed_login_attempts=0,
        )
        db.add(user)
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_failed_login_increments_attempts(self, db: AsyncSession, lockout_user):
        """Test that failed logins increment attempt counter."""
        auth_service = AuthService(db)
        initial_attempts = lockout_user.failed_login_attempts

        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                username="lockoutuser",
                password="WrongPassword!",
            )

        await db.refresh(lockout_user)
        assert lockout_user.failed_login_attempts == initial_attempts + 1

    @pytest.mark.asyncio
    async def test_account_lockout_after_max_attempts(self, db: AsyncSession, lockout_user):
        """Test account lockout after max failed attempts."""
        from app.core.config import settings

        # Set user to max attempts - 1
        lockout_user.failed_login_attempts = settings.account_lockout_attempts - 1
        await db.flush()

        auth_service = AuthService(db)

        # One more failed attempt should lock the account
        with pytest.raises(InvalidCredentialsError):
            await auth_service.login(
                username="lockoutuser",
                password="WrongPassword!",
            )

        await db.refresh(lockout_user)
        assert lockout_user.locked_until is not None
        assert lockout_user.locked_until > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_cannot_login_while_locked(self, db: AsyncSession, lockout_user):
        """Test that locked account cannot login."""
        from datetime import timedelta
        from app.core.config import settings

        lockout_user.locked_until = datetime.now(UTC) + timedelta(minutes=30)
        await db.flush()

        auth_service = AuthService(db)
        with pytest.raises(AccountLockedError):
            await auth_service.login(
                username="lockoutuser",
                password="TestPassword123!",
            )

    @pytest.mark.asyncio
    async def test_lockout_timeout_resets_lockout(self, db: AsyncSession, lockout_user):
        """Test that account can login after lockout expires."""
        from datetime import timedelta

        # Set lockout to past time (expired)
        lockout_user.locked_until = datetime.now(UTC) - timedelta(minutes=1)
        lockout_user.failed_login_attempts = 5
        await db.flush()

        auth_service = AuthService(db)
        tokens, user = await auth_service.login(
            username="lockoutuser",
            password="TestPassword123!",
        )

        assert tokens.access_token
        assert user.failed_login_attempts == 0
        assert user.locked_until is None


@pytest.mark.asyncio
class TestFreshTokenRefresh:
    """Tests for token refresh operation."""

    @pytest.fixture
    async def refresh_user(self, db: AsyncSession):
        """Create a user for token refresh testing."""
        user = User(
            id="usr_refresh",
            username="refreshuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Refresh Test",
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
    async def test_refresh_token_success(self, db: AsyncSession, refresh_user):
        """Test successful token refresh."""
        auth_service = AuthService(db)

        # Initial login
        tokens, _ = await auth_service.login(
            username="refreshuser",
            password="TestPassword123!",
        )

        # Extract JTI from refresh token
        payload = verify_refresh_token(tokens.refresh_token)
        old_jti = payload["jti"]

        # Refresh tokens
        new_tokens = await auth_service.refresh_tokens(refresh_token_jti=old_jti)

        assert new_tokens.access_token
        assert new_tokens.refresh_token
        # New refresh token should have different JTI
        new_payload = verify_refresh_token(new_tokens.refresh_token)
        assert new_payload["jti"] != old_jti

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, db: AsyncSession):
        """Test refresh with invalid token."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidTokenError):
            await auth_service.refresh_tokens(refresh_token_jti="invalid_jti")


@pytest.mark.asyncio
class TestLogout:
    """Tests for logout operation."""

    @pytest.fixture
    async def logout_user(self, db: AsyncSession):
        """Create a user for logout testing."""
        user = User(
            id="usr_logout",
            username="logoutuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Logout Test",
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
    async def test_logout_revokes_token(self, db: AsyncSession, logout_user):
        """Test that logout revokes token."""
        auth_service = AuthService(db)

        # Login
        tokens, _ = await auth_service.login(
            username="logoutuser",
            password="TestPassword123!",
        )

        payload = verify_refresh_token(tokens.refresh_token)
        jti = payload["jti"]

        # Logout
        await auth_service.logout(refresh_token_jti=jti, user_id=logout_user.id)

        # Try to use revoked token
        with pytest.raises(InvalidTokenError):
            await auth_service.refresh_tokens(refresh_token_jti=jti)


@pytest.mark.asyncio
class TestOTPFlow:
    """Tests for OTP request and verification."""

    @pytest.mark.asyncio
    async def test_request_otp(self, db: AsyncSession):
        """Test OTP request."""
        auth_service = AuthService(db)

        request_id, otp_code = await auth_service.request_otp(
            user_id=None,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination="+880123456789",
        )

        assert request_id
        assert len(otp_code) == 6
        assert otp_code.isdigit()

    @pytest.mark.asyncio
    async def test_verify_otp_success(self, db: AsyncSession):
        """Test successful OTP verification."""
        auth_service = AuthService(db)

        # Request OTP
        request_id, otp_code = await auth_service.request_otp(
            user_id=None,
            channel=OTPChannel.EMAIL,
            purpose=OTPPurpose.PASSWORD_RESET,
            destination="user@example.com",
        )

        # Verify OTP
        result = await auth_service.verify_otp(request_id=request_id, otp_code=otp_code)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_otp_invalid_code(self, db: AsyncSession):
        """Test OTP verification with wrong code."""
        auth_service = AuthService(db)

        # Request OTP
        request_id, _ = await auth_service.request_otp(
            user_id=None,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination="+880123456789",
        )

        # Try with wrong code
        with pytest.raises(InvalidOTPError):
            await auth_service.verify_otp(request_id=request_id, otp_code="000000")

    @pytest.mark.asyncio
    async def test_otp_attempt_limiting(self, db: AsyncSession):
        """Test OTP attempt limiting."""
        from app.core.config import settings

        auth_service = AuthService(db)

        # Request OTP
        request_id, _ = await auth_service.request_otp(
            user_id=None,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination="+880123456789",
        )

        # Try wrong code multiple times
        for _ in range(settings.otp_max_attempts):
            with pytest.raises(InvalidOTPError):
                await auth_service.verify_otp(request_id=request_id, otp_code="000000")

        # Next attempt should raise rate limit
        with pytest.raises(RateLimitError):
            await auth_service.verify_otp(request_id=request_id, otp_code="000000")


@pytest.mark.asyncio
class TestPasswordReset:
    """Tests for password reset flow."""

    @pytest.fixture
    async def reset_user(self, db: AsyncSession):
        """Create a user for password reset testing."""
        user = User(
            id="usr_reset",
            username="resetuser",
            password_hash=hash_password("OldPassword123!"),
            full_name="Reset Test",
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
    async def test_request_password_reset(self, db: AsyncSession, reset_user):
        """Test password reset request."""
        auth_service = AuthService(db)

        request_id = await auth_service.request_password_reset(reset_user.id)

        assert request_id
        assert request_id.startswith("prr_")

    @pytest.mark.asyncio
    async def test_complete_password_reset(self, db: AsyncSession, reset_user):
        """Test completing password reset."""
        auth_service = AuthService(db)

        # Request password reset
        request_id = await auth_service.request_password_reset(reset_user.id)

        # Complete reset
        result = await auth_service.complete_password_reset(
            request_id=request_id,
            new_password="NewPassword123!",
        )

        assert result is True

        # Verify new password works
        await db.refresh(reset_user)
        assert verify_password("NewPassword123!", reset_user.password_hash)
        assert not verify_password("OldPassword123!", reset_user.password_hash)


@pytest.mark.asyncio
class TestMFAFlow:
    """Tests for MFA (TOTP) flow."""

    @pytest.fixture
    async def mfa_user(self, db: AsyncSession):
        """Create a user with MFA enabled."""
        secret = generate_totp_secret()
        secret_encrypted = encrypt_field(secret)

        user = User(
            id="usr_mfa",
            username="mfauser",
            password_hash=hash_password("TestPassword123!"),
            full_name="MFA Test",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
            mfa_enabled=True,
            totp_secret_encrypted=secret_encrypted,
        )
        db.add(user)
        await db.flush()
        return user, secret

    @pytest.mark.asyncio
    async def test_login_with_mfa_required(self, db: AsyncSession, mfa_user):
        """Test that MFA is required when enabled."""
        user, secret = mfa_user
        auth_service = AuthService(db)

        with pytest.raises(MFARequiredError) as exc_info:
            await auth_service.login(
                username="mfauser",
                password="TestPassword123!",
            )

        assert exc_info.value.mfa_session_token

    @pytest.mark.asyncio
    async def test_mfa_verification_success(self, db: AsyncSession, mfa_user):
        """Test successful MFA verification."""
        import pyotp

        user, secret = mfa_user
        auth_service = AuthService(db)

        # Try login
        mfa_session_token = None
        try:
            await auth_service.login(
                username="mfauser",
                password="TestPassword123!",
            )
        except MFARequiredError as e:
            mfa_session_token = e.mfa_session_token

        assert mfa_session_token

        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()

        # Verify MFA
        tokens, verified_user = await auth_service.verify_mfa(
            mfa_session_token=mfa_session_token,
            totp_code=code,
        )

        assert tokens.access_token
        assert tokens.refresh_token
        assert verified_user.id == user.id

    @pytest.mark.asyncio
    async def test_mfa_verification_invalid_code(self, db: AsyncSession, mfa_user):
        """Test MFA verification with invalid code."""
        user, secret = mfa_user
        auth_service = AuthService(db)

        # Try login
        mfa_session_token = None
        try:
            await auth_service.login(
                username="mfauser",
                password="TestPassword123!",
            )
        except MFARequiredError as e:
            mfa_session_token = e.mfa_session_token

        # Try with invalid code
        with pytest.raises(InvalidCredentialsError):
            await auth_service.verify_mfa(
                mfa_session_token=mfa_session_token,
                totp_code="000000",
            )
