"""
API v1 router aggregation.
"""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.devices import router as devices_router
from app.api.v1.health import router as health_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.otp import router as otp_router
from app.api.v1.password_reset import router as password_reset_router
from app.api.v1.responders import router as responders_router
from app.api.v1.users import router as users_router

api_router = APIRouter()

# Include all routers
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(otp_router)
api_router.include_router(users_router)
api_router.include_router(devices_router)
api_router.include_router(password_reset_router)
api_router.include_router(incidents_router)
api_router.include_router(responders_router)
api_router.include_router(notifications_router)
api_router.include_router(admin_router)
