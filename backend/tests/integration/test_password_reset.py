"""
Integration tests for password reset and recovery.

Tests cover:
- Password reset request flow
- OTP verification
- Admin approval
- Password reset completion
- One-time use semantics
- Expiration handling
- Security validations
- Audit logging
"""

import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidOTPError,
    InvalidTokenError,
    OTPExpiredError,
    PermissionDeniedError,
)
from app.core.security import hash_otp, hash_password, generate_otp
from app.db.enums import ApprovalStatus, OTPChannel, OTPPurpose, UserStatus
from app.db.models import OTPRequest, PasswordResetRequest, User
from app.services.password_reset import PasswordResetService
from app.schemas.password_reset import (
    CompletePasswordResetRequest,
    OTPVerificationRequest,
    PasswordResetApprovalRequest,
    PasswordResetRequestCreate,
)


@pytest.mark.asyncio
class TestPasswordResetRequest:
    """Tests for password reset request initiation."""

    @pytest.fixture
    async def test_user(self, db: AsyncSession):
        """Create a test user."""
        user = User(
            id="usr_pass_reset",
            username="resetuser",
            password_hash=hash_password("OldPassword123!"),
            full_name="Reset Test User",
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
    async def test_request_password_reset_success(
        self, db: AsyncSession, test_user
    ):
        """Test successful password reset request."""
        service = PasswordResetService(db)
        response = await service.request_password_reset(
            username=test_user.username,
            ip_address="192.168.1.1",
            user_agent="TestAgent",
        )

        assert response.request_id != ""
        assert response.message is not None
        assert response.expires_in_minutes == 1440  # 24 hours

    @pytest.mark.asyncio
    async def test_request_password_reset_nonexistent_user(
        self, db: AsyncSession
    ):
        """Test password reset for non-existent user (should not reveal)."""
        service = PasswordResetService(db)
        response = await service.request_password_reset(
            username="nonexistent_user",
        )

        # Should always return success message for security
        assert response.message is not None

    @pytest.mark.asyncio
    async def test_request_password_reset_existing_active_request(
        self, db: AsyncSession, test_user
    ):
        """Test requesting reset when user already has active request."""
        service = PasswordResetService(db)

        # First request
        response1 = await service.request_password_reset(
            username=test_user.username,
        )

        # Second request should return same request ID
        response2 = await service.request_password_reset(
            username=test_user.username,
        )

        assert response1.request_id == response2.request_id


@pytest.mark.asyncio
class TestPasswordResetStatus:
    """Tests for password reset status tracking."""

    @pytest.fixture
    async def test_user_with_reset(self, db: AsyncSession):
        """Create user with active password reset request."""
        user = User(
            id="usr_status_test",
            username="statususer",
            password_hash=hash_password("OldPassword123!"),
            full_name="Status Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Create reset request
        now = datetime.now(UTC)
        reset_request = PasswordResetRequest(
            id="prr_status_test",
            user_id=user.id,
            requested_at=now,
            expires_at=now + timedelta(hours=24),
            admin_approval_status=ApprovalStatus.PENDING,
        )
        db.add(reset_request)
        await db.flush()

        return {"user": user, "request": reset_request}

    @pytest.mark.asyncio
    async def test_get_reset_status(self, db: AsyncSession, test_user_with_reset):
        """Test getting reset status."""
        service = PasswordResetService(db)
        status = await service.get_reset_status(
            request_id=test_user_with_reset["request"].id,
            user_id=test_user_with_reset["user"].id,
        )

        assert status.request_id == test_user_with_reset["request"].id
        assert status.phone_verified is False
        assert status.email_verified is False
        assert status.admin_approval_status == ApprovalStatus.PENDING.value
        assert status.can_complete is False  # Not verified yet
        assert status.is_expired is False

    @pytest.mark.asyncio
    async def test_get_reset_status_unauthorized_user(
        self, db: AsyncSession, test_user_with_reset
    ):
        """Test that users cannot access other users' reset requests."""
        service = PasswordResetService(db)

        with pytest.raises(PermissionDeniedError):
            await service.get_reset_status(
                request_id=test_user_with_reset["request"].id,
                user_id="usr_other_user",
            )


@pytest.mark.asyncio
class TestOTPVerification:
    """Tests for OTP verification in password reset."""

    @pytest.fixture
    async def test_reset_with_otp(self, db: AsyncSession):
        """Create reset request with OTP."""
        user = User(
            id="usr_otp_test",
            username="otpuser",
            password_hash=hash_password("OldPassword123!"),
            full_name="OTP Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Create reset request
        now = datetime.now(UTC)
        reset_request = PasswordResetRequest(
            id="prr_otp_test",
            user_id=user.id,
            requested_at=now,
            expires_at=now + timedelta(hours=24),
            admin_approval_status=ApprovalStatus.REJECTED,
        )
        db.add(reset_request)
        await db.flush()

        # Create OTP
        otp_code = "123456"
        otp = OTPRequest(
            id="otp_reset_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PASSWORD_RESET,
            destination_hash=hash_otp("1234567890"),
            otp_hash=hash_otp(otp_code),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(otp)
        await db.flush()

        return {
            "user": user,
            "request": reset_request,
            "otp_code": otp_code,
            "otp": otp,
        }

    @pytest.mark.asyncio
    async def test_verify_otp_success(self, db: AsyncSession, test_reset_with_otp):
        """Test successful OTP verification."""
        service = PasswordResetService(db)
        request = OTPVerificationRequest(
            reset_request_id=test_reset_with_otp["request"].id,
            otp=test_reset_with_otp["otp_code"],
            channel=OTPChannel.SMS,
        )

        response = await service.verify_otp(
            request=request,
            user_id=test_reset_with_otp["user"].id,
        )

        assert response.verified is True
        assert response.channel == OTPChannel.SMS.value

    @pytest.mark.asyncio
    async def test_verify_otp_invalid_code(
        self, db: AsyncSession, test_reset_with_otp
    ):
        """Test OTP verification with invalid code."""
        service = PasswordResetService(db)
        request = OTPVerificationRequest(
            reset_request_id=test_reset_with_otp["request"].id,
            otp="999999",  # Wrong code
            channel=OTPChannel.SMS,
        )

        with pytest.raises(InvalidOTPError):
            await service.verify_otp(
                request=request,
                user_id=test_reset_with_otp["user"].id,
            )

    @pytest.mark.asyncio
    async def test_verify_otp_expired(self, db: AsyncSession):
        """Test OTP verification with expired OTP."""
        user = User(
            id="usr_expired_test",
            username="expireduser",
            password_hash=hash_password("OldPassword123!"),
            full_name="Expired Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Create reset request
        now = datetime.now(UTC)
        reset_request = PasswordResetRequest(
            id="prr_expired_test",
            user_id=user.id,
            requested_at=now,
            expires_at=now + timedelta(hours=24),
            admin_approval_status=ApprovalStatus.PENDING,
        )
        db.add(reset_request)
        await db.flush()

        # Create expired OTP
        otp = OTPRequest(
            id="otp_expired_test",
            user_id=user.id,
            channel=OTPChannel.SMS,
            purpose=OTPPurpose.PASSWORD_RESET,
            destination_hash=hash_otp("1234567890"),
            otp_hash=hash_otp("123456"),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),  # Expired
        )
        db.add(otp)
        await db.flush()

        service = PasswordResetService(db)
        request = OTPVerificationRequest(
            reset_request_id=reset_request.id,
            otp="123456",
            channel=OTPChannel.SMS,
        )

        with pytest.raises(OTPExpiredError):
            await service.verify_otp(
                request=request,
                user_id=user.id,
            )


@pytest.mark.asyncio
class TestPasswordResetCompletion:
    """Tests for password reset completion."""

    @pytest.fixture
    async def test_reset_ready_to_complete(self, db: AsyncSession):
        """Create reset request ready for completion."""
        user = User(
            id="usr_complete_test",
            username="completeuser",
            password_hash=hash_password("OldPassword123!"),
            full_name="Complete Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Create reset request with verification and approval
        now = datetime.now(UTC)
        reset_request = PasswordResetRequest(
            id="prr_complete_test",
            user_id=user.id,
            requested_at=now,
            expires_at=now + timedelta(hours=24),
            admin_approval_status=ApprovalStatus.APPROVED,
            approved_by_id=user.id,
            approved_at=now,
            phone_verified_at=now,  # Verified
        )
        db.add(reset_request)
        await db.flush()

        return {"user": user, "request": reset_request}

    @pytest.mark.asyncio
    async def test_complete_password_reset_success(
        self, db: AsyncSession, test_reset_ready_to_complete
    ):
        """Test successful password reset completion."""
        service = PasswordResetService(db)
        request = CompletePasswordResetRequest(
            reset_request_id=test_reset_ready_to_complete["request"].id,
            new_password="NewSecurePassword123!",
        )

        success = await service.complete_password_reset(
            request=request,
            user_id=test_reset_ready_to_complete["user"].id,
        )

        assert success is True

        # Verify password changed
        user = await service.user_repo.get_by_id(
            test_reset_ready_to_complete["user"].id
        )
        assert user.password_changed_at is not None

    @pytest.mark.asyncio
    async def test_complete_password_reset_weak_password(
        self, db: AsyncSession, test_reset_ready_to_complete
    ):
        """Test password reset with weak password (fails validation)."""
        # Validation fails at schema level, before the service is ever reached.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CompletePasswordResetRequest(
                reset_request_id=test_reset_ready_to_complete["request"].id,
                new_password="weak",  # too short, no uppercase/digit/special
            )

    @pytest.mark.asyncio
    async def test_complete_password_reset_one_time_use(
        self, db: AsyncSession, test_reset_ready_to_complete
    ):
        """Test that password reset cannot be completed twice."""
        service = PasswordResetService(db)
        request = CompletePasswordResetRequest(
            reset_request_id=test_reset_ready_to_complete["request"].id,
            new_password="NewSecurePassword123!",
        )

        # First completion succeeds
        success = await service.complete_password_reset(
            request=request,
            user_id=test_reset_ready_to_complete["user"].id,
        )
        assert success is True

        # Second completion fails (one-time use)
        request2 = CompletePasswordResetRequest(
            reset_request_id=test_reset_ready_to_complete["request"].id,
            new_password="AnotherPassword456!",
        )

        with pytest.raises(InvalidTokenError):
            await service.complete_password_reset(
                request=request2,
                user_id=test_reset_ready_to_complete["user"].id,
            )


@pytest.mark.asyncio
class TestAdminApproval:
    """Tests for admin approval of password resets."""

    @pytest.fixture
    async def test_reset_pending_approval(self, db: AsyncSession):
        """Create reset request pending admin approval."""
        user = User(
            id="usr_approval_test",
            username="approvaluser",
            password_hash=hash_password("OldPassword123!"),
            full_name="Approval Test User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        admin = User(
            id="usr_admin_test",
            username="adminuser",
            password_hash=hash_password("AdminPassword123!"),
            full_name="Admin User",
            organization_id="org_test",
            region_id="reg_test",
            is_active=True,
            is_verified=True,
            status=UserStatus.ACTIVE,
        )
        db.add(admin)
        await db.flush()

        # Create reset request (verified, pending approval)
        now = datetime.now(UTC)
        reset_request = PasswordResetRequest(
            id="prr_approval_test",
            user_id=user.id,
            requested_at=now,
            expires_at=now + timedelta(hours=24),
            admin_approval_status=ApprovalStatus.PENDING,
            phone_verified_at=now,  # Verified by user
        )
        db.add(reset_request)
        await db.flush()

        return {"user": user, "admin": admin, "request": reset_request}

    @pytest.mark.asyncio
    async def test_approve_password_reset(
        self, db: AsyncSession, test_reset_pending_approval
    ):
        """Test admin approving password reset."""
        service = PasswordResetService(db)
        approval_request = PasswordResetApprovalRequest(
            reset_request_id=test_reset_pending_approval["request"].id,
            approve=True,
            reason="User identity verified",
        )

        response = await service.approve_password_reset(
            request=approval_request,
            admin_user_id=test_reset_pending_approval["admin"].id,
        )

        assert response.status == ApprovalStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_reject_password_reset(
        self, db: AsyncSession, test_reset_pending_approval
    ):
        """Test admin rejecting password reset."""
        service = PasswordResetService(db)
        approval_request = PasswordResetApprovalRequest(
            reset_request_id=test_reset_pending_approval["request"].id,
            approve=False,
            reason="Suspicious activity detected",
        )

        response = await service.approve_password_reset(
            request=approval_request,
            admin_user_id=test_reset_pending_approval["admin"].id,
        )

        assert response.status == ApprovalStatus.REJECTED.value
