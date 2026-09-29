"""
One-shot bootstrap: drop public schema, recreate from current ORM models.

Used because the legacy Alembic 001 migration drifted significantly from the
SQLAlchemy models (missing columns, missing enum types, timezone-naive
timestamps, etc.). Running create_all from the models is the simplest way
to get a schema that matches the actual code.

After this runs, ``alembic stamp head`` should be invoked separately to
align Alembic's version table.
"""

import asyncio
import sys
import traceback

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
from app.db import enums as E
from app.db import models  # noqa: F401 — registers models with Base.metadata


ENUMS = [
    ("incident_type_enum",         [v.value for v in E.IncidentType]),
    ("incident_severity_enum",     [v.value for v in E.IncidentSeverity]),
    ("incident_status_enum",       [v.value for v in E.IncidentStatus]),
    ("assignment_status_enum",     [v.value for v in E.AssignmentStatus]),
    ("location_source_enum",       [v.value for v in E.LocationSource]),
    ("incident_event_type_enum",   [v.value for v in E.IncidentEventType]),
    ("notification_type_enum",     [v.value for v in E.NotificationType]),
    ("delivery_status_enum",       [v.value for v in E.DeliveryStatus]),
    ("otp_channel_enum",           [v.value for v in E.OTPChannel]),
    ("otp_purpose_enum",           [v.value for v in E.OTPPurpose]),
    ("approval_status_enum",       [v.value for v in E.ApprovalStatus]),
    ("approval_request_type_enum", [v.value for v in E.ApprovalRequestType]),
]


async def main() -> int:
    try:
        async with engine.begin() as conn:
            for name, values in ENUMS:
                vs = ", ".join(f"'{v}'" for v in values)
                await conn.execute(text(f"CREATE TYPE {name} AS ENUM ({vs});"))
            print(f">>> created {len(ENUMS)} enum types")
            await conn.run_sync(Base.metadata.create_all)
            print(f">>> created {len(Base.metadata.tables)} tables from models")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
