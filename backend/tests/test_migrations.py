"""
Migration tests — the guard against model/schema drift.

Each test builds a *scratch* database (created and dropped here, never the dev
or shared test database) and runs the real ``alembic`` CLI against it:

1. empty database          -> ``upgrade head`` -> ``alembic check`` is clean
2. existing 007 database   -> seeded with data -> ``upgrade head`` -> data kept,
   ``users.status`` back-filled from the legacy flags, ``alembic check`` clean
3. legacy "create_all + stamp" database -> ``upgrade head`` converges as well

``alembic check`` exits non-zero when the models differ from the migrated
schema, so any model change without a migration fails this file.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE_URL = make_url(
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://amanah:amanah_dev_password@localhost:5434/amanah_test",
    )
)


def alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url, "ENVIRONMENT": "local"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300,
    )


def assert_ok(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, f"{proc.args}\nSTDOUT:\n{proc.stdout[-3000:]}\nSTDERR:\n{proc.stderr[-3000:]}"


@pytest.fixture
async def scratch_url():
    """A brand-new empty PostGIS database, dropped afterwards."""
    name = f"amanah_mig_{uuid.uuid4().hex[:8]}_test"
    admin = create_async_engine(BASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = BASE_URL.set(database=name).render_as_string(hide_password=False)
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    await eng.dispose()
    try:
        yield url
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()


async def test_fresh_database_migrates_to_models(scratch_url):
    assert_ok(alembic(scratch_url, "upgrade", "head"))
    check = alembic(scratch_url, "check")
    assert check.returncode == 0, f"schema drift after upgrade head:\n{check.stdout[-3000:]}{check.stderr[-3000:]}"


async def test_existing_007_database_with_data_upgrades(scratch_url):
    assert_ok(alembic(scratch_url, "upgrade", "007_users_h3_columns"))

    eng = create_async_engine(scratch_url)
    async with eng.begin() as conn:
        await conn.execute(text("INSERT INTO organizations (id, name, is_active) VALUES ('org_1', 'Org', true)"))
        await conn.execute(text(
            "INSERT INTO regions (id, organization_id, name, timezone, is_active) "
            "VALUES ('reg_1', 'org_1', 'Reg', 'UTC', true)"))
        # (id, is_active, is_verified, is_suspended) -> expected status
        for uid, active, verified, suspended in [
            ("usr_active", True, True, False),
            ("usr_pending", True, False, False),
            ("usr_susp", True, True, True),
            ("usr_off", False, True, False),
        ]:
            await conn.execute(text(
                "INSERT INTO users (id, organization_id, region_id, username, phone_encrypted, phone_hash, "
                "password_hash, mfa_enabled, is_active, is_verified, is_suspended, failed_login_attempts) "
                "VALUES (:id, 'org_1', 'reg_1', :id, '\\x00', 'h', 'x', false, :a, :v, :s, 0)"),
                {"id": uid, "a": active, "v": verified, "s": suspended})
        await conn.execute(text("UPDATE users SET mfa_secret = 'JBSWY3DPEHPK3PXP' WHERE id = 'usr_active'"))
        await conn.execute(text(
            "INSERT INTO devices (id, user_id, fcm_token, os_name, is_active) "
            "VALUES ('dev_old', 'usr_active', 'tok-1', 'iOS', true)"))
        await conn.execute(text(
            "INSERT INTO incidents (id, organization_id, region_id, created_by_id, incident_type, severity, "
            "status, silent_mode, started_at) VALUES ('inc_1', 'org_1', 'reg_1', 'usr_active', 'sos', 'high', "
            "'broadcasting', false, now())"))
    await eng.dispose()

    assert_ok(alembic(scratch_url, "upgrade", "head"))

    eng = create_async_engine(scratch_url)
    async with eng.connect() as conn:
        statuses = dict((await conn.execute(text("SELECT id, status::text FROM users"))).all())
        incident = (await conn.execute(text("SELECT status::text, incident_type::text FROM incidents"))).one()
        count = (await conn.execute(text("SELECT count(*) FROM users"))).scalar()
    await eng.dispose()

    assert count == 4
    assert statuses == {
        "usr_active": "active",
        "usr_pending": "pending_verification",
        "usr_susp": "suspended",
        "usr_off": "deactivated",
    }
    assert incident == ("broadcasting", "sos")

    # device identity (009): legacy row keeps its token, gets a stable uuid/platform/primary flag
    eng = create_async_engine(scratch_url)
    async with eng.connect() as conn:
        dev = (await conn.execute(text(
            "SELECT device_uuid, platform::text, push_token, is_primary FROM devices WHERE id = 'dev_old'"))).one()
        blob = (await conn.execute(text(
            "SELECT totp_secret_encrypted FROM users WHERE id = 'usr_active'"))).scalar()
        plain_col = (await conn.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'mfa_secret'"))).scalar()
    await eng.dispose()
    assert dev == ("dev_old", "ios", "tok-1", True)
    from app.core.security import decrypt_field
    assert decrypt_field(bytes(blob)) == "JBSWY3DPEHPK3PXP"  # migrated, encrypted, not lost
    assert plain_col == 0
    check = alembic(scratch_url, "check")
    assert check.returncode == 0, f"schema drift after upgrade head:\n{check.stdout[-3000:]}{check.stderr[-3000:]}"


async def test_legacy_create_all_and_stamp_database_converges(scratch_url):
    """DBs bootstrapped by scripts/init_schema_from_models.py (pre-`status`) then stamped at 007."""
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from sqlalchemy.dialects.postgresql import ENUM as PGEnum

    eng = create_async_engine(scratch_url)

    def build(sync_conn):
        seen = set()
        for table in Base.metadata.sorted_tables:
            for col in table.columns:
                if isinstance(col.type, PGEnum) and col.type.name not in seen:
                    seen.add(col.type.name)
                    col.type.create(sync_conn, checkfirst=True)
        Base.metadata.create_all(sync_conn)
        # emulate the legacy bootstrap that predates users.status
        sync_conn.execute(text("DROP INDEX idx_users_status"))
        sync_conn.execute(text("ALTER TABLE users DROP COLUMN status"))
        sync_conn.execute(text("DROP TYPE user_status_enum"))
        # ...and the old device shape / plaintext TOTP column (009)
        sync_conn.execute(text("ALTER TABLE devices DROP CONSTRAINT uq_devices_user_device_uuid"))
        sync_conn.execute(text("ALTER TABLE devices RENAME COLUMN push_token TO fcm_token"))
        sync_conn.execute(text("ALTER TABLE devices RENAME COLUMN last_seen_at TO last_used_at"))
        sync_conn.execute(text("ALTER TABLE devices DROP COLUMN device_uuid, DROP COLUMN platform, DROP COLUMN is_primary"))
        sync_conn.execute(text("DROP TYPE device_platform_enum"))
        sync_conn.execute(text("ALTER TABLE users DROP COLUMN totp_secret_encrypted, DROP COLUMN created_by_id"))
        sync_conn.execute(text("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR(32)"))

    async with eng.begin() as conn:
        await conn.run_sync(build)
    await eng.dispose()

    assert_ok(alembic(scratch_url, "stamp", "007_users_h3_columns"))
    assert_ok(alembic(scratch_url, "upgrade", "head"))
    check = alembic(scratch_url, "check")
    assert check.returncode == 0, f"schema drift after upgrade head:\n{check.stdout[-3000:]}{check.stderr[-3000:]}"
