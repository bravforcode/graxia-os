"""
Scheduled task runner for Quant OS.

Manages concurrent execution of multiple scheduled tasks alongside the
primary paper trading session. Tasks run as subprocesses on configurable
interval schedules.

Available tasks (defined in TASKS list):
    - paper-trader: 6-hour London session paper trading
    - quantos-live-logs: MT5 execution log snapshot every hour
    - quantos-spread-heatmap: Spread data collection every 4 hours
"""
import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime

sys.path.insert(0, os.getcwd())

# ── Graceful shutdown via SIGTERM/SIGINT ──────────────────────────────
_shutdown_requested = False


def _shutdown_handler(signum: int, frame) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    print(f"Received signal {signum}, shutting down gracefully...")
    logging.info(f"Received signal {signum}, shutting down gracefully...")


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

from graxia.packages.quant_os.run_paper_trading import PaperTrader
from graxia.packages.quant_os.core.config import get_config, reset_config
from graxia.packages.quant_os.core.enums import TradingMode

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename=f"logs/scheduler_{datetime.now().strftime('%Y%m%d')}.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

PYTHON = sys.executable
SCRIPTS_DIR = os.path.join(os.getcwd(), "scripts")

TASKS = [
    {
        "name": "quantos-live-logs",
        "description": "MT5 execution log snapshot",
        "cmd": [PYTHON, os.path.join(SCRIPTS_DIR, "collect_logs.py"),
                "--mode", "snapshot"],
        "interval_seconds": 3600,
    },
    {
        "name": "quantos-spread-heatmap",
        "description": "Spread data collection into heatmap",
        "cmd": [PYTHON, os.path.join(SCRIPTS_DIR, "spread_heatmap.py"),
                "--interval", "300", "--duration", "14400"],
        "interval_seconds": 14400,
    },
]


async def run_paper_trader():
    reset_config()
    config = get_config()
    config.trading_mode = TradingMode.PAPER
    config.live_trading_enabled = False
    config.max_risk_per_trade_pct = 0.5
    config.max_daily_loss_pct = 2.0
    config.max_drawdown_pct = 15.0
    config.paper_initial_capital = 50000.0
    config.paper_slippage_pips = 0.5
    config.paper_commission_per_lot = 3.5
    config.max_positions = 8
    config.symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
                      "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
    config.mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    config.mt5_server = os.getenv("MT5_SERVER", "Pepperstone-Demo")
    config.mt5_login = int(os.getenv("MT5_LOGIN", "0"))
    config.mt5_password = os.getenv("MT5_PASSWORD", "")
    config.mt5_timeout_ms = int(os.getenv("MT5_TIMEOUT_MS", "10000"))
    trader = PaperTrader(config,
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat=os.getenv("TELEGRAM_CHAT_ID", ""))
    await trader.start(duration_minutes=360)


async def run_subprocess(task_def):
    cmd = task_def["cmd"]
    name = task_def["name"]
    logging.info(f"[{name}] Starting: {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=18000)
        if proc.returncode == 0:
            logging.info(f"[{name}] Completed (rc={proc.returncode})")
        else:
            logging.warning(f"[{name}] Failed (rc={proc.returncode})")
            if stderr:
                logging.warning(f"[{name}] stderr: {stderr.decode(errors='replace')[:500]}")
    except asyncio.TimeoutError:
        logging.warning(f"[{name}] Timed out — killing")
        if proc:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
    except Exception as e:
        logging.error(f"[{name}] Error: {e}")


async def scheduler_loop():
    last_run = {}
    for task in TASKS:
        last_run[task["name"]] = 0

    while not _shutdown_requested:
        now = time.time()
        for task in TASKS:
            name = task["name"]
            interval = task["interval_seconds"]
            if now - last_run[name] >= interval:
                last_run[name] = now
                logging.info(f"[{name}] Dispatch (interval={interval}s)")
                asyncio.ensure_future(run_subprocess(task))
        await asyncio.sleep(30)


async def main():
    logging.info("=" * 60)
    logging.info("SCHEDULER STARTED")
    logging.info(f"Tasks: {[t['name'] for t in TASKS]}")
    logging.info("=" * 60)

    tasks = [
        asyncio.create_task(run_paper_trader()),
        asyncio.create_task(scheduler_loop()),
    ]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logging.info("Scheduler cancelled")
    except Exception as e:
        logging.error(f"Scheduler error: {e}")
    finally:
        # Cancel lingering child tasks
        for t in tasks:
            if not t.done():
                t.cancel()
        logging.info("Scheduler shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
