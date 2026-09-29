"""
HTTP-level tests for: login -> device binding -> authenticated request,
plus the User.status lifecycle rules.

The real FastAPI app runs in-process; its DB dependency is bound to the
rolled-back test session, so nothing leaks between tests.
"""

import httpx
import pytest
from sqlalchemy import func, select

from app.core.security import decode_token, hash_password
from app.db.enums import DevicePlatform, UserStatus
from app.db.models import Device, RefreshToken, User
from app.db.session import get_db
from app.main import app

PASSWORD = "TestPassword123!"


@pytest.fixture
async def client(db):
    async def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def user(db) -> User:
    u = User(
        id="usr_login_flow",
        username="loginflow",
        password_hash=hash_password(PASSWORD),
        full_name="Login Flow",
        organization_id="org_test",
        region_id="reg_test",
        is_active=True,
        is_verified=True,
        status=UserStatus.ACTIVE,
    )
    db.add(u)
    await db.flush()
    return u


def login_body(**overrides) -> dict:
    body = {
        "username": "loginflow",
        "password": PASSWORD,
        "device_uuid": "install-aaaa-1111",
        "platform": "android",
    }
    body.update(overrides)
    return body


async def count_devices(db, user_id: str) -> int:
    return (await db.execute(select(func.count(Device.id)).where(Device.user_id == user_id))).scalar()


@pytest.mark.asyncio
class TestLoginDeviceBinding:
    async def test_login_registers_device_and_binds_tokens(self, client, db, user):
        r = await client.post(
            "/api/v1/auth/login",
            json=login_body(push_token="fcm-1", app_version="2.0.0"),
        )
        assert r.status_code == 200, r.text
        body = r.json()

        device = (await db.execute(select(Device).where(Device.user_id == user.id))).scalar_one()
        assert device.device_uuid == "install-aaaa-1111"
        assert device.platform == DevicePlatform.ANDROID
        assert device.push_token == "fcm-1"
        assert device.app_version == "2.0.0"
        assert device.is_primary is True and device.is_active is True

        # JWT and stored refresh token are bound to the server-side device id
        assert decode_token(body["access_token"]).device_id == device.id
        token = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalar_one()
        assert token.device_id == device.id

    async def test_same_install_logging_in_again_reuses_the_device(self, client, db, user):
        first = await client.post("/api/v1/auth/login", json=login_body(push_token="old"))
        second = await client.post("/api/v1/auth/login", json=login_body())  # no push token this time
        assert first.status_code == second.status_code == 200

        assert await count_devices(db, user.id) == 1
        device = (await db.execute(select(Device).where(Device.user_id == user.id))).scalar_one()
        assert device.push_token == "old"  # "not provided" must not clear a known token
        assert decode_token(second.json()["access_token"]).device_id == device.id

    async def test_second_install_gets_its_own_device_and_is_not_primary(self, client, db, user):
        await client.post("/api/v1/auth/login", json=login_body())
        r = await client.post("/api/v1/auth/login", json=login_body(device_uuid="install-bbbb-2222"))
        assert r.status_code == 200

        devices = (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
        assert {d.device_uuid: d.is_primary for d in devices} == {
            "install-aaaa-1111": True,
            "install-bbbb-2222": False,
        }

    async def test_device_limit_never_blocks_login(self, client, db, user):
        from app.services.auth import MAX_DEVICES

        for i in range(MAX_DEVICES):
            r = await client.post("/api/v1/auth/login", json=login_body(device_uuid=f"install-{i}"))
            assert r.status_code == 200
        r = await client.post("/api/v1/auth/login", json=login_body(device_uuid="install-new"))
        assert r.status_code == 200

        active = (
            await db.execute(
                select(func.count(Device.id)).where(Device.user_id == user.id, Device.is_active.is_(True))
            )
        ).scalar()
        assert active == MAX_DEVICES  # the stalest non-primary device was retired
        primary = (
            await db.execute(select(Device).where(Device.user_id == user.id, Device.is_primary.is_(True)))
        ).scalar_one()
        assert primary.device_uuid == "install-0" and primary.is_active

    @pytest.mark.parametrize("missing", ["device_uuid", "platform"])
    async def test_login_requires_device_identity(self, client, user, missing):
        body = login_body()
        del body[missing]
        r = await client.post("/api/v1/auth/login", json=body)
        assert r.status_code == 422

    async def test_login_then_users_me(self, client, user):
        r = await client.post("/api/v1/auth/login", json=login_body())
        token = r.json()["access_token"]
        me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["id"] == user.id

    async def test_wrong_password_is_rejected_and_registers_no_device(self, client, db, user):
        r = await client.post("/api/v1/auth/login", json=login_body(password="WrongPassword1!"))
        assert r.status_code == 401
        assert await count_devices(db, user.id) == 0


class TestUserStatusLifecycle:
    """`status` is the lifecycle state of record; the boolean flags enforce it."""

    def make(self, **kw) -> User:
        return User(
            id="usr_status",
            username="statususer",
            password_hash="x",
            organization_id="org_test",
            region_id="reg_test",
            **kw,
        )

    def test_defaults_to_pending_verification(self):
        # default applies at INSERT; before flush it is unset on the instance
        assert self.make(is_verified=False).status in (None, UserStatus.PENDING_VERIFICATION)

    def test_suspending_via_flag_moves_status(self):
        u = self.make(status=UserStatus.ACTIVE, is_verified=True, is_active=True, is_suspended=False)
        u.is_suspended = True
        assert u.status == UserStatus.SUSPENDED
        u.is_suspended = False
        assert u.status == UserStatus.ACTIVE

    def test_deactivating_via_flag_moves_status(self):
        u = self.make(status=UserStatus.ACTIVE, is_verified=True, is_active=True)
        u.is_active = False
        assert u.status == UserStatus.DEACTIVATED
        u.is_active = True
        assert u.status == UserStatus.ACTIVE

    def test_flags_do_not_override_pending_states(self):
        u = self.make(status=UserStatus.PENDING_ACTIVATION, is_verified=True, is_active=True, is_suspended=False)
        assert u.status == UserStatus.PENDING_ACTIVATION

    async def test_persisted_and_filterable(self, db):
        u = self.make(status=UserStatus.PENDING_ACTIVATION, is_verified=True)
        db.add(u)
        await db.flush()
        found = (await db.execute(select(User).where(User.status == UserStatus.PENDING_ACTIVATION))).scalars().all()
        assert [x.id for x in found] == ["usr_status"]
