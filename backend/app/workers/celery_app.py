"""
Celery application configuration.
"""

from celery import Celery

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "amanah",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task routing
    task_routes={
        "app.workers.tasks.send_push_notification": {"queue": "notifications"},
        "app.workers.tasks.process_pending_notifications": {"queue": "notifications"},
        "app.workers.tasks.broadcast_to_responders": {"queue": "incidents"},
        "app.workers.tasks.escalate_incident": {"queue": "incidents"},
        "app.workers.tasks.cleanup_expired_data": {"queue": "maintenance"},
        "app.workers.tasks.send_sms": {"queue": "sms"},
        "app.workers.tasks.send_email": {"queue": "email"},
    },
    # Queue settings
    task_default_queue="default",
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Rate limiting
    worker_prefetch_multiplier=1,
    # Result backend settings
    result_expires=3600,  # 1 hour
    # Beat scheduler for periodic tasks
    beat_schedule={
        "process-pending-notifications": {
            "task": "app.workers.tasks.process_pending_notifications",
            "schedule": 30.0,  # Every 30 seconds
        },
        "check-expired-broadcasting-incidents": {
            "task": "app.workers.tasks.check_expired_broadcasting_incidents",
            "schedule": 60.0,  # Every minute
        },
        "cleanup-expired-locations": {
            "task": "app.workers.tasks.cleanup_expired_data",
            "schedule": 3600.0,  # Every hour
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.workers"])
