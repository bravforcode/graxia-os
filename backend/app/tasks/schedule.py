"""Canonical Celery beat schedule for production and dev parity."""
from __future__ import annotations

from datetime import timedelta

from celery.schedules import crontab

from app.tasks.queues import BACKGROUND_QUEUE, CRITICAL_QUEUE, DEFAULT_QUEUE

BEAT_SCHEDULE = {
    "daily-backup": {
        "task": "tasks.backup.run_daily_backup",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": CRITICAL_QUEUE},
    },
    "restore-drill-weekly": {
        "task": "tasks.backup.run_restore_drill",
        "schedule": crontab(day_of_week="sunday", hour=3, minute=0),
        "options": {"queue": CRITICAL_QUEUE},
    },
    "dlq-depth-check": {
        "task": "tasks.maintenance.check_dlq_depth",
        "schedule": timedelta(minutes=15),
        "options": {"queue": CRITICAL_QUEUE},
    },
    "daily-scan": {
        "task": "tasks.daily_scan.run",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "morning-briefing": {
        "task": "tasks.morning_briefing.run",
        "schedule": crontab(hour=8, minute=0),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "follow-up-check": {
        "task": "tasks.follow_up_check.run",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "job-discovery": {
        "task": "tasks.job_discovery.run",
        "schedule": crontab(hour="10,18", minute=0),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "email-processing": {
        "task": "tasks.email_processing.run",
        "schedule": timedelta(minutes=30),
        "options": {"queue": BACKGROUND_QUEUE},
    },
    "weekly-review": {
        "task": "tasks.weekly_review.run",
        "schedule": crontab(day_of_week="sunday", hour=9, minute=30),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "weekly-strategy": {
        "task": "tasks.maintenance.weekly_strategy",
        "schedule": crontab(day_of_week="sunday", hour=8, minute=30),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "identity-snapshot": {
        "task": "tasks.maintenance.identity_snapshot",
        "schedule": crontab(day_of_month=1, hour=10, minute=0),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "obsidian-daily-note": {
        "task": "tasks.maintenance.obsidian_daily_note",
        "schedule": crontab(hour=6, minute=0),
        "options": {"queue": BACKGROUND_QUEUE},
    },
    "obsidian-refresh": {
        "task": "tasks.maintenance.obsidian_refresh",
        "schedule": crontab(hour=6, minute=10),
        "options": {"queue": BACKGROUND_QUEUE},
    },
    "redis-backup": {
        "task": "tasks.backup.run_redis_backup",
        "schedule": crontab(hour=2, minute=30),
        "options": {"queue": BACKGROUND_QUEUE},
    },
    "vault-sync": {
        "task": "tasks.vault_sync.run",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": BACKGROUND_QUEUE},
    },
}
