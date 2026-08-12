"""
Shadow Mode Runner — Long-running production process.
Collects XAUUSD + EURUSD ticks to DuckDB. Sends Telegram alerts.
Run with: python run_shadow.py
"""
import asyncio
import sys
import os
import signal
import threading
from datetime import datetime, UTC

_db_lock = threading.Lock()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import structlog
logger = structlog.get_logger()

shutdown_event = asyncio.Event()


async def main():
    from data.mt5_tick_ingester import MT5TickIngester, MT5IngesterConfig
    from data.duckdb_write_queue import DuckDBWriteQueue
    from data.bar_aggregator import BarAggregator
    from core.event_bus import EventBus
    from core.config import get_settings
    from core.state_store import SystemState, SystemStateEnum
    from monitoring.heartbeat import HeartbeatMonitor
    from monitoring.telegram import TelegramNotifier as TelegramAlerts
    from shadow.shadow_pipeline import ShadowPipeline

    db_path = os.getenv("DUCKDB_PATH", "data/market_data.duckdb")
    state_path = os.getenv("STATE_FILE_PATH", "state/system_state.json")

    event_bus = EventBus()
    write_queue = DuckDBWriteQueue(db_path)
    bar_aggregator = BarAggregator(
        symbols=["XAUUSD", "EURUSD"],
        timeframes=["1m", "5m", "15m", "1h"],
        event_bus=event_bus,
    )
    import json
    state_file = state_path
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = SystemState.from_dict(json.load(f))
    else:
        state = SystemState.default()
    state.system_state = SystemStateEnum.RUNNING.value
    with open(state_file, "w") as f:
        f.write(state.to_json())

    heartbeat_state = {}
    heartbeat = HeartbeatMonitor(heartbeat_state)
    settings = get_settings()
    telegram = TelegramAlerts(
        bot_token=settings.TELEGRAM_BOT_TOKEN,
        chat_id=settings.TELEGRAM_CHAT_ID,
    )
    await telegram.start()

    await write_queue.start()

    import duckdb
    db_conn = duckdb.connect(db_path)
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS shadow_trades (
            signal_id   VARCHAR PRIMARY KEY,
            symbol      VARCHAR NOT NULL,
            direction   VARCHAR NOT NULL,
            entry_price DOUBLE NOT NULL,
            exit_price  DOUBLE,
            stop_loss   DOUBLE,
            take_profit DOUBLE,
            pnl_after_costs DOUBLE,
            cost_estimate   DOUBLE,
            timestamp_utc   VARCHAR NOT NULL,
            status      VARCHAR DEFAULT 'OPEN',
            ledger_hash VARCHAR
        )
    """)

    shadow_pipeline = ShadowPipeline()
    shadow_pipeline.start_session("shadow_live")

    async def _on_shadow_tick(tick: "MT5Tick") -> None:
        # Validate tick data
        try:
            tick_dict = tick.to_dict()
            for key in ("bid", "ask", "last"):
                val = tick_dict.get(key, 0)
                if val is None or val <= 0 or not isinstance(val, (int, float)):
                    logger.warning("invalid_tick", key=key, value=val)
                    return
            if tick_dict.get("bid", 0) > tick_dict.get("ask", 0) * 1.1:
                logger.warning("spread_too_wide", bid=tick_dict["bid"], ask=tick_dict["ask"])
                return
        except Exception as e:
            logger.error("tick_validation_error", error=str(e))
            return

        shadow_pipeline.process_tick(tick_dict)
        signals = shadow_pipeline.get_signals()
        if signals:
            last = signals[-1]
            try:
                with _db_lock:
                    db_conn.execute(
                        """INSERT OR REPLACE INTO shadow_trades
                           (signal_id, symbol, direction, entry_price,
                            stop_loss, take_profit, timestamp_utc, status, ledger_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
                        [
                            last.signal_id, last.symbol, last.direction,
                            last.entry_price, last.stop_loss, last.take_profit,
                            last.timestamp_utc, shadow_pipeline.seal_ledger(),
                        ],
                    )
                # JSONL log for human-readable audit trail
                import json as _json
                log_path = os.getenv("SHADOW_LOG_PATH", "data/shadow_trades.jsonl")
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "a") as _f:
                    _f.write(_json.dumps({
                        "signal_id": last.signal_id,
                        "symbol": last.symbol,
                        "direction": last.direction,
                        "entry_price": last.entry_price,
                        "stop_loss": last.stop_loss,
                        "take_profit": last.take_profit,
                        "timestamp_utc": last.timestamp_utc,
                        "logged_at": datetime.now(UTC).isoformat(),
                    }) + "\n")
            except Exception as e:
                logger.error("shadow_trade_write_error", error=str(e))

    config = MT5IngesterConfig(
        poll_interval_ms=500,
        mt5_login=settings.MT5_LOGIN,
        mt5_password=settings.MT5_PASSWORD,
        mt5_server=settings.MT5_SERVER,
    )
    ingester = MT5TickIngester(
        symbols=["XAUUSD", "EURUSD"],
        event_bus=event_bus,
        write_queue=write_queue,
        config=config,
        on_tick=_on_shadow_tick,
    )

    await heartbeat.start()

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    await telegram.send_alert(
        f"[SHADOW] System started\n"
        f"Server: {settings.MT5_SERVER}\n"
        f"Time: {now}\n"
        f"Symbols: XAUUSD, EURUSD\n"
        f"Mode: Shadow (paper trading)",
        severity="HIGH",
    )

    logger.info("shadow_mode_running")

    def _task_done(task, name="unknown"):
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Task {name} failed: {exc}")
            try:
                asyncio.get_event_loop().create_task(
                    telegram.send_alert(f"CRITICAL: Task {name} crashed: {exc}")
                )
            except Exception:
                pass

    task_specs = [
        (ingester.start(), "ingester"),
        (bar_aggregator.start(), "aggregator"),
        (_stats_loop(write_queue, ingester, telegram), "stats_loop"),
        (_daily_report_loop(write_queue, telegram, db_conn), "daily_report_loop"),
    ]
    tasks = []
    for coro, task_name in task_specs:
        t = asyncio.create_task(coro)
        t.add_done_callback(lambda t, n=task_name: _task_done(t, n))
        tasks.append(t)

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass

    logger.info("shadow_mode_stopping")

    # Cancel all tasks first
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Then cleanup resources
    try:
        await ingester.stop()
    except Exception:
        pass
    try:
        await write_queue.stop()
    except Exception:
        pass
    try:
        await heartbeat.stop()
    except Exception:
        pass
    try:
        bar_aggregator.stop()
    except Exception:
        pass
    try:
        with _db_lock:
            db_conn.close()
    except Exception:
        pass

    state.system_state = SystemStateEnum.HALTED.value
    with open(state_file, "w") as f:
        f.write(state.to_json())

    await telegram.send_alert("[SHADOW] System stopped", severity="MEDIUM")
    logger.info("shadow_mode_stopped")


