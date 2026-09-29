"""
Integration tests for OTP (One-Time Password) verification.

Tests cover:
- OTP request generation
- OTP verification with code validation
- Expiration handling
- Attempt limiting and rate limiting
- One-time use semantics
- Resend functionality
- Status checking
- Delivery orchestration
- Audit logging
"""

import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidOTPError,
    OTPExpiredError,
    RateLimitError,
    UserNotFoundError,
)
from app.core.security import hash_otp, hash_password, generate_otp
from app.db.enums import OTPChannel, OTPPurpose, UserStatus
from app.db.models import OTPRequest, User
from app.services.otp import OTPService
from app.schemas.otp import (
    OTPRequestCreate,
    OTPVerifyRequest,
    OTPResendRequest,
)


@pytest.mark.asyncio
class TestOTPRequest:
    """Tests for OTP request generation."""

    @pytest.fixture
    async def test_user(self, db: AsyncSession):
        """Create a test user."""
        user = User(
            id="usr_otp_test",
            username="otpuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="OTP Test User",
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
    async def test_request_otp_success(self, db: AsyncSession, test_user):
        """Test successful OTP request."""
        service = OTPService(db)
        request = OTPRequestCreate(
            user_id=test_user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination="+1234567890",
        )

        response, otp_code = await service.request_otp(
            request=request,
            ip_address="192.168.1.1",
            user_agent="TestAgent",
        )

        assert response.request_id != ""
        assert response.channel == OTPChannel.SMS.value
        assert response.expires_in_seconds > 0
        assert len(otp_code) == 6
        assert otp_code.isdigit()

    @pytest.mark.asyncio
    async def test_request_otp_without_user(self, db: AsyncSession):
        """Test OTP request without authentication (signup/password reset)."""
        service = OTPService(db)
        request = OTPRequestCreate(
            user_id=None,
            channel=OTPChannel.EMAIL,
            purpose=OTPPurpose.EMAIL_VERIFICATION,
            destination="test@example.com",
        )

        response, otp_code = await service.request_otp(request=request)

        assert response.request_id != ""
        assert len(otp_code) == 6

    @pytest.mark.asyncio
    async def test_request_otp_duplicate_request(
        self, db: AsyncSession, test_user
    ):
        """Test duplicate OTP request returns existing request."""
        service = OTPService(db)
        request_data = OTPRequestCreate(
            user_id=test_user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination="+1234567890",
        )

        # First request
        response1, code1 = await service.request_otp(request=request_data)

        # Duplicate request
        response2, code2 = await service.request_otp(request=request_data)

        # Should return same request ID
        assert response1.request_id == response2.request_id
        # Second call doesn't return OTP code
        assert code2 == ""

    @pytest.mark.asyncio
    async def test_request_otp_nonexistent_user(self, db: AsyncSession):
        """Test OTP request with non-existent user."""
        service = OTPService(db)
        request = OTPRequestCreate(
            user_id="usr_nonexistent",
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination="+1234567890",
        )

        with pytest.raises(UserNotFoundError):
            await service.request_otp(request=request)


@pytest.mark.asyncio
class TestOTPVerification:
    """Tests for OTP verification."""

    @pytest.fixture
    async def test_otp(self, db: AsyncSession):
        """Create a test OTP."""
        user = User(
            id="usr_verify_test",
            username="verifyuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Verify Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        otp_code = "123456"
        otp = OTPRequest(
            id="otp_verify_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination_hash=hash_otp("+1234567890"),
            otp_hash=hash_otp(otp_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(otp)
        await db.flush()

        return {"user": user, "otp": otp, "code": otp_code}

    @pytest.mark.asyncio
    async def test_verify_otp_success(self, db: AsyncSession, test_otp):
        """Test successful OTP verification."""
        service = OTPService(db)
        request = OTPVerifyRequest(
            request_id=test_otp["otp"].id,
            code=test_otp["code"],
        )

        response = await service.verify_otp(
            request=request,
            user_id=test_otp["user"].id,
        )

        assert response.verified is True
        assert response.channel == OTPChannel.SMS.value

        # Verify OTP is marked as used
        otp = await service.otp_repo.get_by_id(test_otp["otp"].id)
        assert otp.is_used

    @pytest.mark.asyncio
    async def test_verify_otp_invalid_code(self, db: AsyncSession, test_otp):
        """Test OTP verification with invalid code."""
        service = OTPService(db)
        request = OTPVerifyRequest(
            request_id=test_otp["otp"].id,
            code="999999",  # Wrong code
        )

        with pytest.raises(InvalidOTPError):
            await service.verify_otp(request=request)

    @pytest.mark.asyncio
    async def test_verify_otp_expired(self, db: AsyncSession):
        """Test OTP verification with expired OTP."""
        user = User(
            id="usr_expired_test",
            username="expireduser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Expired Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Create expired OTP
        otp = OTPRequest(
            id="otp_expired_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination_hash=hash_otp("+1234567890"),
            otp_hash=hash_otp("123456"),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),  # Expired
        )
        db.add(otp)
        await db.flush()

        service = OTPService(db)
        request = OTPVerifyRequest(
            request_id=otp.id,
            code="123456",
        )

        with pytest.raises(OTPExpiredError):
            await service.verify_otp(request=request)

    @pytest.mark.asyncio
    async def test_verify_otp_max_attempts(self, db: AsyncSession):
        """Test OTP verification with exceeded attempts."""
        user = User(
            id="usr_attempts_test",
            username="attemptsuser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Attempts Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Create OTP with low max attempts
        otp = OTPRequest(
            id="otp_attempts_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination_hash=hash_otp("+1234567890"),
            otp_hash=hash_otp("123456"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            max_attempts=3,
        )
        db.add(otp)
        await db.flush()

        service = OTPService(db)

        # Make 3 failed attempts
        for i in range(3):
            request = OTPVerifyRequest(
                request_id=otp.id,
                code="999999",  # Wrong code
            )

            if i < 2:
                with pytest.raises(InvalidOTPError):
                    await service.verify_otp(request=request)
            else:
                # 3rd attempt should raise RateLimitError
                with pytest.raises(RateLimitError):
                    await service.verify_otp(request=request)

    @pytest.mark.asyncio
    async def test_verify_otp_already_used(self, db: AsyncSession):
        """Test OTP verification when already used."""
        user = User(
            id="usr_used_test",
            username="useduser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Used Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        otp_code = "123456"
        otp = OTPRequest(
            id="otp_used_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination_hash=hash_otp("+1234567890"),
            otp_hash=hash_otp(otp_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            used_at=datetime.now(UTC),  # Already used
        )
        db.add(otp)
        await db.flush()

        service = OTPService(db)
        request = OTPVerifyRequest(
            request_id=otp.id,
            code=otp_code,
        )

        # Should raise OTPExpiredError (treated as invalid)
        with pytest.raises(OTPExpiredError):
            await service.verify_otp(request=request)


@pytest.mark.asyncio
class TestOTPResend:
    """Tests for OTP resend functionality."""

    @pytest.fixture
    async def test_otp_for_resend(self, db: AsyncSession):
        """Create a test OTP for resend."""
        user = User(
            id="usr_resend_test",
            username="resenduser",
            password_hash=hash_password("TestPassword123!"),
            full_name="Resend Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        otp = OTPRequest(
            id="otp_resend_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination_hash=hash_otp("+1234567890"),
            otp_hash=hash_otp("123456"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(otp)
        await db.flush()

        return {"user": user, "otp": otp}

    @pytest.mark.asyncio
    async def test_resend_otp_same_channel(
        self, db: AsyncSession, test_otp_for_resend
    ):
        """Test resending OTP to same channel."""
        service = OTPService(db)
        request = OTPResendRequest(request_id=test_otp_for_resend["otp"].id)

        response, new_code = await service.resend_otp(
            request=request,
            user_id=test_otp_for_resend["user"].id,
        )

        assert response.request_id == test_otp_for_resend["otp"].id
        assert response.channel == OTPChannel.SMS.value
        assert len(new_code) == 6

    @pytest.mark.asyncio
    async def test_resend_otp_different_channel(
        self, db: AsyncSession, test_otp_for_resend
    ):
        """Test resending OTP to different channel."""
        service = OTPService(db)
        request = OTPResendRequest(
            request_id=test_otp_for_resend["otp"].id,
            channel=OTPChannel.EMAIL,
        )

        response, new_code = await service.resend_otp(
            request=request,
            user_id=test_otp_for_resend["user"].id,
        )

        # Should create new request with different channel
        assert response.channel == OTPChannel.EMAIL.value
        assert response.request_id != test_otp_for_resend["otp"].id


@pytest.mark.asyncio
class TestOTPStatus:
    """Tests for OTP status checking."""

    @pytest.fixture
    async def test_otp_for_status(self, db: AsyncSession):
        """Create a test OTP for status check."""
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

        otp = OTPRequest(
            id="otp_status_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PHONE_VERIFICATION,
            destination_hash=hash_otp("+1234567890"),
            otp_hash=hash_otp("123456"),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(otp)
        await db.flush()

        return {"user": user, "otp": otp}

    @pytest.mark.asyncio
    async def test_get_otp_status(self, db: AsyncSession, test_otp_for_status):
        """Test getting OTP status."""
        service = OTPService(db)
        status = await service.get_otp_status(
            request_id=test_otp_for_status["otp"].id,
            user_id=test_otp_for_status["user"].id,
        )

        assert status.request_id == test_otp_for_status["otp"].id
        assert status.is_verified is False
        assert status.is_expired is False
        assert status.is_used is False
        assert status.attempts_remaining > 0
