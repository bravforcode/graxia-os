"""
Celery Tasks for Quant OS

Background task processing:
- Daily report generation
- Risk monitoring
- Kill switch checks
- Data quality validation
"""

from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timedelta
import os

# Initialize Celery
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(
    "quant_os",
    broker=redis_url,
    backend=redis_url,
    include=["graxia.packages.quant_os.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Beat schedule (periodic tasks)
celery_app.conf.beat_schedule = {
    "daily-report": {
        "task": "graxia.packages.quant_os.tasks.generate_daily_report",
        "schedule": crontab(hour=0, minute=5),  # 00:05 UTC daily
    },
    "risk-check": {
        "task": "graxia.packages.quant_os.tasks.check_risk_limits",
        "schedule": 60.0,  # Every 60 seconds
    },
    "portfolio-snapshot": {
        "task": "graxia.packages.quant_os.tasks.take_portfolio_snapshot",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "kill-switch-monitor": {
        "task": "graxia.packages.quant_os.tasks.monitor_kill_switch",
        "schedule": 30.0,  # Every 30 seconds
    },
    "data-quality-check": {
        "task": "graxia.packages.quant_os.tasks.check_data_quality",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes
    },
    "telegram-daily-summary": {
        "task": "graxia.packages.quant_os.tasks.send_telegram_daily_summary",
        "schedule": crontab(hour=23, minute=55),  # 23:55 UTC daily
    },
}


@celery_app.task(bind=True, max_retries=3)
def generate_daily_report(self):
    """Generate daily trading report"""
    try:
        from .monitoring.telegram import TelegramNotifier
        
        # Calculate metrics
        today = datetime.utcnow().date()
        
        # Placeholder - would query database
        report_data = {
            "date": today.isoformat(),
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "daily_pnl": 0.0,
            "cumulative_pnl": 0.0,
            "drawdown_pct": 0.0,
            "open_positions": 0,
        }
        
        # Send Telegram notification if configured
        notifier = TelegramNotifier()
        if notifier.bot_token:
            asyncio = __import__("asyncio")
            asyncio.run(notifier.notify_daily_report(**report_data))
        
        return {"status": "success", "date": report_data["date"]}
    
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def check_risk_limits(self):
    """Check risk limits and trigger alerts if breached"""
    try:
        from .risk.kill_switch import KillSwitch
        from .core.config import get_config
        
        config = get_config()
        kill_switch = KillSwitch()
        
        # Check various risk conditions
        checks = {
            "daily_loss": False,
            "drawdown": False,
            "exposure": False,
            "consecutive_losses": False,
        }
        
        # Would query database for actual metrics
        # For now, placeholder
        
        if any(checks.values()):
            # Trigger kill switch if any check failed
            # kill_switch.trigger_auto(checks)
            pass
        
        return {"status": "success", "checks": checks}
    
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, max_retries=3)
def take_portfolio_snapshot(self):
    """Take portfolio snapshot every 5 minutes"""
    try:
        from .data.models import PortfolioSnapshot
        from .core.config import get_config
        from decimal import Decimal
        
        config = get_config()
        
        snapshot_data = {
            "snapshot_date": datetime.utcnow().date(),
            "balance": Decimal("10000.00"),
            "equity": Decimal("10000.00"),
            "floating_pnl": Decimal("0.00"),
            "daily_pnl": Decimal("0.00"),
            "daily_pnl_pct": Decimal("0.00"),
            "open_positions": 0,
            "daily_trades": 0,
            "win_trades_day": 0,
            "drawdown_pct": Decimal("0.00"),
            "peak_equity": Decimal("10000.00"),
            "portfolio_exposure_pct": Decimal("0.00"),
            "trading_mode": config.trading_mode.value,
        }
        
        # Would save to database
        # PortfolioSnapshot(**snapshot_data)
        
        return {"status": "success", "timestamp": datetime.utcnow().isoformat()}
    
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def monitor_kill_switch(self):
    """Monitor kill switch status every 30 seconds"""
    try:
        from .risk.kill_switch import KillSwitch
        
        kill_switch = KillSwitch()
        
        # Check auto-trigger conditions
        checks = kill_switch.check_auto_triggers()
        
        if checks["should_trigger"]:
            # Trigger kill switch
            kill_switch.trigger_auto(checks["reasons"])
            
            # Send alert
            from .monitoring.telegram import TelegramNotifier
            notifier = TelegramNotifier()
            if notifier.bot_token:
                import asyncio
                asyncio.run(notifier.notify_kill_switch(
                    trigger_type="AUTO",
                    reason=", ".join(checks["reasons"]),
                    triggered_by="system"
                ))
        
        return {
            "status": "success",
            "armed": kill_switch.is_armed,
            "triggered": kill_switch.is_triggered,
        }
    
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(bind=True, max_retries=3)
def check_data_quality(self):
    """Check data quality every 10 minutes"""
    try:
        from .data.quality_gate import DataQualityGate
        
        gate = DataQualityGate()
        
        # Run data quality checks
        # Would fetch actual data
        check_results = []
        
        all_passed = gate.all_checks_passed(check_results)
        
        return {
            "status": "success",
            "all_passed": all_passed,
            "checks_count": len(check_results),
        }
    
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(bind=True, max_retries=3)
def send_telegram_daily_summary(self):
    """Send daily summary to Telegram"""
    try:
        from .monitoring.telegram import TelegramNotifier
        
        notifier = TelegramNotifier()
        
        if not notifier.bot_token or not notifier.chat_id:
            return {"status": "skipped", "reason": "Telegram not configured"}
        
        today = datetime.utcnow().date()
        
        # Generate summary message
        message = f"""
📊 <b>Daily Trading Summary — {today}</b>

<b>Trading Mode:</b> PAPER
<b>Total Trades:</b> 0
<b>Open Positions:</b> 0

<b>Today's P&L:</b> $0.00
<b>Cumulative P&L:</b> $0.00

<i>Report generated at {datetime.utcnow().strftime('%H:%M')} UTC</i>
"""
        
        import asyncio
        asyncio.run(notifier.send_custom_message(
            title="Daily Summary",
            content=message,
        ))
        
        return {"status": "sent", "date": today.isoformat()}
    
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True)
def process_trading_signal(self, signal_data: dict):
    """Process trading signal from webhook"""
    try:
        from .strategies.base import Signal
        from .execution.manager import OrderManager
        
        # Create signal from data
        signal = Signal.create(
            strategy_id=signal_data.get("strategy", "unknown"),
            symbol=signal_data["symbol"],
            signal_type=signal_data["action"].upper(),
            confidence=signal_data.get("confidence", 0.5),
            entry_price=signal_data.get("price"),
            stop_loss=signal_data.get("sl"),
            take_profit=signal_data.get("tp"),
        )
        
        # Process through order manager
        # order_manager = OrderManager()
        # order = order_manager.process_signal(signal)
        
        return {
            "status": "success",
            "signal_id": str(signal.id),
            "symbol": signal.symbol,
        }
    
    except Exception as exc:
        # Don't retry - signal processing failures should be investigated
        return {"status": "error", "error": str(exc)}


@celery_app.task(bind=True)
def cleanup_old_data(self, days: int = 30):
    """Clean up old data (run weekly)"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Would clean up old:
        # - Order state history
        # - Data quality runs
        # - Audit logs older than retention period
        
        return {
            "status": "success",
            "cutoff_date": cutoff_date.isoformat(),
            "deleted_records": 0,
        }
    
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@celery_app.task(bind=True)
def backup_database(self):
    """Backup database (run daily)"""
    try:
        import subprocess
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = f"/backups/quant_os_{timestamp}.sql"
        
        # Would run: pg_dump command
        # subprocess.run([
        #     "pg_dump",
        #     "-h", "quant-db",
        #     "-U", "postgres",
        #     "-d", "quant_os",
        #     "-f", backup_file
        # ])
        
        return {
            "status": "success",
            "backup_file": backup_file,
            "timestamp": timestamp,
        }
    
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# Add periodic cleanup task
celery_app.conf.beat_schedule["cleanup-old-data"] = {
    "task": "graxia.packages.quant_os.tasks.cleanup_old_data",
    "schedule": crontab(day_of_week="0", hour="2", minute="0"),  # Weekly Sunday 2 AM
}

# Add backup task
celery_app.conf.beat_schedule["backup-database"] = {
    "task": "graxia.packages.quant_os.tasks.backup_database",
    "schedule": crontab(hour="3", minute="0"),  # Daily 3 AM
}
