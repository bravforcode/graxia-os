#!/usr/bin/env python3
"""
MT5 Paper Trading Setup — Connect to Pepperstone Demo and validate.

Steps:
1. Install MetaTrader5 Python package (if not installed)
2. Connect to MT5 terminal
3. Validate account (demo)
4. Check symbol specs (XAUUSD, XAGUSD, XPDUSD, XPTUSD)
5. Pull latest tick data for spread measurement
6. Start continuous spread logging

Usage:
    python scripts/setup_mt5_paper.py
    python scripts/setup_mt5_paper.py --check-only
    python scripts/setup_mt5_paper.py --measure-spread --duration 3600
"""

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT_PATH = ROOT / "reports" / "mt5_setup_status.json"
SPREAD_LOG = ROOT / "data" / "spread_measurement.jsonl"

SYMBOLS = ["XAUUSD", "XAGUSD", "XPDUSD", "XPTUSD"]


def check_mt5_installed() -> bool:
    """Check if MetaTrader5 package is installed."""
    try:
        import MetaTrader5
        return True
    except ImportError:
        return False


def install_mt5():
    """Install MetaTrader5 package."""
    import subprocess
    print("  Installing MetaTrader5...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "MetaTrader5"])
    print("  ✅ MetaTrader5 installed")


def connect_mt5() -> bool:
    """Initialize MT5 connection."""
    import MetaTrader5 as mt5

    if not mt5.initialize():
        print(f"  ❌ MT5 initialize failed: {mt5.last_error()}")
        return False

    info = mt5.account_info()
    if info is None:
        print("  ❌ No account info — is MT5 logged in?")
        mt5.shutdown()
        return False

    print(f"  ✅ Connected to MT5")
    print(f"     Server:    {info.server}")
    print(f"     Account:   {info.login}")
    print(f"     Balance:   {info.balance} {info.currency}")
    print(f"     Leverage:  1:{info.leverage}")
    print(f"     Trade mode: {info.trade_mode}")

    # Check if demo
    if info.trade_mode != 0:  # 0 = demo
        print(f"  ⚠️  WARNING: Account is NOT demo (trade_mode={info.trade_mode})")
        print(f"     This script is for paper trading only!")
    else:
        print(f"  ✅ Demo account confirmed")

    return True


def check_symbol_specs(symbols: list[str]) -> dict:
    """Check symbol specifications."""
    import MetaTrader5 as mt5

    specs = {}
    for sym in symbols:
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"  ❌ {sym}: not found")
            specs[sym] = {"status": "not_found"}
            continue

        specs[sym] = {
            "status": "ok",
            "point": info.point,
            "digits": info.digits,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "spread": info.spread,
            "spread_float": info.spread_float,
            "trade_mode": info.trade_mode,
            "margin_initial": info.margin_initial,
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
        }

        spread_bps = (info.spread * info.point) / (info.ask if info.ask > 0 else 1) * 10000
        print(f"  ✅ {sym}: digits={info.digits}, vol_min={info.volume_min}, "
              f"spread={info.spread} pts ({spread_bps:.1f} bps)")

    return specs


