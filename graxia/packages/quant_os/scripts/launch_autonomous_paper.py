"""
Launch Autonomous Trading Loop — Paper Mode

Runs the full ChartMonitor → LLM DecisionEngine → OrderExecutor pipeline
in paper trading mode (no real money).

Usage:
    python scripts/launch_autonomous_paper.py
    python scripts/launch_autonomous_paper.py --symbols XAUUSD,BTCUSD
    python scripts/launch_autonomous_paper.py --timeframes 15m,1h
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch autonomous trading loop (paper mode)")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols (default: from .env AUTO_SYMBOLS)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default=None,
        help="Comma-separated timeframes (default: from .env AUTO_TIMEFRAMES)",
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=None,
        help="Chart poll interval in seconds",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Minimum LLM confidence to trade (0.0-1.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run one cycle and exit (for testing)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Override env vars if CLI args provided
    if args.symbols:
        os.environ["AUTO_SYMBOLS"] = args.symbols
    if args.timeframes:
        os.environ["AUTO_TIMEFRAMES"] = args.timeframes
    if args.poll_seconds:
        os.environ["AUTO_CHART_POLL_SECONDS"] = str(args.poll_seconds)
    if args.min_confidence:
        os.environ["AUTO_LLM_MIN_CONFIDENCE"] = str(args.min_confidence)

    # Force paper mode
    os.environ["AUTO_TRADING_MODE"] = "paper"

    from autonomous.config import (
        CHART_POLL_SECONDS,
        LLM_MIN_CONFIDENCE,
        SYMBOLS,
        TIMEFRAMES,
        TRADING_MODE,
    )

    print("=" * 60)
    print("  AUTONOMOUS TRADING LOOP — PAPER MODE")
    print("=" * 60)
    print(f"  Symbols:      {', '.join(SYMBOLS)}")
    print(f"  Timeframes:   {', '.join(TIMEFRAMES)}")
    print(f"  Poll:         {CHART_POLL_SECONDS}s")
    print(f"  Min Conf:     {LLM_MIN_CONFIDENCE}")
    print(f"  Mode:         {TRADING_MODE}")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] Running one cycle...")
        from autonomous.chart_monitor import ChartMonitor
        from autonomous.decision_engine import DecisionEngine

        monitor = ChartMonitor()
        engine = DecisionEngine()

        for symbol in SYMBOLS:
            for tf in TIMEFRAMES:
                try:
                    snapshot = await monitor.collect_snapshot(symbol, tf)
                    decision = await engine.analyze(snapshot)
                    print(
                        f"  {symbol}/{tf}: {decision.direction.value} "
                        f"conf={decision.confidence:.2f} "
                        f"entry={decision.entry} sl={decision.stop_loss} tp={decision.take_profit}"
                    )
                except Exception as e:
                    print(f"  {symbol}/{tf}: ERROR — {e}")

        print("\n[DRY RUN] Done.")
        return

    # Full autonomous loop
    from autonomous.orchestrator import AutonomousOrchestrator

    orchestrator = AutonomousOrchestrator()

    print("\nStarting autonomous loop... Press Ctrl+C to stop.\n")

    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
