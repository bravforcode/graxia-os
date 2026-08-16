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

            # Digital fulfillment - sweep PAID orders missing delivery (locked)
            "digital-fulfillment": {
                "task": "graxia.packages.revenue_os.celery.tasks.digital_fulfillment",
                "schedule": 300.0,  # Every 5 minutes
                "options": {"queue": "default"},
            },

            # Process pending refunds against Stripe (idempotent)
            "process-refunds": {
                "task": "graxia.packages.revenue_os.celery.tasks.process_refunds",
                "schedule": 300.0,  # Every 5 minutes
                "options": {"queue": "default"},
            },

            # Commerce ops agent - autonomous decision cycle (locked)
            "commerce-ops": {
                "task": "graxia.packages.revenue_os.celery.tasks.commerce_ops",
                "schedule": 3600.0,  # Hourly
                "options": {"queue": "default"},
            },

            # Incident alerter - Telegram for MEDIUM+ incidents (sent once)
            "incident-alerter": {
                "task": "graxia.packages.revenue_os.celery.tasks.incident_alerter",
                "schedule": 300.0,  # Every 5 minutes
                "options": {"queue": "critical"},
            },

            # Rollout gate checker - daily autonomy stage readiness (never auto-advances)
            "rollout-gate-checker": {
                "task": "graxia.packages.revenue_os.celery.tasks.rollout_gate_checker",
                "schedule": 86400.0,  # Daily
                "options": {"queue": "reporting"},
            },

            # ── Phase 2 ─────────────────────────────────────────────────
            "shopify-sync": {
                "task": "graxia.packages.revenue_os.celery.tasks.shopify_sync",
                "schedule": 300.0,  # Every 5 min
                "options": {"queue": "default"},
            },
            "supplier-poll": {
                "task": "graxia.packages.revenue_os.celery.tasks.supplier_poll",
                "schedule": 900.0,  # Every 15 min
                "options": {"queue": "default"},
            },
            "ads-sync": {
                "task": "graxia.packages.revenue_os.celery.tasks.ads_sync",
                "schedule": 3600.0,  # Hourly
                "options": {"queue": "default"},
            },
            "backtest-runner": {
                "task": "graxia.packages.revenue_os.celery.tasks.backtest_runner",
                "schedule": 86400.0,  # Nightly
                "options": {"queue": "reporting"},
            },

            # ── Phase 3 ─────────────────────────────────────────────────
            "marketplace-poll": {
                "task": "graxia.packages.revenue_os.celery.tasks.marketplace_poll",
                "schedule": 600.0,  # every 10 min
                "options": {"queue": "default"},
            },
            "inventory-sync": {
                "task": "graxia.packages.revenue_os.celery.tasks.inventory_sync",
                "schedule": 900.0,  # every 15 min
                "options": {"queue": "default"},
            },
            "fx-refresh": {
                "task": "graxia.packages.revenue_os.celery.tasks.fx_refresh",
                "schedule": 86400.0,  # daily
                "options": {"queue": "reporting"},
            },
            "affiliate-review": {
                "task": "graxia.packages.revenue_os.celery.tasks.affiliate_review",
                "schedule": 86400.0,  # daily
                "options": {"queue": "reporting"},
            },
            "payout-recon": {
                "task": "graxia.packages.revenue_os.celery.tasks.payout_recon",
                "schedule": 3600.0,  # hourly
                "options": {"queue": "reporting"},
            },
            "repricing": {
                "task": "graxia.packages.revenue_os.celery.tasks.repricing",
                "schedule": 3600.0,  # hourly
                "options": {"queue": "default"},
            },
            "channel-health": {
                "task": "graxia.packages.revenue_os.celery.tasks.channel_health",
                "schedule": 3600.0,  # hourly
                "options": {"queue": "default"},
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