async def _stats_loop(write_queue, ingester, telegram):
    """Hourly stats to Telegram."""
    while True:
        await asyncio.sleep(3600)
        try:
            stats = write_queue.stats
            await telegram.send_alert(
                f"[SHADOW] Hourly report\n"
                f"Ticks: {stats.total_written}\n"
                f"Flushes: {stats.total_flushes}\n"
                f"Errors: {stats.total_errors}",
                severity="INFO",
            )
        except Exception as e:
            logger.error("stats_loop_error", error=str(e))


async def _daily_report_loop(write_queue, telegram, db_conn):
    """Daily report at 22:00 UTC."""
    while True:
        now = datetime.now(UTC)
        # Sleep until 22:00 UTC
        target = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if now >= target:
            import datetime as dt
            target += dt.timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            with _db_lock:
                tick_count = db_conn.execute("SELECT COUNT(*) FROM ticks").fetchone()[0]

            stats = write_queue.stats
            await telegram.send_alert(
                f"[SHADOW] Daily report\n"
                f"Total ticks in DB: {tick_count}\n"
                f"Ticks today: {stats.total_written}\n"
                f"Errors: {stats.total_errors}\n"
                f"Status: RUNNING",
                severity="DAILY",
            )
        except Exception as e:
            logger.error("daily_report_error", error=str(e))


def handle_shutdown(sig, frame):
    logger.info("shutdown_signal_received", signal=sig)
    shutdown_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    asyncio.run(main())
