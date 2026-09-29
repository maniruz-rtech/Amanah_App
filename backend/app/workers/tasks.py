"""
Celery tasks for background processing.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from celery import shared_task

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_push_notification(self, notification_id: str):
    """
    Send a single push notification via FCM.

    Retries up to 3 times on failure.
    """
    async def _send():
        from app.db.session import AsyncSessionFactory
        from app.services import NotificationService

        async with AsyncSessionFactory() as db:
            service = NotificationService(db)
            notification = await service.notification_repo.get_by_id(notification_id)

            if not notification:
                logger.warning("notification_not_found", notification_id=notification_id)
                return False

            success = await service.send_push_notification(notification)
            await db.commit()
            return success

    try:
        return run_async(_send())
    except Exception as exc:
        logger.error("send_push_notification_failed", notification_id=notification_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task
def process_pending_notifications():
    """
    Process all pending notifications.

    Runs periodically via Celery Beat.
    """
    async def _process():
        from app.db.session import AsyncSessionFactory
        from app.services import NotificationService

        async with AsyncSessionFactory() as db:
            service = NotificationService(db)
            results = await service.process_pending_notifications()
            await db.commit()
            return results

    return run_async(_process())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def broadcast_to_responders(self, incident_id: str):
    """
    Find and notify nearby responders for an incident.

    Called when SOS is created.
    """
    async def _broadcast():
        from app.db.session import AsyncSessionFactory
        from app.repositories import IncidentRepository
        from app.services import IncidentService

        async with AsyncSessionFactory() as db:
            service = IncidentService(db)
            incident = await service.incident_repo.get_by_id(incident_id)

            if not incident:
                logger.warning("incident_not_found", incident_id=incident_id)
                return None

            await service._broadcast_to_responders(incident)
            await db.commit()
            return True

    try:
        return run_async(_broadcast())
    except Exception as exc:
        logger.error("broadcast_to_responders_failed", incident_id=incident_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task
def check_expired_broadcasting_incidents():
    """
    Check for incidents broadcasting too long without response.

    Escalates incidents that haven't been accepted within timeout.
    """
    async def _check():
        from app.db.session import AsyncSessionFactory
        from app.repositories import IncidentRepository

        async with AsyncSessionFactory() as db:
            repo = IncidentRepository(db)
            expired = await repo.get_expired_broadcasting_incidents()

            for incident in expired:
                # Queue escalation task
                escalate_incident.delay(incident.id)

            await db.commit()
            return len(expired)

    return run_async(_check())


@celery_app.task(bind=True, max_retries=2)
def escalate_incident(self, incident_id: str):
    """
    Escalate an incident that hasn't received response.

    - Expand search radius
    - Notify admins
    - Optionally contact authorities
    """
    async def _escalate():
        from app.db.session import AsyncSessionFactory
        from app.db.enums import IncidentStatus, NotificationType
        from app.repositories import (
            IncidentRepository,
            NotificationRepository,
            ResponderRepository,
        )

        async with AsyncSessionFactory() as db:
            incident_repo = IncidentRepository(db)
            responder_repo = ResponderRepository(db)
            notification_repo = NotificationRepository(db)

            incident = await incident_repo.get_with_details(incident_id)

            if not incident:
                return None

            if incident.status != IncidentStatus.BROADCASTING:
                # Already accepted or canceled
                return None

            # Get latest location
            if not incident.locations:
                return None

            latest_location = max(incident.locations, key=lambda l: l.captured_at)

            # Expand radius and find more responders
            expanded_radius = settings.responder_search_radius_km * 2

            # Get already-assigned responder IDs
            assigned_ids = [a.responder_id for a in incident.assignments] if incident.assignments else []

            nearby = await responder_repo.find_nearby_responders(
                lat=latest_location.lat,
                lng=latest_location.lng,
                organization_id=incident.organization_id,
                radius_km=expanded_radius,
                exclude_user_ids=assigned_ids,
                limit=10,
            )

            # Assign new responders
            from app.repositories import IncidentAssignmentRepository
            assignment_repo = IncidentAssignmentRepository(db)

            for responder_status, distance_m in nearby:
                await assignment_repo.assign_responder(
                    incident_id=incident.id,
                    responder_id=responder_status.user_id,
                    distance_m=int(distance_m) if distance_m else None,
                )

                await notification_repo.create_notification(
                    user_id=responder_status.user_id,
                    notification_type=NotificationType.INCIDENT_ASSIGNED,
                    title="Urgent: Emergency Alert",
                    body="Someone needs immediate help. Please respond if available.",
                    incident_id=incident.id,
                )

            # TODO: Notify regional admins
            # TODO: Contact emergency services if configured

            await db.commit()

            logger.info(
                "incident_escalated",
                incident_id=incident_id,
                new_responders=len(nearby),
            )

            return len(nearby)

    try:
        return run_async(_escalate())
    except Exception as exc:
        logger.error("escalate_incident_failed", incident_id=incident_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task
def cleanup_expired_data():
    """
    Clean up expired data.

    - Delete expired location data
    - Clean up old OTP requests
    - Archive old audit logs (if configured)
    """
    async def _cleanup():
        from app.db.session import AsyncSessionFactory
        from sqlalchemy import delete
        from app.db.models import EmergencyLocation, OTPRequest

        async with AsyncSessionFactory() as db:
            now = datetime.now(UTC)
            results = {}

            # Delete expired locations
            result = await db.execute(
                delete(EmergencyLocation).where(EmergencyLocation.expires_at < now)
            )
            results["expired_locations"] = result.rowcount

            # Delete old OTP requests (older than 24 hours)
            otp_cutoff = now - timedelta(hours=24)
            result = await db.execute(
                delete(OTPRequest).where(OTPRequest.created_at < otp_cutoff)
            )
            results["old_otps"] = result.rowcount

            await db.commit()

            logger.info("cleanup_completed", **results)
            return results

    return run_async(_cleanup())


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_sms(self, phone_number: str, message: str):
    """
    Send SMS via Twilio or other provider.

    Placeholder for SMS integration.
    """
    try:
        # In production, integrate with Twilio or other SMS provider
        # from twilio.rest import Client
        # client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        # message = client.messages.create(
        #     body=message,
        #     from_=settings.twilio_phone_number,
        #     to=phone_number
        # )

        logger.info("sms_sent", phone=phone_number[:4] + "****")
        return True

    except Exception as exc:
        logger.error("send_sms_failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email(self, to_email: str, subject: str, body: str, html_body: str | None = None):
    """
    Send email via SMTP or email service.

    Placeholder for email integration.
    """
    try:
        # In production, integrate with email service
        # import smtplib
        # from email.mime.text import MIMEText
        # from email.mime.multipart import MIMEMultipart
        #
        # msg = MIMEMultipart()
        # msg["From"] = settings.email_from
        # msg["To"] = to_email
        # msg["Subject"] = subject
        # msg.attach(MIMEText(body, "plain"))
        # if html_body:
        #     msg.attach(MIMEText(html_body, "html"))
        #
        # with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        #     server.starttls()
        #     server.login(settings.smtp_user, settings.smtp_password)
        #     server.send_message(msg)

        logger.info("email_sent", to=to_email)
        return True

    except Exception as exc:
        logger.error("send_email_failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task
def notify_trusted_contacts(incident_id: str):
    """
    Notify user's trusted contacts about an incident.

    Called when SOS is created (if configured).
    """
    async def _notify():
        from app.db.session import AsyncSessionFactory
        from app.core.security import decrypt_field
        from app.repositories import IncidentRepository, TrustedContactRepository

        async with AsyncSessionFactory() as db:
            incident_repo = IncidentRepository(db)
            contact_repo = TrustedContactRepository(db)

            incident = await incident_repo.get_with_details(incident_id)
            if not incident:
                return None

            contacts = await contact_repo.get_user_contacts(incident.created_by_id)

            for contact in contacts:
                # Decrypt phone number
                try:
                    phone = decrypt_field(contact.phone_encrypted)
                except Exception:
                    continue

                # Send SMS to trusted contact
                message = (
                    f"Emergency Alert: {contact.name}, your contact has triggered "
                    f"an SOS alert and may need help. Please try to reach them."
                )

                send_sms.delay(phone, message)

            return len(contacts)

    return run_async(_notify())
