"""
Heartbeat Monitor — autonomous watchdog for the TSM paper trading bot.

Reads the structured heartbeat JSON written by scripts/tsm_paper_trade.py,
checks freshness, and escalates via Telegram + kill switch when stale.

Usage:
    python -m monitoring.heartbeat_monitor                # default 5-min loop
    python -m monitoring.heartbeat_monitor --once         # single check, exit
    python -m monitoring.heartbeat_monitor --interval 60  # check every 60s

Thresholds:
    - STALE_THRESHOLD_S  = 3600   (1 hour  → Telegram alert)
    - CRITICAL_THRESHOLD_S = 14400 (4 hours → activate kill switch)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

logger = logging.getLogger("heartbeat_monitor")

# ── Thresholds ────────────────────────────────────────────────────
STALE_THRESHOLD_S: int = 3600  # 1 hour  → warning alert
CRITICAL_THRESHOLD_S: int = 14400  # 4 hours → kill switch
CHECK_INTERVAL_S: int = 300  # 5 minutes default loop

# ── Paths ─────────────────────────────────────────────────────────
HEARTBEAT_PATH = BASE / "data" / "tsm_heartbeat.txt"
KILL_SWITCH_STATE = BASE / "data" / "kill_switch_state.json"


def _load_heartbeat() -> dict | None:
    """Load and parse heartbeat file. Returns None if missing or corrupt."""
    if not HEARTBEAT_PATH.exists():
        logger.warning("Heartbeat file missing: %s", HEARTBEAT_PATH)
        return None
    try:
        raw = HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
        # Support legacy plain-timestamp format
        if raw.startswith("{"):
            return json.loads(raw)
        else:
            # Legacy ISO timestamp string
            return {"timestamp_utc": raw}
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read heartbeat: %s", exc)
        return None


def _parse_timestamp(iso_str: str) -> datetime | None:
    """Parse ISO-8601 timestamp, return aware datetime or None."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None


def _heartbeat_age_s(heartbeat: dict) -> float | None:
    """Return age of heartbeat in seconds, or None if unparseable."""
    ts_str = heartbeat.get("timestamp_utc")
    if not ts_str:
        return None
    ts = _parse_timestamp(ts_str)
    if ts is None:
        return None
    return (datetime.now(UTC) - ts).total_seconds()


def _send_telegram_alert(message: str) -> None:
    """Fire-and-forget Telegram alert via core.telegram_notify."""
    try:
        from core.telegram_notify import TelegramNotifier

        notifier = TelegramNotifier()
        notifier.send(message)
    except Exception as exc:
        logger.error("Telegram alert failed: %s", exc)


def _activate_kill_switch(reason: str) -> None:
    """Activate the kill switch programmatically."""
    try:
        from risk.kill_switch import KillSwitch

        ks = KillSwitch(str(KILL_SWITCH_STATE))
        if not ks.is_active():
            ks.activate(reason, source="heartbeat_monitor")
            logger.critical("Kill switch ACTIVATED: %s", reason)
        else:
            logger.info("Kill switch already active, skipping activation")
    except Exception as exc:
        logger.error("Failed to activate kill switch: %s", exc)


def check_heartbeat() -> int:
    """
    Run one heartbeat check cycle.

    Returns:
        0 = healthy
        1 = stale (alert sent)
        2 = critical (kill switch activated)
        3 = no heartbeat file
    """
    heartbeat = _load_heartbeat()
    if heartbeat is None:
        _send_telegram_alert(
            "🚨 *Heartbeat Monitor*: heartbeat file MISSING.\n"
            "The TSM bot may not have started or crashed before writing."
        )
        return 3

    age = _heartbeat_age_s(heartbeat)
    if age is None:
        logger.error("Cannot parse heartbeat timestamp")
        return 3

    age_min = age / 60
    logger.info("Heartbeat age: %.1f minutes", age_min)

    # ── Critical: stale > 4 hours → kill switch ──
    if age > CRITICAL_THRESHOLD_S:
        hours = age / 3600
        msg = (
            f"🚨 *Heartbeat CRITICAL*: no heartbeat for {hours:.1f} hours "
            f"(threshold: {CRITICAL_THRESHOLD_S // 3600}h).\n"
            f"Activating kill switch — all trading halted."
        )
        logger.critical(msg)
        _send_telegram_alert(msg)
        _activate_kill_switch(f"Heartbeat stale {hours:.1f}h (threshold {CRITICAL_THRESHOLD_S // 3600}h)")
        return 2

    # ── Stale: > 1 hour → Telegram warning ──
    if age > STALE_THRESHOLD_S:
        hours = age / 3600
        msg = (
            f"⚠️ *Heartbeat STALE*: no heartbeat for {hours:.1f}h "
            f"(threshold: {STALE_THRESHOLD_S // 3600}h).\n"
            f"Check TSM bot process."
        )
        logger.warning(msg)
        _send_telegram_alert(msg)
        return 1

    # ── Healthy ──
    logger.debug("Heartbeat healthy (age=%.1f min)", age_min)
    return 0


def run_loop(interval_s: int = CHECK_INTERVAL_S) -> None:
    """Run heartbeat check on a loop."""
    logger.info("Heartbeat monitor started (interval=%ds)", interval_s)
    while True:
        try:
            check_heartbeat()
        except Exception as exc:
            logger.exception("Heartbeat check failed: %s", exc)
        time.sleep(interval_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Heartbeat monitor for TSM bot")
    parser.add_argument("--once", action="store_true", help="Single check and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=CHECK_INTERVAL_S,
        help=f"Check interval in seconds (default: {CHECK_INTERVAL_S})",
    )
    parser.add_argument(
        "--heartbeat-path",
        type=str,
        default=None,
        help="Override heartbeat file path",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    global HEARTBEAT_PATH
    if args.heartbeat_path:
        HEARTBEAT_PATH = Path(args.heartbeat_path)

    if args.once:
        rc = check_heartbeat()
        sys.exit(rc)
    else:
        run_loop(interval_s=args.interval)


if __name__ == "__main__":
    main()
