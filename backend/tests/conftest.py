"""
Shared pytest fixtures.

Tests run against a real PostgreSQL/PostGIS database (the models use PostGIS
``Geography`` columns and native PG enums, so SQLite is not an option).

Configuration:
    TEST_DATABASE_URL  postgresql+asyncpg://user:pass@host:port/amanah_test
                       (the database name MUST end in ``_test`` — the schema is
                       dropped and recreated at the start of every session.)

Each test runs inside a transaction that is rolled back afterwards, so tests
never see each other's data.
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import make_url, text
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://amanah:amanah_dev_password@localhost:5434/amanah_test",
)

# Must be set before ``app.core.config`` is imported anywhere.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("ENVIRONMENT", "local")

if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point at a database whose name ends in '_test'")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    from app.db import models  # noqa: F401 — registers models with Base.metadata
    from app.db.base import Base

    eng = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        # Native PG enum types are declared with create_type=False on the columns,
        # so create them explicitly — derived from the models, never hand-listed.
        def _create_enums(sync_conn):
            seen = set()
            for table in Base.metadata.sorted_tables:
                for col in table.columns:
                    if isinstance(col.type, PGEnum) and col.type.name not in seen:
                        seen.add(col.type.name)
                        col.type.create(sync_conn, checkfirst=True)

        await conn.run_sync(_create_enums)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """A session bound to a connection whose outer transaction is rolled back."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            # Reference rows many fixtures assume exist (FK targets).
            from app.db.models import Organization, Region

            session.add(Organization(id="org_test", name="Test Org"))
            await session.flush()
            session.add(Region(id="reg_test", organization_id="org_test", name="Test Region"))
            await session.flush()
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def db_session(db: AsyncSession) -> AsyncSession:
    """Alias of :func:`db` (some test modules use this name)."""
    return db
