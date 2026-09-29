"""
Health, readiness and operational endpoints.

Three endpoints:
  - GET /api/v1/health      — full status; returns 200 always with a
                                ``status: healthy|degraded`` field. Used by
                                external monitors / on-call dashboards.
  - GET /api/v1/ready       — readiness; returns 503 when DB / Redis are
                                down. Used by Kubernetes / load balancers.
  - GET /api/v1/live        — liveness; returns 200 as long as the process
                                is running. No I/O.

The health endpoint provides per-subsystem latency so operators can spot
slow DBs / queues without leaving the request.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DBSession
from app.core.config import settings

logger = structlog.get_logger()

router = APIRouter(tags=["Health"])


async def _check_db(db) -> tuple[bool, float | None, str | None]:
    start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        return True, (time.perf_counter() - start) * 1000.0, None
    except Exception as e:  # noqa: BLE001
        return False, None, str(e)[:200]


async def _check_redis() -> tuple[bool, float | None, str | None]:
    """Best-effort Redis ping. Returns (up, latency_ms, error_msg)."""
    try:
        import redis.asyncio as redis_async  # type: ignore
    except ImportError:
        return False, None, "redis client not installed"

    start = time.perf_counter()
    try:
        client = redis_async.from_url(str(settings.redis_url))
        try:
            await client.ping()
        finally:
            await client.aclose()
        return True, (time.perf_counter() - start) * 1000.0, None
    except Exception as e:  # noqa: BLE001
        return False, None, str(e)[:200]


@router.get("/health")
async def health_check(db: DBSession) -> dict[str, Any]:
    """Operator-facing health probe. Always returns 200."""
    db_up, db_ms, db_err = await _check_db(db)
    rd_up, rd_ms, rd_err = await _check_redis()

    healthy = db_up and rd_up
    return {
        "status":      "healthy" if healthy else "degraded",
        "version":     settings.app_version,
        "environment": settings.environment,
        "timestamp":   datetime.now(UTC).isoformat(),
        "services":    {
            "database": {
                "up":         db_up,
                "latency_ms": db_ms,
                "error":      db_err,
            },
            "redis": {
                "up":         rd_up,
                "latency_ms": rd_ms,
                "error":      rd_err,
            },
        },
    }


@router.get("/ready")
async def readiness_check(db: DBSession, response: Response) -> dict[str, Any]:
    """LB / Kubernetes-facing readiness. Returns 503 when not ready."""
    db_up, _, db_err = await _check_db(db)
    rd_up, _, rd_err = await _check_redis()

    if not (db_up and rd_up):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        await logger.awarning(
            "readiness_failed",
            db_up=db_up, db_err=db_err,
            redis_up=rd_up, redis_err=rd_err,
        )
        return {
            "ready":     False,
            "database":  db_up,
            "redis":     rd_up,
        }
    return {"ready": True}


@router.get("/live")
async def liveness_check() -> dict[str, bool]:
    """Process-alive probe. Never touches I/O."""
    return {"alive": True}
