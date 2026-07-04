#!/usr/bin/env python3
"""
GRAXIA-OS Paper Trade Bot v1.0 — Automated Demo Trading
========================================================
Runs 24/7 on local PC: every 15min generates XAUUSD signal,
places trades with B2 stop ($6.30) at 0.01 lot, logs to CSV,
and sends Telegram alerts.

Config: scripts/telegram_config.toml
Usage:  $env:PYTHONIOENCODING='utf-8'; python scripts/paper_trade_bot.py
"""

import argparse
import csv
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# --- GLOBALS ---
SYMBOL = "XAUUSD"
LOT_SIZE = 0.01
B2_STOP_DOLLARS = 6.30
MIN_CONFIDENCE = 0.85
CSV_PATH = BASE / "data" / "paper_trade_log.csv"
SESSION_PATH = BASE / "data" / "paper_trade_session.json"
HEARTBEAT_PATH = BASE / "data" / "heartbeat.txt"
MODEL_PATH = BASE / "artifacts" / "strategy_model" / "model.pkl"
FEATURES_V2_DIR = BASE / "artifacts" / "features_v2"
STATE_PATH = BASE / "data" / "bot_state.json"

HEADERS = [
    "timestamp",
    "direction",
    "entry_price",
    "exit_price",
    "exit_reason",
    "stop_filled_at",
    "intended_stop",
    "slippage",
    "pnl_gross",
    "pnl_net",
    "event_flag",
    "notes",
]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}")


# ============================================================
# TELEGRAM
# ============================================================
def get_notifier():
    from core.telegram_notify import TelegramNotifier

    try:
        return TelegramNotifier()
    except RuntimeError as e:
        log(f"Telegram not configured: {e}")
        return None


NOTIFIER = get_notifier()


def tg(msg: str):
    if NOTIFIER:
        NOTIFIER.send(msg)
    log(msg)


# ============================================================
# MT5 CONNECTION
# ============================================================
_mt5_initialized = False


def ensure_mt5():
    global _mt5_initialized
    import MetaTrader5 as mt5

    if not _mt5_initialized:
        initialized = mt5.initialize()
        if not initialized:
            error = mt5.last_error()
            raise RuntimeError(f"MT5 init failed: {error}")
        _mt5_initialized = True
        log("MT5 initialized")
    return mt5


def get_live_data(mt5, n_bars: int = 100) -> pd.DataFrame | None:
    """Fetch latest XAUUSD M15 bars from MT5."""
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    df = df.rename(
        columns={
            "tick_volume": "volume",
            "real_volume": "real_volume",
        }
    )
    # Add required columns
    df["symbol"] = SYMBOL
    df["freq"] = "15min"
    log(f"Fetched {len(df)} bars from MT5 (latest: {df.index[-1]})")
    return df


def get_open_position(mt5) -> dict | None:
    """Check for any open XAUUSD position."""
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions and len(positions) > 0:
        pos = positions[0]
        return {
            "ticket": pos.ticket,
            "direction": "long" if pos.type == 0 else "short",
            "volume": pos.volume,
            "open_price": pos.price_open,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
            "swap": pos.swap,
            "open_time": datetime.fromtimestamp(pos.time, tz=timezone.utc),
        }
    return None


# ============================================================
# SIGNAL GENERATION
# ============================================================
def load_model():
    """Load pretrained XGBoost model."""
    if not MODEL_PATH.exists():
        log(f"Model not found at {MODEL_PATH}")
        return None
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    log(f"Model loaded from {MODEL_PATH}")
    return model


def load_feature_template() -> tuple[pd.DataFrame, list[str]]:
    """Load historical features to use as feature template."""
    path = FEATURES_V2_DIR / f"features_v2_{SYMBOL}_15min.parquet"
    if not path.exists():
        log(f"Feature template not found: {path}")
        return None, []
    df = pd.read_parquet(path)
    # Get feature columns (exclude targets/idents)
    exclude = {
        "target",
        "target_return",
        "symbol",
        "freq",
        "tb_label",
        "tb_bar_hit",
        "tb_side",
        "tb_ret",
        "tb_k_upper",
        "tb_k_lower",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "tick_count",
    }
    feature_cols = [
        c
        for c in df.columns
        if c not in exclude
        and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)
    ]
    log(f"Feature template: {len(df)} rows, {len(feature_cols)} features")
    return df, feature_cols


