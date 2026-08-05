"""
Live Paper Trade — Donchian(25) + Vol Filter > 1.0 on EURUSD D1
Connects to Pepperstone MT5, calculates signals, tracks performance.
Run daily at/after D1 close (5pm ET / 10pm GMT).

Usage:
  python live_paper_trade.py              # Check signals + log
  python live_paper_trade.py --status     # Show current position
  python live_paper_trade.py --history    # Show trade history
  python live_paper_trade.py --init       # Initialize (first run)
"""
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import json, sys, os
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ─────────────────────────────────────────────────────
MT5_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
LOGIN = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER = os.getenv("MT5_SERVER", "Pepperstone-Demo")

SYMBOL = "EURUSD"
PERIOD = 25        # Donchian lookback
VOL_THRESH = 1.0   # Vol filter threshold (× median ATR ratio)
LOT_SIZE = 0.01    # Micro lot for paper trading
RISK_PCT = 1.0     # Risk per trade (1% of equity)

BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
TRADE_LOG = BASE / "reports" / "live_paper_trades.json"
SIGNAL_STATE = BASE / "reports" / "signal_state.json"

# ─── MT5 Connection ─────────────────────────────────────────────
def connect_mt5():
    if not mt5.initialize(path=MT5_PATH, login=LOGIN, password=PASSWORD, server=SERVER):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    info = mt5.account_info()
    print(f"[MT5] Connected: Balance=${info.balance:.2f}, Leverage=1:{info.leverage}")
    return info

# ─── Signal Calculation ─────────────────────────────────────────
def get_eurusd_data(n_bars=300):
    """Get EURUSD D1 data from MT5."""
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_D1, 0, n_bars)
    if rates is None or len(rates) < PERIOD + 50:
        raise RuntimeError(f"Insufficient data: {len(rates) if rates else 0} bars")
    
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df

def calculate_atr(df, period=14):
    """Calculate ATR."""
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(closes)
    atr = np.zeros(n)
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        atr[i] = (atr[i-1] * (period-1) + tr) / period if i >= period else tr
    return atr

def calculate_signal(df):
    """
    Calculate Donchian(25) + Vol filter signal.
    Returns: (signal, reason, metrics)
    signal: 1 (long), -1 (short), 0 (flat)
    """
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(closes)
    
    # ATR for vol filter
    atr = calculate_atr(df)
    atr_ratio = np.where(closes > 0, atr / closes, 0)
    med_ratio = np.nanmedian(atr_ratio[-200:])
    
    # Current ATR ratio
    curr_vol = atr_ratio[-1]
    vol_ok = curr_vol > med_ratio * VOL_THRESH
    
    # Donchian signals
    hh = np.max(highs[-(PERIOD+1):-1])  # Highest high of last PERIOD bars (excl current)
    ll = np.min(lows[-(PERIOD+1):-1])   # Lowest low of last PERIOD bars (excl current)
    
    prev_close = closes[-2]
    curr_close = closes[-1]
    
    # Signal logic
    if curr_close > hh:
        sig = 1
        reason = f"BREAKOUT LONG: {curr_close:.5f} > HH({PERIOD})={hh:.5f}"
    elif curr_close < ll:
        sig = -1
        reason = f"BREAKOUT SHORT: {curr_close:.5f} < LL({PERIOD})={ll:.5f}"
    else:
        sig = 0
        reason = f"NO SIGNAL: {curr_close:.5f} in range [{ll:.5f}, {hh:.5f}]"
    
    # Vol filter
    if not vol_ok and sig != 0:
        sig = 0
        reason += f" [BLOCKED by vol filter: ATR ratio {curr_vol:.4f} < {med_ratio*VOL_THRESH:.4f}]"
    
    # Also check previous bar for signal (for D1, we act on yesterday's close)
    prev_hh = np.max(highs[-(PERIOD+2):-2])
    prev_ll = np.min(lows[-(PERIOD+2):-2])
    
    prev_sig = 0
    if closes[-2] > prev_hh:
        prev_sig = 1
    elif closes[-2] < prev_ll:
        prev_sig = -1
    
    metrics = {
        "atr": float(atr[-1]),
        "atr_ratio": float(curr_vol),
        "median_vol": float(med_ratio),
        "vol_ok": vol_ok,
        "highest_high": float(hh),
        "lowest_low": float(ll),
        "curr_close": float(curr_close),
        "prev_close": float(prev_close),
        "signal": sig,
        "prev_signal": prev_sig,
    }
    
    return sig, reason, metrics

