#!/usr/bin/env python3
"""
XAUUSD TSM Paper Trade — Single-Asset, lb=60, Verified Costs Only
=================================================================

60-day paper trading requirement per CONSTITUTION Golden Rule #3.

Strategy: sign(lookback_return) * vol_target / realized_vol
Lookback: 60 days (verified from backtest: Sharpe=2.0, 33 trades in 2.6 years)
Asset: XAUUSD only (FROM_TICKS verified, 0.65 bps RT typical, 72 bps stress)
Rebalance: Weekly (Friday close)

Modes:
  --dry-run   Compute signals, log to CSV, no MT5 orders
  --live      Connect to MT5 demo, place real orders
  --status    Show paper trading progress (days elapsed, trades, P&L)

Usage:
    python scripts/tsm_paper_trade_xauusd.py --dry-run
    python scripts/tsm_paper_trade_xauusd.py --live
    python scripts/tsm_paper_trade_xauusd.py --status
"""

# Load .env before anything else
try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from core.returns import compute_returns  # noqa: E402

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

ASSET = "XAUUSD"
MT5_SYMBOL = "XAUUSD"
LOOKBACK = 60  # days — verified from backtest
TARGET_VOL = 0.10  # 10% annualized
RVOL_WINDOW = 20  # realized vol lookback
REBALANCE_FREQ = "W-FRI"  # weekly Friday

# Verified costs from config/cost_calibration.json (FROM_TICKS status)
COST_BPS_TYPICAL = 0.65  # round-trip, median measured
COST_BPS_STRESS = 72.0  # round-trip, worst-case observed
CONTRACT_SIZE = 100  # 1 lot = 100 troy oz
MIN_LOT = 0.01
MAGIC_NUMBER = 202607  # unique magic for XAUUSD paper trade

# Paper trading requirements (CONSTITUTION Golden Rule #3)
PAPER_TRADE_DAYS_MIN = 60
PAPER_TRADE_TRADES_MIN = 100

# Paths
PARQUET_PATH = BASE / "artifacts" / "portfolio" / "d1_multi_asset.parquet"
STATE_DIR = BASE / "artifacts" / "paper_trade_xauusd"
STATE_PATH = STATE_DIR / "state.json"
CSV_LOG_PATH = STATE_DIR / "trade_log.csv"
DAILY_LOG_PATH = STATE_DIR / "daily_pnl.csv"
PROGRESS_PATH = STATE_DIR / "progress.json"

CSV_HEADERS = ["timestamp", "action", "signal", "weight", "lots", "price", "cost_bps", "pnl", "equity", "notes"]

DAILY_HEADERS = [
    "date",
    "open_equity",
    "close_equity",
    "daily_pnl",
    "cumulative_pnl",
    "drawdown",
    "signal",
    "position",
    "trades_today",
]


# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════


def log(msg: str):
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe = msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    try:
        print(f"[{ts}] {safe}")
    except UnicodeEncodeError:
        print(f"[{ts}] {safe.encode('ascii', errors='replace').decode('ascii')}")


def tg(msg: str):
    """Send Telegram notification if configured."""
    try:
        from quant_os.core.telegram_notify import TelegramNotifier

        notifier = TelegramNotifier()
        notifier.send(msg)
    except Exception:
        pass
    log(msg)


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════


def load_xauusd_data() -> pd.Series:
    """Load XAUUSD close prices from parquet."""
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(f"Portfolio data not found: {PARQUET_PATH}")
    df = pd.read_parquet(PARQUET_PATH)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    col = f"{ASSET}_close"
    if col not in df.columns:
        raise ValueError(f"Column {col} not found in parquet data")
    return df[col].dropna()


# ═══════════════════════════════════════════════════════════════
# SIGNAL COMPUTATION
# ═══════════════════════════════════════════════════════════════


def compute_signal(close: pd.Series, lookback: int) -> pd.Series:
    """TSM signal: sign of lookback-period return."""
    ret = compute_returns(close, lookback)
    return np.sign(ret)


