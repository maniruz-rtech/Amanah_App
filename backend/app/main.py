"""
Amanah - Community Safety & Emergency Response API

Main FastAPI application entry point.
"""

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.websocket import websocket_endpoint

# Set up structured logging
setup_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await logger.ainfo(
        "application_starting",
        environment=settings.environment,
        debug=settings.debug,
    )

    # Initialize database connection pool
    from app.db.session import engine

    await logger.ainfo("database_connected")

    yield

    # Shutdown
    await logger.ainfo("application_shutting_down")

    # Close database connections
    await engine.dispose()
    await logger.ainfo("database_disconnected")


# Create FastAPI application
app = FastAPI(
    title="Amanah API",
    description="Verified Community Safety & Emergency Response Platform",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add request ID to all requests for tracing."""
    import secrets

    request_id = request.headers.get("X-Request-ID") or f"req_{secrets.token_urlsafe(8)}"

    # Bind request ID to structlog context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    return response


# Request logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests with timing."""
    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = time.perf_counter() - start_time

    await logger.ainfo(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        process_time_ms=round(process_time * 1000, 2),
    )

    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    await logger.aerror(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
        },
    )


# Custom exception handlers
from app.core.exceptions import (
    AccountLockedError,
    AccountSuspendedError,
    IncidentNotFoundError,
    InvalidCredentialsError,
    InvalidOTPError,
    InvalidStateTransitionError,
    InvalidTokenError,
    PermissionDeniedError,
    RateLimitError,
    UserNotFoundError,
)


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "invalid_credentials", "message": str(exc)},
    )


@app.exception_handler(InvalidTokenError)
async def invalid_token_handler(request: Request, exc: InvalidTokenError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "invalid_token", "message": str(exc)},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(AccountLockedError)
async def account_locked_handler(request: Request, exc: AccountLockedError):
    return JSONResponse(
        status_code=status.HTTP_423_LOCKED,
        content={
            "error": "account_locked",
            "message": str(exc),
            "locked_until": exc.locked_until.isoformat() if exc.locked_until else None,
        },
    )


@app.exception_handler(AccountSuspendedError)
async def account_suspended_handler(request: Request, exc: AccountSuspendedError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "account_suspended", "message": str(exc)},
    )


@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "permission_denied", "message": str(exc)},
    )


@app.exception_handler(UserNotFoundError)
async def user_not_found_handler(request: Request, exc: UserNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "user_not_found", "message": str(exc)},
    )


@app.exception_handler(IncidentNotFoundError)
async def incident_not_found_handler(request: Request, exc: IncidentNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "incident_not_found", "message": str(exc)},
    )


@app.exception_handler(InvalidStateTransitionError)
async def invalid_state_handler(request: Request, exc: InvalidStateTransitionError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "invalid_state_transition", "message": str(exc)},
    )


@app.exception_handler(InvalidOTPError)
async def invalid_otp_handler(request: Request, exc: InvalidOTPError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "invalid_otp", "message": str(exc)},
    )


@app.exception_handler(RateLimitError)
async def rate_limit_handler(request: Request, exc: RateLimitError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "rate_limit_exceeded", "message": str(exc)},
    )


# Include API router
app.include_router(api_router, prefix="/api/v1")

# WebSocket endpoint
app.add_api_websocket_route("/ws", websocket_endpoint)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Amanah API",
        "version": "1.0.0",
        "description": "Verified Community Safety & Emergency Response Platform",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info",
    )