# ─── Position Sizing ────────────────────────────────────────────
def calculate_position_size(equity, atr, stop_multiplier=1.5):
    """Calculate position size based on risk and ATR stop."""
    stop_distance = atr * stop_multiplier
    # EURUSD: 1 pip = 0.0001, 1 standard lot = $10/pip
    # For 0.01 lot: $0.10/pip
    pip_value = LOT_SIZE * 10  # $ per pip for the lot size
    stop_pips = stop_distance / 0.0001
    
    risk_amount = equity * RISK_PCT / 100
    position_value = risk_amount / (stop_pips * 0.0001) if stop_pips > 0 else 0
    
    # Cap at max lots
    lots = min(LOT_SIZE, position_value) if position_value > 0 else LOT_SIZE
    return round(lots, 2)

# ─── Trade Logging ──────────────────────────────────────────────
def load_trades():
    if TRADE_LOG.exists():
        with open(TRADE_LOG) as f:
            return json.load(f)
    return {"trades": [], "equity_curve": [], "stats": {}}

def save_trades(data):
    with open(TRADE_LOG, "w") as f:
        json.dump(data, f, indent=2, default=str)

def load_state():
    if SIGNAL_STATE.exists():
        with open(SIGNAL_STATE) as f:
            return json.load(f)
    return {"current_signal": 0, "entry_date": None, "entry_price": None, "lots": None}

def save_state(state):
    with open(SIGNAL_STATE, "w") as f:
        json.dump(state, f, indent=2, default=str)

# ─── Main Logic ─────────────────────────────────────────────────
def check_signals():
    """Main signal check — run once per day at/after D1 close."""
    print("=" * 60)
    print("  LIVE PAPER TRADE — Donchian(25) + Vol Filter")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Connect
    acct = connect_mt5()
    
    # Get data
    df = get_eurusd_data(300)
    last_date = df["time"].iloc[-1].date()
    print(f"\n[DATA] {len(df)} bars, last: {last_date}")
    
    # Calculate signal
    sig, reason, metrics = calculate_signal(df)
    print(f"\n[SIGNAL] {reason}")
    print(f"  ATR ratio: {metrics['atr_ratio']:.4f} (threshold: {metrics['median_vol']*VOL_THRESH:.4f})")
    print(f"  Vol OK: {metrics['vol_ok']}")
    print(f"  Current: {metrics['curr_close']:.5f}")
    print(f"  Range: [{metrics['lowest_low']:.5f}, {metrics['highest_high']:.5f}]")
    
    # Load state
    state = load_state()
    current_signal = state.get("current_signal", 0)
    
    # Check for signal change
    if sig != current_signal:
        print(f"\n*** SIGNAL CHANGE: {current_signal} → {sig} ***")
        
        # Close existing position if any
        if current_signal != 0:
            # Calculate P&L for the closed trade
            entry_px = state.get("entry_price", 0)
            exit_px = metrics["curr_close"]
            lots = state.get("lots", LOT_SIZE)
            
            if current_signal == 1:  # Long
                pnl_pips = (exit_px - entry_px) / 0.0001
            else:  # Short
                pnl_pips = (entry_px - exit_px) / 0.0001
            
            # Deduct spread cost (3.4 bps)
            spread_cost = entry_px * 3.4 / 10000 * lots * 100000
            pnl_pips -= spread_cost / (lots * 100000 * 0.0001)
            
            pnl_usd = pnl_pips * lots * 10
            
            trade = {
                "entry_date": state.get("entry_date"),
                "exit_date": str(last_date),
                "direction": "LONG" if current_signal == 1 else "SHORT",
                "entry_price": entry_px,
                "exit_price": exit_px,
                "lots": lots,
                "pnl_pips": round(pnl_pips, 2),
                "pnl_usd": round(pnl_usd, 2),
                "signal_reason": reason,
            }
            
            data = load_trades()
            data["trades"].append(trade)
            
            # Update stats
            trades = data["trades"]
            total_pnl = sum(t.get("pnl_usd", 0) for t in trades)
            wins = sum(1 for t in trades if t.get("pnl_usd", 0) > 0)
            data["stats"] = {
                "total_trades": len(trades),
                "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
                "total_pnl_usd": round(total_pnl, 2),
                "avg_pnl_usd": round(total_pnl / len(trades), 2) if trades else 0,
            }
            
            save_trades(data)
            print(f"\n[TRADE CLOSED] {trade['direction']} @ {entry_px:.5f} → {exit_px:.5f}")
            print(f"  P&L: {pnl_pips:.1f} pips = ${pnl_usd:.2f}")
        
        # Open new position if signal != 0
        if sig != 0:
            lots = calculate_position_size(acct.balance, metrics["atr"])
            state = {
                "current_signal": sig,
                "entry_date": str(last_date),
                "entry_price": metrics["curr_close"],
                "lots": lots,
                "direction": "LONG" if sig == 1 else "SHORT",
            }
            print(f"\n[TRADE OPENED] {'LONG' if sig == 1 else 'SHORT'} @ {metrics['curr_close']:.5f}")
            print(f"  Lots: {lots}, Risk: {RISK_PCT}%")
        else:
            state = {"current_signal": 0, "entry_date": None, "entry_price": None, "lots": None}
            print(f"\n[FLAT] No position")
    else:
        print(f"\n[HOLD] Signal unchanged: {current_signal}")
        if current_signal != 0:
            entry_px = state.get("entry_price", 0)
            curr_px = metrics["curr_close"]
            if current_signal == 1:
                unrealized = (curr_px - entry_px) / 0.0001
            else:
                unrealized = (entry_px - curr_px) / 0.0001
            print(f"  Entry: {entry_px:.5f}, Current: {curr_px:.5f}")
            print(f"  Unrealized: {unrealized:.1f} pips")
    
    save_state(state)
    
    # Log equity curve
    data = load_trades()
    data["equity_curve"].append({
        "date": str(last_date),
        "balance": acct.balance,
        "equity": acct.equity,
        "signal": sig,
        "position_signal": state.get("current_signal", 0),
    })
    save_trades(data)
    
    print(f"\n[DONE] Next check: tomorrow at/after D1 close")
    mt5.shutdown()
    return sig