def compute_features_live(
    live_df: pd.DataFrame, template_df: pd.DataFrame, feature_cols: list[str]
) -> np.ndarray:
    """
    Compute features on live data using the same logic as the training pipeline.
    For now: align columns, fill NaN, return numpy array.
    """
    # Add synthetic features to match template
    for col in feature_cols:
        if col not in live_df.columns:
            # Try common transformations
            if col.startswith("ret_"):
                period = int(col.split("_")[1].replace("m", ""))
                live_df[col] = live_df["close"].pct_change(period)
            elif col.startswith("ma_"):
                period = int(col.split("_")[1].replace("m", ""))
                live_df[col] = live_df["close"].rolling(period).mean()
            elif col.startswith("ema_"):
                period = int(col.split("_")[1].replace("m", ""))
                live_df[col] = live_df["close"].ewm(span=period).mean()
            elif col == "atr":
                high_low = live_df["high"] - live_df["low"]
                high_close = (live_df["high"] - live_df["close"].shift()).abs()
                low_close = (live_df["low"] - live_df["close"].shift()).abs()
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                live_df[col] = tr.rolling(14).mean()
            elif col == "rsi":
                delta = live_df["close"].diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss.replace(0, np.nan)
                live_df[col] = 100 - (100 / (1 + rs))
            elif col.endswith("_zscore"):
                base = col.replace("_zscore", "")
                period = 20
                if base in live_df.columns:
                    live_df[col] = (
                        live_df[base] - live_df[base].rolling(period).mean()
                    ) / live_df[base].rolling(period).std().replace(0, np.nan)
            else:
                live_df[col] = 0.0

    # Select only the feature columns, fill NaN
    result = live_df[feature_cols].fillna(0).values
    return result[-1:]  # Return only latest bar


# ============================================================
# TRADE EXECUTION
# ============================================================
def place_trade(
    mt5, direction: int, entry_price: float, confidence: float
) -> dict | None:
    """
    Place a market order on MT5 demo.
    direction: 0=SELL, 1=BUY
    """
    order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
    price = (
        mt5.symbol_info_tick(SYMBOL).ask
        if direction == 1
        else mt5.symbol_info_tick(SYMBOL).bid
    )

    # B2 stop: $6.30 in price units at 0.01 lot (1 oz)
    stop_distance_price = B2_STOP_DOLLARS  # $6.30 = 6.30 price points at 0.01 lot
    sl = price - stop_distance_price if direction == 1 else price + stop_distance_price

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": 0.0,
        "deviation": 10,
        "magic": 123456,
        "comment": f"GRAXIA B2 conf={confidence:.2f}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        log(
            f"TRADE OPENED: {'BUY' if direction == 1 else 'SELL'} @ {price:.2f}, SL={sl:.2f}, conf={confidence:.2f}"
        )
        return {
            "ticket": result.order,
            "direction": "long" if direction == 1 else "short",
            "entry": price,
            "sl": sl,
            "confidence": confidence,
        }
    else:
        error = result.comment if result else "no result"
        log(f"TRADE FAILED: {error} (retcode={result.retcode if result else 'N/A'})")
        return None


def close_trade(mt5, ticket: int) -> bool:
    """Close an open position by ticket."""
    position = mt5.positions_get(ticket=ticket)
    if not position or len(position) == 0:
        return False
    pos = position[0]
    order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    price = (
        mt5.symbol_info_tick(SYMBOL).bid
        if pos.type == 0
        else mt5.symbol_info_tick(SYMBOL).ask
    )

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": pos.volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 10,
        "magic": 123456,
        "comment": "GRAXIA close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    success = result and result.retcode == mt5.TRADE_RETCODE_DONE
    if success:
        log(f"TRADE CLOSED: ticket={ticket} @ {price:.2f}")
    return success


