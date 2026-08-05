"""
Daily Scheduler — Run Donchian(25)+Vol paper trade check daily.
Saves to logs/ directory. Can be scheduled via Windows Task Scheduler.

Schedule: Run daily at 17:30 ET (22:30 GMT) — after D1 candle close.
"""
import subprocess
import sys
import logging
from pathlib import Path
from datetime import datetime

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
LOG_DIR = BASE / "reports" / "trade_logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / f"paper_trade_{datetime.now().strftime('%Y%m%d')}.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

def run_check():
    try:
        logging.info("Starting daily paper trade check")
        result = subprocess.run(
            [sys.executable, str(BASE / "live_paper_trade.py")],
            capture_output=True, text=True, timeout=120
        )
        logging.info(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            logging.warning(f"STDERR:\n{result.stderr}")
        logging.info(f"Exit code: {result.returncode}")
        return result.stdout
    except Exception as e:
        logging.error(f"Check failed: {e}")
        return f"ERROR: {e}"

if __name__ == "__main__":
    print(run_check())
