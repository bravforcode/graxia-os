"""
7-Day Paper Trading Campaign v2 — Launch tsm_paper_trade.py for multi-asset.

This script orchestrates a 7-day live paper trading campaign using
the TSM (Time-Series Momentum) strategy across multiple asset classes.

It launches tsm_paper_trade.py (NOT gold_bot) with proper configuration.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "reports" / "campaign_7day_v2.json"
LOG_PATH = ROOT / "reports" / "campaign_7day.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("campaign_7day")

# Multi-asset universe for TSM
ASSETS = {
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
    "metals": ["XAUUSD"],
    "indices": ["US30", "NAS100"],
}


def _verify_preflight() -> bool:
    """Run preflight checks before launching."""
    preflight_script = ROOT / "scripts" / "paper_trade_preflight_v2.py"
    if not preflight_script.exists():
        logger.warning("Preflight script not found — skipping")
        return True

    try:
        result = subprocess.run(
            [sys.executable, str(preflight_script)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error(f"Preflight failed:\n{result.stdout}\n{result.stderr}")
            return False
        logger.info("Preflight passed")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Preflight timed out")
        return False


def _launch_tsm(live: bool = False) -> dict[str, Any]:
    """Launch tsm_paper_trade.py for multi-asset trading.

    Args:
        live: If True, execute real broker orders. Default False (paper).

    Returns:
        Launch result dict.
    """
    tsm_script = ROOT / "scripts" / "tsm_paper_trade.py"
    if not tsm_script.exists():
        return {"success": False, "error": "tsm_paper_trade.py not found"}

    cmd = [sys.executable, str(tsm_script)]
    if live:
        cmd.append("--live")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return {
            "success": True,
            "pid": proc.pid,
            "command": " ".join(cmd),
            "assets": ASSETS,
            "mode": "live" if live else "paper",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _create_campaign_report(launch_result: dict[str, Any]) -> dict[str, Any]:
    """Create campaign report."""
    return {
        "campaign": "7day_tsm_v2",
        "start_time": datetime.now(UTC).isoformat(),
        "end_target": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        "strategy": "tsm_time_series_momentum",
        "assets": ASSETS,
        "launch": launch_result,
        "status": "launched" if launch_result.get("success") else "failed",
        "monitoring": {
            "log_file": str(LOG_PATH),
            "report_file": str(REPORT_PATH),
            "heartbeat_file": str(ROOT / "data" / "heartbeat.json"),
        },
    }


def main():
    logger.info("=== 7-Day TSM Campaign v2 ===")
    live = "--live" in sys.argv

    # Step 1: Preflight
    if not _verify_preflight():
        logger.error("Preflight checks failed — aborting")
        sys.exit(1)

    # Step 2: Launch
    launch_result = _launch_tsm(live=live)
    report = _create_campaign_report(launch_result)

    # Step 3: Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str))

    print(f"\n=== 7-Day Campaign Report ===")
    print(f"Status: {report['status']}")
    print(f"Strategy: {report['strategy']}")
    print(f"Assets: {json.dumps(ASSETS, indent=2)}")
    print(f"Report: {REPORT_PATH}")

    if launch_result.get("success"):
        print(f"\n✅ Campaign launched (PID: {launch_result['pid']})")
        print(f"Monitor: tail -f {LOG_PATH}")
    else:
        print(f"\n❌ Launch failed: {launch_result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