# ============================================================
# LOGGING
# ============================================================
def log_trade(
    entry: dict | None = None,
    close_entry: dict | None = None,
    pnl: float = 0.0,
    reason: str = "natural",
    event: str = "none",
):
    """Append to paper_trade_log.csv."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="") as f:
            csv.writer(f).writerow(HEADERS)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if entry and not close_entry:
        # Opening
        row = {
            "timestamp": now,
            "direction": entry["direction"],
            "entry_price": entry["entry"],
            "exit_price": "",
            "exit_reason": "",
            "stop_filled_at": "",
            "intended_stop": str(B2_STOP_DOLLARS),
            "slippage": "0.0",
            "pnl_gross": "",
            "pnl_net": "",
            "event_flag": event,
            "notes": f"Open conf={entry.get('confidence', 0):.2f} ticket={entry.get('ticket', '')}",
        }
    elif close_entry:
        row = {
            "timestamp": now,
            "direction": close_entry.get("direction", ""),
            "entry_price": close_entry.get("entry_price", ""),
            "exit_price": close_entry.get("exit_price", ""),
            "exit_reason": reason,
            "stop_filled_at": close_entry.get("stop_filled_at", ""),
            "intended_stop": str(B2_STOP_DOLLARS),
            "slippage": close_entry.get("slippage", "0.0"),
            "pnl_gross": f"{pnl:.2f}",
            "pnl_net": f"{pnl:.2f}",
            "event_flag": event,
            "notes": close_entry.get("notes", ""),
        }
    else:
        return

    with open(CSV_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writerow(row)
    log(f"Logged to CSV: {row.get('direction','')} {row.get('pnl_gross','')}")


# ============================================================
# MAIN LOOP
# ============================================================
def main_loop(
    model,
    feature_cols: list[str],
    template_df: pd.DataFrame,
    interval_minutes: int = 15,
):
    """Main trading loop — runs every interval_minutes."""
    mt5 = ensure_mt5()
    daily_trades = 0
    daily_pnl = 0.0
    current_date = datetime.now(timezone.utc).date()
    last_heartbeat = 0.0

    log("=== PAPER TRADE BOT STARTED ===")
    log(f"Symbol: {SYMBOL} | Lot: {LOT_SIZE} | Stop: ${B2_STOP_DOLLARS}")
    log(f"Model: {MODEL_PATH.name if MODEL_PATH.exists() else 'not found'}")
    tg(
        f"🚀 *GRAXIA-OS Paper Trade Bot STARTED*\n"
        f"{SYMBOL} M15 | {LOT_SIZE} lot | B2 stop \${B2_STOP_DOLLARS}"
    )
    _send_heartbeat(mt5, daily_trades, daily_pnl, daily_pnl)  # initial

    while True:
        try:
            now = datetime.now(timezone.utc)
            date_today = now.date()

            # Reset daily counters
            if date_today != current_date:
                current_date = date_today
                daily_trades = 0
                daily_pnl = 0.0

            # 1. Get live data
            live_df = get_live_data(mt5, n_bars=200)
            if live_df is None or len(live_df) < 50:
                log("Insufficient live data, waiting...")
                time.sleep(60)
                continue

            # 2. Check open position
            pos = get_open_position(mt5)

            # 3. Heartbeat every 6h
            if time.time() - last_heartbeat > 21600:
                _send_heartbeat(mt5, daily_trades, daily_pnl, daily_pnl)
                last_heartbeat = time.time()

            # 4. If position open → check if stopped out
            if pos:
                current_price = mt5.symbol_info_tick(SYMBOL).bid
                if pos["direction"] == "long":
                    stop_hit = pos["sl"] and current_price <= pos["sl"]
                    pnl = (current_price - pos["open_price"]) * 1  # 0.01 lot = 1 oz
                else:
                    stop_hit = pos["sl"] and current_price >= pos["sl"]
                    pnl = (pos["open_price"] - current_price) * 1
                pnl -= pos.get("swap", 0)

                if stop_hit:
                    log(
                        f"STOP HIT: direction={pos['direction']} entry={pos['open_price']:.2f} sl={pos['sl']:.2f}"
                    )
                    tg(f"❤️ *STOP HIT* | {pos['direction']} | PnL: \${pnl:.2f}")
                    log_trade(
                        close_entry={
                            "direction": pos["direction"],
                            "exit_price": pos["sl"],
                            "stop_filled_at": pos["sl"],
                            "slippage": "0.0",
                            "entry_price": pos["open_price"],
                            "notes": f"B2 stop hit ticket={pos['ticket']}",
                        },
                        pnl=pnl,
                        reason="stop_hit",
                    )
                    daily_trades += 1
                    daily_pnl += pnl
                # Don't open new trades if position exists
                time.sleep(interval_minutes * 60)
                continue

            # 5. Generate signal
            features = compute_features_live(live_df, template_df, feature_cols)
            if features.shape[1] != len(feature_cols):
                log(
                    f"Feature mismatch: got {features.shape[1]}, expected {len(feature_cols)}"
                )
                time.sleep(60)
                continue

            # Predict
            pred = model.predict(features)
            proba = model.predict_proba(features)
            confidence = max(proba[0])

            if confidence >= MIN_CONFIDENCE:
                direction = int(pred[0])
                entry_price = (
                    mt5.symbol_info_tick(SYMBOL).ask
                    if direction == 1
                    else mt5.symbol_info_tick(SYMBOL).bid
                )
                log(
                    f"Signal: {'BUY' if direction == 1 else 'SELL'} conf={confidence:.3f} price={entry_price:.2f}"
                )

                result = place_trade(mt5, direction, entry_price, confidence)
                if result:
                    log_trade(
                        entry={
                            "direction": result["direction"],
                            "entry": result["entry"],
                            "confidence": result["confidence"],
                            "ticket": result["ticket"],
                        }
                    )
                    tg(
                        f"🟢 *LONG* @ `{result['entry']:.2f}` | conf=`{confidence:.3f}`"
                        if direction == 1
                        else f"🔴 *SHORT* @ `{result['entry']:.2f}` | conf=`{confidence:.3f}`"
                    )
            else:
                current_price = mt5.symbol_info_tick(SYMBOL).bid
                log(
                    f"No signal: max conf={confidence:.3f} < {MIN_CONFIDENCE} price={current_price:.2f}"
                )

        except Exception as e:
            log(f"LOOP ERROR: {e}")
            import traceback

            traceback.print_exc()
            try:
                tg(f"⚠️ Bot loop error: {e}")
            except Exception:
                pass

        # Wait for next bar
        time.sleep(interval_minutes * 60)


def _send_heartbeat(mt5, trades_today: int, daily_pnl: float, monthly_pnl: float):
    """Send heartbeat to Telegram."""
    try:
        balance = mt5.account_info().balance if mt5.account_info() else 0
        if NOTIFIER:
            NOTIFIER.heartbeat(
                trades_today=trades_today,
                win_rate_7d=0.0,  # Will be calculated from CSV
                balance=balance,
            )
    except Exception as e:
        log(f"Heartbeat error: {e}")


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="GRAXIA-OS Paper Trade Bot")
    parser.add_argument(
        "--interval", type=int, default=15, help="Check interval in minutes"
    )
    parser.add_argument("--force", action="store_true", help="Skip MT5 preflight check")
    args = parser.parse_args()

    # Load model
    model = load_model()
    if model is None:
        log(
            "No trained model found. Train one first:\n"
            "  python scripts/walk_forward.py --symbol XAUUSD --freq 15min"
        )
        return

    # Load feature template
    template_df, feature_cols = load_feature_template()
    if template_df is None:
        log("No feature data found.")
        return

    log(f"Model ready: {type(model).__name__}")
    log(f"Feature columns: {len(feature_cols)}")
    log(f"B2 stop: ${B2_STOP_DOLLARS}")
    log(f"Min confidence: {MIN_CONFIDENCE}")

    # Start main loop
    main_loop(model, feature_cols, template_df, interval_minutes=args.interval)


if __name__ == "__main__":
    main()
