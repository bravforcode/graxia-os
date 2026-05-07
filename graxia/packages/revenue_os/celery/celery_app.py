"""
Revenue OS Celery Application Factory
Creates and configures Celery app for 24/7 automation
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import structlog

logger = structlog.get_logger()


def create_revenue_os_celery_app(settings) -> Celery:
    """
    Create and configure Celery application for Revenue OS.

    Args:
        settings: Application settings object

    Returns:
        Celery: Configured Celery application
    """
    app = Celery("graxia_revenue_os")

    app.config_from_object({
        # Broker & Backend
        "broker_url": settings.CELERY_BROKER_URL,
        "result_backend": settings.CELERY_RESULT_BACKEND,

        # Serialization
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],

        # Timezone
        "timezone": "UTC",
        "enable_utc": True,

        # Task Execution
        "task_track_started": True,
        "task_acks_late": True,  # Prevents task loss on worker crash
        "worker_prefetch_multiplier": 1,  # Fair dispatch for long tasks
        "task_reject_on_worker_lost": True,

        # Time Limits
        "task_soft_time_limit": 300,  # 5 min soft limit → raises SoftTimeLimitExceeded
        "task_time_limit": 360,  # 6 min hard kill

        # Testing
        "task_always_eager": settings.APP_ENV == "test",

        # Queues
        "task_queues": (
            Queue("critical", routing_key="critical"),
            Queue("default", routing_key="default"),
            Queue("email", routing_key="email"),
            Queue("reporting", routing_key="reporting"),
        ),
        "task_default_queue": "default",

        # Beat Schedule (24/7 Automation)
        "beat_schedule": {
            # Hourly monitoring - checks system health
            "hourly-monitor": {
                "task": "graxia.packages.revenue_os.celery.tasks.hourly_monitor",
                "schedule": crontab(minute=0),  # Every hour at :00
                "options": {"queue": "critical"},
            },

            # Daily revenue operations - main automation
            "daily-revenue-ops": {
                "task": "graxia.packages.revenue_os.celery.tasks.daily_revenue_ops",
                "schedule": crontab(hour=6, minute=0),  # 06:00 UTC daily
                "options": {"queue": "default"},
            },

            # Weekly review - strategy analysis
            "weekly-review": {
                "task": "graxia.packages.revenue_os.celery.tasks.weekly_review",
                "schedule": crontab(day_of_week=1, hour=7, minute=0),  # Monday 07:00 UTC
                "options": {"queue": "reporting"},
            },

            # Send pending emails - high frequency
            "send-pending-emails": {
                "task": "graxia.packages.revenue_os.celery.tasks.send_pending_emails",
                "schedule": crontab(minute="*/5"),  # Every 5 minutes
                "options": {"queue": "email"},
            },

            # Campaign engine - budget & incident monitoring
            "campaign-engine": {
                "task": "graxia.packages.revenue_os.celery.tasks.campaign_engine",
                "schedule": crontab(minute="*/15"),  # Every 15 minutes
                "options": {"queue": "default"},
            },

            # Process outbox - publish events to Redis Streams
            "process-outbox": {
                "task": "graxia.packages.revenue_os.celery.tasks.process_outbox",
                "schedule": 60.0,  # Every 60 seconds
                "options": {"queue": "critical"},
            },

            # Agent consumers - consume Redis Stream events
            "agent-consumers": {
                "task": "graxia.packages.revenue_os.celery.tasks.agent_consumers",
                "schedule": 30.0,  # Every 30 seconds
                "options": {"queue": "critical"},
            },
        },
    })

    logger.info(
        "revenue_os_celery_app_created",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        queues=["critical", "default", "email", "reporting"],
    )

    return app
