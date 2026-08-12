"""
Autonomous Engine Dry-Run Simulator
====================================
Runs the engine in dry-run mode for 1 hour, logging all decisions.

Every cycle:
  1. Get live MT5 XAUUSD price
  2. Read MacroRegimeCache (regime)
  3. Check SessionFilter
  4. Check NewsBlackout
  5. Generate simple signal from price action
  6. Call engine.evaluate()
  7. Log decision + guard results

Output: reports/dry_run_{timestamp}.json + summary
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logger = structlog.get_logger(__name__)

REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"

_mt5_initialized = False


def _init_mt5() -> bool:
    """Initialize MT5 once. Returns True if already initialized."""
    global _mt5_initialized
    if _mt5_initialized:
        return True
    try:
        import MetaTrader5 as mt5
        if mt5.initialize(path=MT5_PATH, timeout=15000):
            _mt5_initialized = True
            return True
    except Exception:
        pass
    return False


def _shutdown_mt5():
    """Shutdown MT5 at end of run."""
    global _mt5_initialized
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass
    _mt5_initialized = False


def _get_mt5_price(symbol: str = "XAUUSD") -> dict | None:
    """Get live MT5 tick data."""
    if not _init_mt5():
        return None
    try:
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return {
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": round((tick.ask - tick.bid) * 10, 2),
                "time": datetime.now(UTC).isoformat(),
            }
    except Exception as e:
        logger.warning("mt5.error", error=str(e))
        _shutdown_mt5()
    return None


def _simple_signal(prices: list[float]) -> tuple[str, float]:
    """Trend-aware signal generator using multiple timeframes.

    - Short-term: momentum (5 ticks)
    - Medium-term: MA crossover (5 vs 10)
    - Long-term: trend direction (20-period MA slope)
    - Trend filter: only BUY in uptrend, SELL in downtrend

    Returns (signal, confidence) where signal is BUY/SELL/HOLD.
    """
    if len(prices) < 10:
        return ("HOLD", 0.0)

    # 1. Short-term momentum (last 5 ticks)
    recent5 = prices[-5:]
    momentum = (recent5[-1] - recent5[0]) / recent5[0] * 100

    # 2. MA crossover (5 vs 10)
    ma5 = sum(prices[-5:]) / 5
    ma10 = sum(prices[-10:]) / 10
    ma_cross = (ma5 - ma10) / ma10 * 100

    # 3. Long-term trend (20-period or available)
    period = min(20, len(prices))
    ma20 = sum(prices[-period:]) / period
    trend_slope = (prices[-1] - prices[-period]) / prices[-period] * 100

    # 4. Price position relative to MAs
    above_ma5 = prices[-1] > ma5
    above_ma10 = prices[-1] > ma10
    above_ma20 = prices[-1] > ma20

    # Trend classification
    uptrend = above_ma20 and trend_slope > 0.01
    downtrend = not above_ma20 and trend_slope < -0.01
    ranging = not uptrend and not downtrend

    # Signal scoring
    score = momentum * 0.3 + ma_cross * 0.3 + trend_slope * 0.4

    # Trend filter: only trade in direction of trend
    if uptrend and score > 0.005:
        conf = min(0.65 + abs(score) * 12, 0.95)
        return ("BUY", round(conf, 3))
    elif downtrend and score < -0.005:
        conf = min(0.65 + abs(score) * 12, 0.95)
        return ("SELL", round(conf, 3))
    elif ranging:
        # In ranging market, use mean reversion
        if momentum < -0.03 and not above_ma5:
            conf = min(0.60 + abs(momentum) * 10, 0.90)
            return ("BUY", round(conf, 3))  # Oversold bounce
        elif momentum > 0.03 and above_ma5:
            conf = min(0.60 + abs(momentum) * 10, 0.90)
            return ("SELL", round(conf, 3))  # Overbought fade
        return ("HOLD", round(0.3 + abs(score) * 3, 3))
    else:
        return ("HOLD", round(0.3 + abs(score) * 3, 3))


async def run_dry_run(duration_minutes: int = 60, interval_seconds: int = 60):
    """Run dry simulation for specified duration."""
    from core.agents.autonomous_engine import AutonomousEngine
    from core.canonical.macro_regime import MacroRegimeCache
    from core.news_blackout import NewsBlackout
    from core.session_filter import SessionFilter

    engine = AutonomousEngine()
    regime_cache = MacroRegimeCache()
    session_filter = SessionFilter()
    news_blackout = NewsBlackout()

    # File logging (works even when stdout is redirected)
    log_file = REPORTS_DIR / "dry_run_live.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    flog = open(log_file, "w", encoding="utf-8", buffering=1)  # line-buffered

    def _log(msg: str):
        print(msg)
        flog.write(msg + "\n")
        flog.flush()

    report = {
        "start_time": datetime.now(UTC).isoformat(),
        "duration_minutes": duration_minutes,
        "interval_seconds": interval_seconds,
        "decisions": [],
        "summary": {},
    }

    prices: list[float] = []
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    cycle = 0

    _log(f"\n{'='*60}")
    _log(f"  DRY RUN STARTED -- {duration_minutes} minutes")
    _log(f"  Interval: {interval_seconds}s | Engine: DRY RUN")
    _log("  Kill switch: OFF | All 9 guards: ACTIVE")
    _log(f"{'='*60}\n")

    while time.time() < end_time:
        cycle += 1
        now = datetime.now(UTC)
        elapsed = (time.time() - start_time) / 60

        # 1. Get MT5 price
        price_data = _get_mt5_price()
        if price_data:
            prices.append(price_data["bid"])
            if len(prices) > 100:
                prices = prices[-100:]

        # 2. Get current regime
        regime = regime_cache.get()
        regime_label = regime.label if hasattr(regime, "label") else "NORMAL"

        # 3. Check session
        session_active = session_filter.is_active()
        session_name = session_filter.current_session.value if hasattr(session_filter, "current_session") else "unknown"

        # 4. Check news blackout
        is_news_blocked = news_blackout.is_blocked()

        # 5. Generate signal
        signal, confidence = _simple_signal(prices) if prices else ("HOLD", 0.0)

        # 6. Evaluate
        decision = engine.evaluate(
            symbol="XAUUSD",
            signal=signal,
            confidence=confidence,
            regime_label=regime_label,
            is_news_blocked=is_news_blocked,
            session_active=session_active,
        )

        # 7. Log decision
        decision_record = {
            "cycle": cycle,
            "time": now.isoformat(),
            "elapsed_min": round(elapsed, 1),
            "price": price_data["bid"] if price_data else None,
            "spread": price_data["spread"] if price_data else None,
            "regime": regime_label,
            "session": session_name,
            "session_active": session_active,
            "news_blocked": is_news_blocked,
            "signal": signal,
            "confidence": round(confidence, 3),
            "action": decision.action,
            "reason": decision.reason,
            "guards_checked": len(decision.guards_checked),
            "guards_passed": len(decision.guards_passed),
            "position_pct": decision.position_size_pct,
        }
        report["decisions"].append(decision_record)

        # Print status
        status = "APPROVED" if decision.action != "HOLD" else "REJECTED"
        price_str = f"{price_data['bid']:.2f}" if price_data else "N/A"
        _log(
            f"[{cycle:3d}] {now.strftime('%H:%M:%S')} | "
            f"Price: {price_str} | "
            f"Regime: {regime_label:15s} | "
            f"Session: {session_name:10s} | "
            f"Signal: {signal:4s} ({confidence:.2f}) | "
            f"-> {status}: {decision.action} | "
            f"Guards: {len(decision.guards_passed)}/{len(decision.guards_checked)}"
        )

        # Wait for next cycle
        await asyncio.sleep(interval_seconds)

    # Generate summary
    total = len(report["decisions"])
    approved = sum(1 for d in report["decisions"] if d["action"] != "HOLD")
    rejected = total - approved
    buy_count = sum(1 for d in report["decisions"] if d["action"] == "BUY")
    sell_count = sum(1 for d in report["decisions"] if d["action"] == "SELL")
    hold_count = sum(1 for d in report["decisions"] if d["action"] == "HOLD")

    # Guard rejection breakdown
    guard_rejections = {}
    for d in report["decisions"]:
        if d["action"] == "HOLD":
            reason = d["reason"]
            guard_rejections[reason] = guard_rejections.get(reason, 0) + 1

    report["summary"] = {
        "end_time": datetime.now(UTC).isoformat(),
        "total_cycles": total,
        "approved": approved,
        "rejected": rejected,
        "buy_signals": buy_count,
        "sell_signals": sell_count,
        "hold_signals": hold_count,
        "approval_rate": f"{approved/total*100:.1f}%" if total > 0 else "0%",
        "price_range": {
            "min": min((d["price"] for d in report["decisions"] if d["price"]), default=0),
            "max": max((d["price"] for d in report["decisions"] if d["price"]), default=0),
        },
        "guard_rejections": guard_rejections,
    }

    # Save report
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"dry_run_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    _log(f"\n{'='*60}")
    _log("  DRY RUN COMPLETE")
    _log(f"{'='*60}")
    _log(f"  Duration:    {duration_minutes} minutes")
    _log(f"  Cycles:      {total}")
    _log(f"  Approved:    {approved} ({report['summary']['approval_rate']})")
    _log(f"  Rejected:    {rejected}")
    _log(f"  BUY signals: {buy_count}")
    _log(f"  SELL signals:{sell_count}")
    _log(f"  HOLD signals:{hold_count}")
    _log(f"  Price range: {report['summary']['price_range']['min']:.2f} - {report['summary']['price_range']['max']:.2f}")
    _log("\n  Guard rejections:")
    for reason, count in sorted(guard_rejections.items(), key=lambda x: -x[1]):
        _log(f"    {count:3d}x  {reason}")
    _log(f"\n  Report: {report_path}")
    _log(f"{'='*60}\n")

    _shutdown_mt5()
    flog.close()
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Engine Dry-Run")
    parser.add_argument("--duration", type=int, default=60, help="Duration in minutes (default: 60)")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds (default: 60)")
    args = parser.parse_args()

    asyncio.run(run_dry_run(
        duration_minutes=args.duration,
        interval_seconds=args.interval,
    ))


if __name__ == "__main__":
    main()
