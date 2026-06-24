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
    "frequent-scan": {
        "task": "tasks.daily_scan.run",
        "schedule": timedelta(minutes=15),
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
    "job-discovery-frequent": {
        "task": "tasks.job_discovery.run",
        "schedule": timedelta(minutes=20),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "email-processing": {
        "task": "tasks.email_processing.run",
        "schedule": timedelta(minutes=30),
        "options": {"queue": BACKGROUND_QUEUE},
    },
    "autopilot-cycle": {
        "task": "tasks.maintenance.autopilot_cycle",
        "schedule": timedelta(minutes=30),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "outreach-email": {
        "task": "tasks.outreach.email",
        "schedule": timedelta(hours=1),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "leadgen-frequent": {
        "task": "tasks.leadgen.run",
        "schedule": timedelta(minutes=30),
        "options": {"queue": DEFAULT_QUEUE},
    },
    "crm-sync": {
        "task": "tasks.crm.sync",
        "schedule": timedelta(hours=12),
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
    "weekly-cog-evolution": {
        "task": "tasks.cog_evolution.run",
        "schedule": crontab(day_of_week="sunday", hour=10, minute=0),
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
    "win-back-emails": {
        "task": "tasks.funnel_automation.send_win_back_emails",
        "schedule": crontab(hour=10, minute=0),
        "options": {"queue": BACKGROUND_QUEUE},
    },
}