def show_status():
    """Show current position and stats."""
    state = load_state()
    data = load_trades()
    
    print("=" * 60)
    print("  PAPER TRADE STATUS")
    print("=" * 60)
    
    if state.get("current_signal", 0) != 0:
        print(f"\n  Position: {state.get('direction', 'NONE')}")
        print(f"  Entry: {state.get('entry_price', 0):.5f}")
        print(f"  Date: {state.get('entry_date', 'N/A')}")
        print(f"  Lots: {state.get('lots', 0)}")
    else:
        print(f"\n  Position: FLAT")
    
    stats = data.get("stats", {})
    if stats:
        print(f"\n  Stats:")
        print(f"    Total trades: {stats.get('total_trades', 0)}")
        print(f"    Win rate: {stats.get('win_rate', 0)}%")
        print(f"    Total P&L: ${stats.get('total_pnl_usd', 0):.2f}")
        print(f"    Avg P&L: ${stats.get('avg_pnl_usd', 0):.2f}")
    
    # Show last 5 trades
    trades = data.get("trades", [])[-5:]
    if trades:
        print(f"\n  Last 5 trades:")
        for t in trades:
            print(f"    {t['entry_date']} {t['direction']:5s} @ {t['entry_price']:.5f} → {t['exit_price']:.5f} = {t['pnl_pips']:+.1f} pips (${t['pnl_usd']:+.2f})")
    
    # MT5 balance
    acct = connect_mt5()
    print(f"\n  MT5 Balance: ${acct.balance:.2f}")
    mt5.shutdown()

def show_history():
    """Show all trades."""
    data = load_trades()
    trades = data.get("trades", [])
    
    print("=" * 60)
    print(f"  TRADE HISTORY ({len(trades)} trades)")
    print("=" * 60)
    
    for t in trades:
        print(f"  {t['entry_date']} {t['direction']:5s} @ {t['entry_price']:.5f} → {t['exit_price']:.5f} = {t['pnl_pips']:+.1f} pips (${t['pnl_usd']:+.2f})")
    
    if trades:
        total_pnl = sum(t.get("pnl_usd", 0) for t in trades)
        wins = sum(1 for t in trades if t.get("pnl_usd", 0) > 0)
        print(f"\n  Total: {len(trades)} trades, WR={wins/len(trades)*100:.1f}%, P&L=${total_pnl:.2f}")

if __name__ == "__main__":
    if "--status" in sys.argv:
        show_status()
    elif "--history" in sys.argv:
        show_history()
    elif "--init" in sys.argv:
        # Initialize trade log
        if not TRADE_LOG.exists():
            save_trades({"trades": [], "equity_curve": [], "stats": {}})
            print("Trade log initialized")
        save_state({"current_signal": 0, "entry_date": None, "entry_price": None, "lots": None})
        print("Signal state initialized")
    else:
        check_signals()