def measure_spread(symbols: list[str], duration_seconds: int = 60, interval: float = 1.0) -> dict:
    """Measure real-time spreads for specified duration."""
    import MetaTrader5 as mt5

    print(f"\n  Measuring spreads for {duration_seconds}s (interval={interval}s)...")

    measurements = {sym: [] for sym in symbols}
    start = time.time()
    count = 0

    while time.time() - start < duration_seconds:
        for sym in symbols:
            tick = mt5.symbol_info_tick(sym)
            if tick is None:
                continue

            spread_raw = tick.ask - tick.bid
            mid = (tick.ask + tick.bid) / 2
            spread_bps = (spread_raw / mid) * 10000 if mid > 0 else 0

            measurements[sym].append({
                "timestamp": datetime.now(UTC).isoformat(),
                "bid": tick.bid,
                "ask": tick.ask,
                "spread_raw": spread_raw,
                "spread_bps": spread_bps,
            })

        count += 1
        time.sleep(interval)

    # Compute stats
    stats = {}
    for sym in symbols:
        if not measurements[sym]:
            stats[sym] = {"status": "no_data"}
            continue

        spreads_bps = [m["spread_bps"] for m in measurements[sym]]
        stats[sym] = {
            "n_samples": len(spreads_bps),
            "mean_bps": round(sum(spreads_bps) / len(spreads_bps), 2),
            "median_bps": round(sorted(spreads_bps)[len(spreads_bps) // 2], 2),
            "p90_bps": round(sorted(spreads_bps)[int(len(spreads_bps) * 0.9)], 2),
            "max_bps": round(max(spreads_bps), 2),
            "min_bps": round(min(spreads_bps), 2),
        }
        print(f"  {sym}: mean={stats[sym]['mean_bps']:.1f} bps, "
              f"median={stats[sym]['median_bps']:.1f} bps, "
              f"p90={stats[sym]['p90_bps']:.1f} bps")

    # Save raw measurements
    SPREAD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SPREAD_LOG, "a") as f:
        for sym in symbols:
            for m in measurements[sym]:
                f.write(json.dumps({"symbol": sym, **m}) + "\n")
    print(f"\n  Raw data saved: {SPREAD_LOG}")

    return stats


def check_telegram() -> dict:
    """Check Telegram bot configuration."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return {"status": "not_configured", "detail": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"}

    # Try sending test message
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": "🧪 MT5 Paper Trading Setup Test"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result.get("ok"):
            return {"status": "ok", "detail": "Test message sent"}
        else:
            return {"status": "error", "detail": str(result)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def main():
    parser = argparse.ArgumentParser(description="MT5 Paper Trading Setup")
    parser.add_argument("--check-only", action="store_true", help="Only check, don't measure")
    parser.add_argument("--measure-spread", action="store_true", help="Measure spreads")
    parser.add_argument("--duration", type=int, default=60, help="Spread measurement duration (seconds)")
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS, help="Symbols to check")
    args = parser.parse_args()

    print("=" * 60)
    print("  MT5 PAPER TRADING SETUP")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    status = {
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {},
    }

    # 1. Check MT5 installed
    print("\n[1/5] Checking MetaTrader5 package...")
    if check_mt5_installed():
        print("  ✅ MetaTrader5 installed")
        status["checks"]["mt5_installed"] = True
    else:
        print("  ❌ MetaTrader5 not installed")
        if not args.check_only:
            install_mt5()
            status["checks"]["mt5_installed"] = True
        else:
            status["checks"]["mt5_installed"] = False

    # 2. Connect to MT5
    print("\n[2/5] Connecting to MT5...")
    try:
        if connect_mt5():
            status["checks"]["mt5_connected"] = True
        else:
            status["checks"]["mt5_connected"] = False
            if args.check_only:
                _save_status(status)
                return
    except Exception as e:
        print(f"  ❌ Connection error: {e}")
        status["checks"]["mt5_connected"] = False
        _save_status(status)
        return

    # 3. Check symbol specs
    print("\n[3/5] Checking symbol specifications...")
    try:
        specs = check_symbol_specs(args.symbols)
        status["checks"]["symbols"] = specs
    except Exception as e:
        print(f"  ❌ Symbol check error: {e}")

    # 4. Check Telegram
    print("\n[4/5] Checking Telegram alerts...")
    tg = check_telegram()
    status["checks"]["telegram"] = tg
    print(f"  {'✅' if tg['status'] == 'ok' else '⚠️'} Telegram: {tg['detail']}")

    # 5. Measure spreads
    if args.measure_spread and not args.check_only:
        print("\n[5/5] Measuring spreads...")
        spread_stats = measure_spread(args.symbols, args.duration)
        status["checks"]["spread_measurement"] = spread_stats
    else:
        print("\n[5/5] Skipping spread measurement (use --measure-spread)")

    # Save status
    _save_status(status)

    # Shutdown MT5
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass

    # Summary
    print(f"\n{'='*60}")
    print("  SETUP STATUS")
    print(f"{'='*60}")
    checks = status["checks"]
    mt5_ok = checks.get("mt5_connected", False)
    tg_ok = checks.get("telegram", {}).get("status") == "ok"
    syms_ok = all(v.get("status") == "ok" for v in checks.get("symbols", {}).values() if isinstance(v, dict))

    print(f"  MT5 Connection:   {'✅' if mt5_ok else '❌'}")
    print(f"  Symbol Specs:     {'✅' if syms_ok else '⚠️'}")
    print(f"  Telegram Alerts:  {'✅' if tg_ok else '⚠️'}")

    if mt5_ok and syms_ok:
        print(f"\n  🎯 READY for paper trading!")
        print(f"  Next: python scripts/paper_trade_preflight_v2.py")
    else:
        print(f"\n  ⚠️  Fix issues above before proceeding")


def _save_status(status: dict):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        json.dump(status, f, indent=2, default=str)
    print(f"\n  Status saved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
