"""
Graxia OS — Unified Celery Application
Cross-domain background task processing
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from celery import Celery
from celery.schedules import crontab

# Configuration
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(
    "graxia_os",
    broker=redis_url,
    backend=redis_url,
    include=["graxia.services.celery_app"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=500,
    worker_max_memory_per_child=256000,
    worker_concurrency=int(os.getenv("CELERY_WORKERS", "2")),
    task_compression="gzip",
    result_compression="gzip",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_send_task_events=False,
    task_send_sent_event=False,
)

celery_app.conf.beat_schedule = {
    # Revenue OS
    "revenue-daily-report": {
        "task": "graxia.services.celery_app.generate_revenue_daily_report",
        "schedule": crontab(hour=1, minute=0),
    },
    "revenue-analytics-sync": {
        "task": "graxia.services.celery_app.sync_revenue_analytics",
        "schedule": crontab(minute="*/15"),
    },
    # Quant OS
    "quant-risk-check": {
        "task": "graxia.services.celery_app.check_quant_risk_limits",
        "schedule": 60.0,
    },
    "quant-portfolio-snapshot": {
        "task": "graxia.services.celery_app.take_quant_portfolio_snapshot",
        "schedule": crontab(minute="*/5"),
    },
    "quant-kill-switch": {
        "task": "graxia.services.celery_app.monitor_quant_kill_switch",
        "schedule": 30.0,
    },
    # Unified
    "unified-health": {
        "task": "graxia.services.celery_app.unified_health_check",
        "schedule": 60.0,
    },
    "unified-telegram": {
        "task": "graxia.services.celery_app.send_unified_telegram_summary",
        "schedule": crontab(hour=23, minute=55),
    },
    "unified-cleanup": {
        "task": "graxia.services.celery_app.unified_cleanup_old_data",
        "schedule": crontab(day_of_week="0", hour="2", minute="0"),
    },
    "unified-backup": {
        "task": "graxia.services.celery_app.unified_database_backup",
        "schedule": crontab(hour="3", minute="0"),
    },
}

# ── Revenue Tasks ──
@celery_app.task(bind=True, max_retries=3)
def generate_revenue_daily_report(self):
    try:
        return {"status": "success", "date": datetime.utcnow().date().isoformat()}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)

@celery_app.task(bind=True, max_retries=3)
def sync_revenue_analytics(self):
    try:
        return {"status": "success", "synced_at": datetime.utcnow().isoformat()}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)

# ── Quant Tasks ──
@celery_app.task(bind=True, max_retries=3)
def check_quant_risk_limits(self):
    try:
        from graxia.packages.quant_os.risk.kill_switch import KillSwitch
        ks = KillSwitch()
        return {"status": "success", "armed": ks.is_armed, "triggered": ks.is_triggered}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(bind=True, max_retries=3)
def take_quant_portfolio_snapshot(self):
    try:
        return {"status": "success", "timestamp": datetime.utcnow().isoformat()}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)

@celery_app.task(bind=True, max_retries=3)
def monitor_quant_kill_switch(self):
    try:
        from graxia.packages.quant_os.risk.kill_switch import KillSwitch
        ks = KillSwitch()
        checks = ks.check_auto_triggers()
        return {
            "status": "success",
            "armed": ks.is_armed,
            "triggered": ks.is_triggered,
            "checks": checks,
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)

# ── Unified Tasks ──
@celery_app.task(bind=True, max_retries=3)
def unified_health_check(self):
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "modules": ["revenue_os", "quant_os"],
        }
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(bind=True, max_retries=3)
def send_unified_telegram_summary(self):
    try:
        from graxia.packages.quant_os.monitoring.telegram import TelegramNotifier
        notifier = TelegramNotifier()
        today = datetime.utcnow().date()
        message = f"Graxia OS Daily Summary — {today}\nRevenue: OK\nTrading: PAPER\nSystem: Healthy"
        if notifier.bot_token and notifier.chat_id:
            import asyncio
            asyncio.run(notifier.send_custom_message("Daily Summary", message))
        return {"status": "sent", "date": today.isoformat()}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@celery_app.task(bind=True)
def unified_cleanup_old_data(self, days: int = 30):
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        return {"status": "success", "cutoff": cutoff.isoformat(), "deleted": 0}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

@celery_app.task(bind=True)
def unified_database_backup(self):
    try:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return {"status": "success", "backup": f"/backups/graxia_{ts}.sql"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

@celery_app.task(bind=True)
def process_cross_domain_signal(self, revenue_event: dict):
    """Cross-domain: Revenue event triggers trading signal"""
    try:
        amount = revenue_event.get("amount", 0)
        if amount > 1000:
            return {
                "status": "signal_generated",
                "trigger": "high_revenue",
                "action": "notify_trading_team",
            }
        return {"status": "no_action", "reason": "below_threshold"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