def compute_weight(close: pd.Series, lookback: int, target_vol: float) -> pd.Series:
    """Vol-targeted position weight: signal * target_vol / realized_vol."""
    signal = compute_signal(close, lookback)
    daily_ret = compute_returns(close, 1)
    rvol = daily_ret.rolling(RVOL_WINDOW).std() * np.sqrt(252)
    rvol = rvol.replace(0, np.nan)
    weight = signal * target_vol / rvol
    return weight.clip(-1, 1)


# ═══════════════════════════════════════════════════════════════
# STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════════


def init_dirs():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    """Load paper trading state."""
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "start_date": datetime.now(UTC).isoformat(),
        "initial_equity": 100_000.0,
        "current_equity": 100_000.0,
        "position_lots": 0.0,
        "position_direction": "FLAT",  # LONG, SHORT, FLAT
        "entry_price": 0.0,
        "total_trades": 0,
        "total_pnl": 0.0,
        "high_water_mark": 100_000.0,
        "max_drawdown": 0.0,
        "daily_pnl_history": [],
    }


def save_state(state: dict):
    init_dirs()
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def init_csv():
    init_dirs()
    if not CSV_LOG_PATH.exists():
        with open(CSV_LOG_PATH, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADERS)


def log_trade(row: dict):
    init_csv()
    with open(CSV_LOG_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=CSV_HEADERS).writerow(row)


def init_daily_csv():
    init_dirs()
    if not DAILY_LOG_PATH.exists():
        with open(DAILY_LOG_PATH, "w", newline="") as f:
            csv.writer(f).writerow(DAILY_HEADERS)


def log_daily(row: dict):
    init_daily_csv()
    with open(DAILY_LOG_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=DAILY_HEADERS).writerow(row)


# ═══════════════════════════════════════════════════════════════
# MT5 CONNECTION (for --live mode)
# ═══════════════════════════════════════════════════════════════

_mt5_initialized = False


def ensure_mt5():
    global _mt5_initialized
    import MetaTrader5 as mt5  # noqa: N813

    if not _mt5_initialized:
        login = int(os.getenv("MT5_LOGIN", "0"))
        password = os.getenv("MT5_PASSWORD", "")
        server = os.getenv("MT5_SERVER", "Pepperstone-Demo")
        initialized = mt5.initialize(login=login, password=password, server=server)
        if not initialized:
            raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("Cannot read MT5 account info")
        server_lower = info.server.lower()
        if "demo" not in server_lower and "practice" not in server_lower:
            raise RuntimeError(f"LIVE ACCOUNT DETECTED: {info.server}")
        _mt5_initialized = True
        log(f"MT5 connected: {info.server} | Equity: ${info.equity:,.2f}")
    return mt5


def get_mt5_price(mt5, symbol: str) -> float | None:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return (tick.bid + tick.ask) / 2.0


def get_mt5_equity(mt5) -> float:
    info = mt5.account_info()
    if info is None:
        raise RuntimeError("Cannot read MT5 account info")
    return info.equity


