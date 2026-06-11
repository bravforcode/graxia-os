from celery import Celery

from app.config import settings
from app.tasks.queues import ALL_QUEUES, DEFAULT_QUEUE, TASK_ROUTES
from app.tasks.schedule import BEAT_SCHEDULE

celery_app = Celery(
    "personal_os",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.daily_scan",
        "app.tasks.morning_briefing",
        "app.tasks.follow_up_check",
        "app.tasks.job_discovery",
        "app.tasks.email_processing",
        "app.tasks.weekly_review",
        "app.tasks.maintenance_tasks",
        "app.tasks.backup_tasks",
        "app.tasks.vault_sync",
        "app.tasks.outreach_tasks",
        "app.tasks.leadgen_tasks",
        "app.tasks.crm_sync_tasks",
        "app.tasks.funnel_automation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Bangkok",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_soft_time_limit=300,
    task_time_limit=360,
    task_default_queue=DEFAULT_QUEUE,
    task_queues=ALL_QUEUES,
    task_routes=TASK_ROUTES,
    beat_schedule=BEAT_SCHEDULE,
    result_expires=3600,
)
