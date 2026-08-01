"""
Paper Trade - EURUSD D1 RSI + BB
Pepperstone Razor Demo

Usage:
    python graxia/packages/quant_os/paper_trade_rsi_bb.py

Requires:
    MT5 terminal running
    Pepperstone Razor Demo account
    Connected via mt5.login()
"""

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, UTC
from pathlib import Path
import json

# === CONFIGURATION ===
LOGIN = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER = os.getenv("MT5_SERVER", "Pepperstone-Demo")
SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_D1

# Strategy parameters
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
BB_PERIOD = 20
BB_STD = 2.0

# Risk management
RISK_PER_TRADE = 0.01  # 1%
SL_ATR_MULT = 1.5
TP_ATR_MULT = 2.0

# Logging
LOG_DIR = Path("graxia/packages/quant_os/data/paper_trades")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def compute_rsi(closes, period=14):
    delta = np.diff(closes, prepend=closes[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).rolling(period).mean().values
    avg_loss = pd.Series(loss).rolling(period).mean().values
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - 100 / (1 + rs)


def compute_bb(closes, period=20, std_mult=2.0):
    sma = pd.Series(closes).rolling(period).mean().values
    std = pd.Series(closes).rolling(period).std().values
    return sma, sma - std_mult * std, sma + std_mult * std


def compute_atr(highs, lows, closes, period=14):
    tr = np.maximum(highs - lows, np.maximum(
        np.abs(highs - np.roll(closes, 1)),
        np.abs(lows - np.roll(closes, 1))
    ))
    tr[0] = highs[0] - lows[0]
    return pd.Series(tr).rolling(period).mean().values


def generate_signal(closes, highs, lows):
    rsi = compute_rsi(closes, RSI_PERIOD)
    sma, lower, upper = compute_bb(closes, BB_PERIOD, BB_STD)
    atr = compute_atr(highs, lows, closes)

    current_rsi = rsi[-1]
    current_price = closes[-1]
    current_lower = lower[-1]
    current_upper = upper[-1]
    current_atr = atr[-1]

    signal = None
    reason = ""

    # RSI signal
    if current_rsi < RSI_OVERSOLD:
        signal = "BUY"
        reason = "RSI %.1f < %.1f" % (current_rsi, RSI_OVERSOLD)
    elif current_rsi > RSI_OVERBOUGHT:
        signal = "SELL"
        reason = "RSI %.1f > %.1f" % (current_rsi, RSI_OVERBOUGHT)

    # BB confirmation
    if signal == "BUY" and current_price < current_lower:
        reason += " + below BB lower"
    elif signal == "SELL" and current_price > current_upper:
        reason += " + above BB upper"
    else:
        signal = None  # No BB confirmation

    sl_distance = current_atr * SL_ATR_MULT
    tp_distance = current_atr * TP_ATR_MULT

    return signal, reason, sl_distance, tp_distance, current_rsi


def log_trade(trade_data):
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    log_file = LOG_DIR / "trades_%s.jsonl" % today
    with open(log_file, "a") as f:
        f.write(json.dumps(trade_data) + "\n")


def run_paper_trade():
    print("=== PAPER TRADE - EURUSD D1 RSI + BB ===")
    print("Broker: Pepperstone Razor Demo")
    print("Strategy: RSI(14) + BB(20,2)")
    print()

    # Connect to MT5
    if not mt5.initialize():
        print("MT5 initialize failed:", mt5.last_error())
        return

    if not mt5.login(LOGIN, PASSWORD, SERVER):
        print("Login failed:", mt5.last_error())
        mt5.shutdown()
        return

    account = mt5.account_info()
    print("Connected! Account: %d, Balance: %.2f %s" % (
        account.login, account.balance, account.currency))

    # Get historical data for indicators
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 100)
    if rates is None or len(rates) < 50:
        print("Insufficient data")
        mt5.shutdown()
        return

    closes = rates["close"].astype(float)
    highs = rates["high"].astype(float)
    lows = rates["low"].astype(float)

    # Generate signal
    signal, reason, sl_dist, tp_dist, rsi_val = generate_signal(closes, highs, lows)

    print("Current RSI: %.1f" % rsi_val)
    print("Signal: %s" % (signal or "NONE"))
    if signal:
        print("Reason: %s" % reason)
        print("SL distance: %.5f" % sl_dist)
        print("TP distance: %.5f" % tp_dist)

        # Log the signal
        log_trade({
            "timestamp": datetime.now(UTC).isoformat(),
            "action": "SIGNAL",
            "signal": signal,
            "reason": reason,
            "rsi": rsi_val,
            "sl_distance": sl_dist,
            "tp_distance": tp_dist,
            "price": float(closes[-1]),
        })
        print("Signal logged to %s" % LOG_DIR)

    mt5.shutdown()
    print("\nDisconnected from MT5")


if __name__ == "__main__":
    run_paper_trade()