def place_mt5_order(mt5, symbol: str, lots: float, comment: str = "XAU-PAPER") -> dict | None:
    import MetaTrader5 as mt5_mod  # noqa: N813

    side = mt5_mod.ORDER_TYPE_BUY if lots > 0 else mt5_mod.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(symbol).ask if lots > 0 else mt5.symbol_info_tick(symbol).bid
    request = {
        "action": mt5_mod.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": abs(lots),
        "type": side,
        "price": price,
        "deviation": 10,
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5_mod.ORDER_TIME_GTC,
        "type_filling": mt5_mod.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None:
        return None
    if result.retcode != mt5_mod.TRADE_RETCODE_DONE:
        log(f"❌ Order failed: {result.comment}")
        return None
    return {"ticket": result.order, "price": result.price, "lots": lots}


def close_mt5_positions(mt5, symbol: str):
    import MetaTrader5 as mt5_mod  # noqa: N813

    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    for pos in positions:
        side = mt5_mod.ORDER_TYPE_SELL if pos.type == 0 else mt5_mod.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if pos.type == 0 else mt5.symbol_info_tick(symbol).ask
        request = {
            "action": mt5_mod.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": side,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": MAGIC_NUMBER,
            "comment": "XAU-PAPER-close",
            "type_time": mt5_mod.ORDER_TIME_GTC,
            "type_filling": mt5_mod.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result and result.retcode == mt5_mod.TRADE_RETCODE_DONE:
            log(f"✅ Closed ticket={pos.ticket} vol={pos.volume}")
        else:
            log(f"❌ Close failed ticket={pos.ticket}")


# ═══════════════════════════════════════════════════════════════
# PAPER TRADING ENGINE
# ═══════════════════════════════════════════════════════════════


def run_paper_trade(live: bool = False, force: bool = False):
    """Main paper trading routine."""
    log("=" * 60)
    log(f"XAUUSD TSM Paper Trade — {'LIVE' if live else 'DRY-RUN'}")
    log(f"Strategy: lb={LOOKBACK}, vol_target={TARGET_VOL:.0%}")
    log(f"Costs: {COST_BPS_TYPICAL} bps typical, {COST_BPS_STRESS} bps stress")
    log("=" * 60)

    # Day-of-week check
    now = datetime.now(UTC)
    if not force and now.weekday() != 4:
        log(f"Today is {now.strftime('%A')} — rebalance only on Friday. Use --force to override.")
        return

    init_dirs()
    state = load_state()

    # Load data
    close = load_xauusd_data()
    log(f"Data: {len(close)} bars, {close.index.min().date()} to {close.index.max().date()}")

    # Compute signal and weight
    signal = compute_signal(close, LOOKBACK)
    weight = compute_weight(close, LOOKBACK, TARGET_VOL)

    # Get latest values
    latest_signal = float(signal.iloc[-1])
    latest_weight = float(weight.iloc[-1])
    latest_price = float(close.iloc[-1])
    latest_ret = float(compute_returns(close, 1).iloc[-1])

    # Determine position direction
    if latest_weight > 0.01:
        target_direction = "LONG"
        target_lots = abs(latest_weight) * state["initial_equity"] / (latest_price * CONTRACT_SIZE)
        target_lots = round(max(target_lots, 0) * 100) / 100
    elif latest_weight < -0.01:
        target_direction = "SHORT"
        target_lots = abs(latest_weight) * state["initial_equity"] / (latest_price * CONTRACT_SIZE)
        target_lots = round(max(target_lots, 0) * 100) / 100
    else:
        target_direction = "FLAT"
        target_lots = 0.0

    log("\n--- Signal & Position ---")
    log(f"  Date: {close.index[-1].date()}")
    log(f"  Price: ${latest_price:,.2f}")
    log(f"  Signal: {latest_signal:+.0f}")
    log(f"  Weight: {latest_weight:+.4f}")
    log(f"  Target: {target_direction} {target_lots:.2f} lots")

    # Check if position change is needed
    current_direction = state["position_direction"]
    current_lots = state["position_lots"]

    position_changed = (target_direction != current_direction) or (abs(target_lots - current_lots) > 0.01)

    if not position_changed:
        log("  No position change needed")
        # Still log daily P&L
        _log_daily_pnl(state, latest_price, latest_ret, 0)
        return

    # Compute cost
    cost_bps = COST_BPS_TYPICAL  # use typical for logging; stress tested separately
    cost_pct = cost_bps / 10000

    # Estimate P&L from position change
    pnl = 0.0
    if current_lots > 0:
        # Closing existing position
        if current_direction == "LONG":
            pnl += (latest_price - state["entry_price"]) / state["entry_price"] * current_lots * CONTRACT_SIZE
        elif current_direction == "SHORT":
            pnl += (state["entry_price"] - latest_price) / state["entry_price"] * current_lots * CONTRACT_SIZE
        pnl -= cost_pct * current_lots * latest_price * CONTRACT_SIZE

    if target_lots > 0:
        # Opening new position
        pnl -= cost_pct * target_lots * latest_price * CONTRACT_SIZE

    # Update state
    state["total_trades"] += 1
    state["total_pnl"] += pnl
    state["current_equity"] = state["initial_equity"] + state["total_pnl"]
    state["position_direction"] = target_direction
    state["position_lots"] = target_lots
    if target_lots > 0:
        state["entry_price"] = latest_price
    else:
        state["entry_price"] = 0.0

    # Update high water mark and drawdown
    if state["current_equity"] > state["high_water_mark"]:
        state["high_water_mark"] = state["current_equity"]
    dd = (state["current_equity"] - state["high_water_mark"]) / state["high_water_mark"]
    if dd < state["max_drawdown"]:
        state["max_drawdown"] = dd

    # Execute on MT5 if live
    fills = []
    if live:
        mt5 = ensure_mt5()
        # Close existing position if needed
        if current_lots > 0 and target_direction != current_direction:
            close_mt5_positions(mt5, MT5_SYMBOL)
        # Open new position
        if target_lots > 0:
            direction = 1 if target_direction == "LONG" else -1
            result = place_mt5_order(mt5, MT5_SYMBOL, direction * target_lots)
            if result:
                fills.append(result)
                log(f"  ✅ Order filled: {target_direction} {target_lots:.2f} lots @ ${result['price']:,.2f}")
            else:
                log("  ❌ Order failed")
        else:
            log("  ✅ Closed all positions (FLAT)")

    # Log trade
    log_trade(
        {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
            "action": f"{current_direction}->{target_direction}",
            "signal": f"{latest_signal:+.0f}",
            "weight": f"{latest_weight:+.4f}",
            "lots": f"{target_lots:+.2f}",
            "price": f"{latest_price:.2f}",
            "cost_bps": f"{cost_bps:.2f}",
            "pnl": f"{pnl:+.2f}",
            "equity": f"{state['current_equity']:+.2f}",
            "notes": f"trades={state['total_trades']}",
        }
    )

    # Log daily P&L
    _log_daily_pnl(state, latest_price, latest_ret, 1)

    # Save state
    save_state(state)

    # Progress report
    start_date = datetime.fromisoformat(state["start_date"])
    days_elapsed = (datetime.now(UTC) - start_date).days
    days_remaining = max(0, PAPER_TRADE_DAYS_MIN - days_elapsed)
    trades_remaining = max(0, PAPER_TRADE_TRADES_MIN - state["total_trades"])

    log("\n--- Paper Trading Progress ---")
    log(f"  Days: {days_elapsed}/{PAPER_TRADE_DAYS_MIN} ({days_remaining} remaining)")
    log(f"  Trades: {state['total_trades']}/{PAPER_TRADE_TRADES_MIN} ({trades_remaining} remaining)")
    log(f"  Equity: ${state['current_equity']:,.2f} (P&L: ${state['total_pnl']:+,.2f})")
    log(f"  Max DD: {state['max_drawdown']:.2%}")
    log(
        f"  Status: {'COMPLETE' if days_elapsed >= PAPER_TRADE_DAYS_MIN and state['total_trades'] >= PAPER_TRADE_TRADES_MIN else 'IN PROGRESS'}"
    )

    tg(
        f"📊 *XAUUSD Paper Trade*\n"
        f"Action: {current_direction}->{target_direction}\n"
        f"Lots: {target_lots:.2f} @ ${latest_price:,.2f}\n"
        f"Equity: ${state['current_equity']:,.2f}\n"
        f"Progress: {days_elapsed}d / {state['total_trades']} trades"
    )


def _log_daily_pnl(state: dict, price: float, daily_ret: float, trades_today: int):
    """Log daily P&L to CSV."""
    start_date = datetime.fromisoformat(state["start_date"])
    today = datetime.now(UTC).date()
    days_elapsed = (today - start_date.date()).days

    # Estimate daily P&L from position
    pnl_today = 0.0
    if state["position_lots"] > 0:
        if state["position_direction"] == "LONG":
            pnl_today = daily_ret * state["position_lots"] * CONTRACT_SIZE * price
        elif state["position_direction"] == "SHORT":
            pnl_today = -daily_ret * state["position_lots"] * CONTRACT_SIZE * price

    log_daily(
        {
            "date": today.isoformat(),
            "open_equity": f"{state['initial_equity'] + state['total_pnl'] - pnl_today:.2f}",
            "close_equity": f"{state['current_equity']:.2f}",
            "daily_pnl": f"{pnl_today:+.2f}",
            "cumulative_pnl": f"{state['total_pnl']:+.2f}",
            "drawdown": f"{state['max_drawdown']:.4f}",
            "signal": f"{state.get('last_signal', 0):+.0f}",
            "position": state["position_direction"],
            "trades_today": trades_today,
        }
    )


def show_status():
    """Show paper trading progress."""
    state = load_state()
    start_date = datetime.fromisoformat(state["start_date"])
    days_elapsed = (datetime.now(UTC) - start_date).days

    print("\n" + "=" * 60)
    print("XAUUSD TSM Paper Trading Status")
    print("=" * 60)
    print(f"  Start date: {start_date.date()}")
    print(f"  Days elapsed: {days_elapsed}/{PAPER_TRADE_DAYS_MIN}")
    print(f"  Trades: {state['total_trades']}/{PAPER_TRADE_TRADES_MIN}")
    print(f"  Initial equity: ${state['initial_equity']:,.2f}")
    print(f"  Current equity: ${state['current_equity']:,.2f}")
    print(f"  Total P&L: ${state['total_pnl']:+,.2f}")
    print(f"  Max drawdown: {state['max_drawdown']:.2%}")
    print(f"  Position: {state['position_direction']} {state['position_lots']:.2f} lots")
    if state["position_lots"] > 0:
        print(f"  Entry price: ${state['entry_price']:,.2f}")

    # Check completion
    days_ok = days_elapsed >= PAPER_TRADE_DAYS_MIN
    trades_ok = state["total_trades"] >= PAPER_TRADE_TRADES_MIN
    if days_ok and trades_ok:
        print("\n  [OK] PAPER TRADING COMPLETE — ready for live readiness review")
    else:
        reasons = []
        if not days_ok:
            reasons.append(f"{PAPER_TRADE_DAYS_MIN - days_elapsed} more days needed")
        if not trades_ok:
            reasons.append(f"{PAPER_TRADE_TRADES_MIN - state['total_trades']} more trades needed")
        print(f"\n  [IN PROGRESS] — {', '.join(reasons)}")

    print("=" * 60)

    # Show recent trades
    if CSV_LOG_PATH.exists():
        df = pd.read_csv(CSV_LOG_PATH)
        if len(df) > 0:
            print("\nRecent trades (last 5):")
            for _, row in df.tail(5).iterrows():
                print(
                    f"  {row['timestamp']} | {row['action']:>12s} | {str(row['lots']):>6s} lots | P&L: {str(row['pnl']):>10s}"
                )


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="XAUUSD TSM Paper Trade — 60-day requirement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/tsm_paper_trade_xauusd.py --dry-run     # Test without MT5
  python scripts/tsm_paper_trade_xauusd.py --live         # Execute on demo
  python scripts/tsm_paper_trade_xauusd.py --status       # Show progress
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Compute signals, log, no orders")
    group.add_argument("--live", action="store_true", help="Connect to MT5 & execute orders")
    group.add_argument("--status", action="store_true", help="Show paper trading progress")
    parser.add_argument("--force", action="store_true", help="Force rebalance (skip day-of-week check)")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    run_paper_trade(live=args.live, force=args.force)


if __name__ == "__main__":
    main()
