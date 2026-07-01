#!/usr/bin/env python3
"""
GRAXIA-OS Paper Trade Bot v1.0 — Automated Demo Trading
========================================================
Runs 24/7 on local PC: every 15min generates XAUUSD signal,
places trades with B2 stop ($6.30) at 0.01 lot, logs to CSV,
and sends Telegram alerts.

Config: scripts/telegram_config.toml, .env (MT5_SERVER, TELEGRAM_*)
Usage:  $env:PYTHONIOENCODING='utf-8'; python scripts/paper_trade_bot.py
"""

# Load .env before anything else
try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars

import argparse
import csv
import json
import os
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
LOT_SIZE = 0.10
B2_STOP_DOLLARS = 6.30        # B2 locked stop-loss (1× avg_win)
MIN_CONFIDENCE = 0.85          # B2 locked confidence threshold
CSV_PATH = BASE / "data" / "paper_trade_log.csv"
SESSION_PATH = BASE / "data" / "paper_trade_session.json"
HEARTBEAT_PATH = BASE / "data" / "heartbeat.txt"
FEATURES_V2_DIR = BASE / "artifacts" / "features_v2"
MODEL_DIRS = [
    BASE / "artifacts" / "strategy_model", # strategy model
    BASE / "ml" / "models",  # ML saved models
]

HEADERS = [
    "timestamp", "direction", "entry_price", "exit_price", "exit_reason",
    "stop_filled_at", "intended_stop", "slippage", "pnl_gross", "pnl_net",
    "event_flag", "notes",
]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    safe = msg.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    try:
        print(f"[{ts}] {safe}")
    except UnicodeEncodeError:
        print(f"[{ts}] {safe.encode('ascii', errors='replace').decode('ascii')}")


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
        # Safety check: reject live accounts
        account_info = mt5.account_info()
        if account_info is None:
            raise RuntimeError("Cannot read MT5 account info — check connection")
        server_lower = account_info.server.lower()
        if "demo" not in server_lower and "practice" not in server_lower:
            raise RuntimeError(
                f"LIVE ACCOUNT DETECTED: {account_info.server} "
                f"(login={account_info.login}). "
                f"paper_trade_bot requires demo server. "
                f"Set MT5_SERVER env var to a demo server."
            )
        _mt5_initialized = True
        log(f"MT5 initialized — account: {account_info.server} (demo)")
    return mt5


def get_live_data(mt5, n_bars: int = 100) -> pd.DataFrame | None:
    """Fetch latest XAUUSD M15 bars from MT5."""
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
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
def load_best_model():
    """Load the newest trained XGBoost model with feature names."""
    for model_dir in MODEL_DIRS:
        if model_dir.exists():
            models = sorted(model_dir.glob("xgboost*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if models:
                path = models[0]
                with open(path, "rb") as f:
                    raw = pickle.load(f)
                # Models saved as {'model': XGBClassifier, 'feature_names': [...], ...}
                if isinstance(raw, dict) and 'model' in raw:
                    model = raw['model']
                    feature_names = raw.get('feature_names', [])
                    log(f"Model loaded: {path.name} ({type(model).__name__}, {len(feature_names)} features)")
                    return model, feature_names
                else:
                    log(f"Model loaded: {path.name} ({type(raw).__name__}, no feature_names)")
                    return raw, []
    log("No XGBoost models found — will retrain from walk-forward")
    return None, []


def load_feature_template() -> tuple[pd.DataFrame | None, list[str]]:
    """Load historical features to use as feature template."""
    path = FEATURES_V2_DIR / f"features_v2_{SYMBOL}_15min.parquet"
    if not path.exists():
        log(f"Feature template not found: {path}")
        return None, []
    df = pd.read_parquet(path)
    exclude = {
        "target", "target_return", "symbol", "freq",
        "tb_label", "tb_bar_hit", "tb_side", "tb_ret",
        "tb_k_upper", "tb_k_lower", "open", "high", "low", "close",
        "volume", "tick_count",
    }
    feature_cols = [c for c in df.columns if c not in exclude
                    and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]
    log(f"Feature template: {len(df)} rows, {len(feature_cols)} features")
    return df, feature_cols


def compute_features_live(live_df: pd.DataFrame, template_df: pd.DataFrame,
                          feature_cols: list[str]) -> np.ndarray:
    """
    Compute ALL 40 features on live data matching training pipeline exactly.
    Uses only OHLCV data from MT5 bars.
    """
    from datetime import timezone as tz
    df = live_df.copy()

    # --- Returns ---
    for p in [1, 5, 10, 15, 30, 60]:
        df[f"ret_{p}bar"] = df["close"].pct_change(p)

    # --- ATR ---
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    for w in [7, 14, 21]:
        df[f"atr_{w}"] = tr.rolling(w).mean()

    # --- Realized Volatility ---
    log_ret = np.log(df["close"] / df["close"].shift(1))
    for w in [10, 20, 60]:
        df[f"rvol_{w}"] = log_ret.rolling(w).std() * np.sqrt(252 * 96)  # annualized

    # --- RSI ---
    delta = df["close"].diff()
    for p in [7, 14, 21]:
        gain = delta.clip(lower=0).rolling(p).mean()
        loss = (-delta.clip(upper=0)).rolling(p).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f"rsi_{p}"] = 100 - (100 / (1 + rs))

    # --- Stochastic ---
    low14 = df["low"].rolling(14).min()
    high14 = df["high"].rolling(14).max()
    df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14).replace(0, np.nan)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # --- CCI ---
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["cci_20"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())

    # --- Williams %R ---
    df["willr_14"] = -100 * (high14 - df["close"]) / (high14 - low14).replace(0, np.nan)

    # --- EMA distances ---
    for p in [5, 10, 20, 200]:
        ema = df["close"].ewm(span=p, adjust=False).mean()
        df[f"ema_{p}_dist"] = (df["close"] - ema) / ema

    # --- SMA cross ---
    sma20 = df["close"].rolling(20).mean()
    sma50 = df["close"].rolling(50).mean()
    df["sma_20_50_cross"] = (sma20 - sma50) / sma50

    # --- Bollinger Bands ---
    sma20_bb = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    upper_bb = sma20_bb + 2 * std20
    lower_bb = sma20_bb - 2 * std20
    df["bb_width"] = (upper_bb - lower_bb) / sma20_bb
    df["bb_pctb"] = (df["close"] - lower_bb) / (upper_bb - lower_bb).replace(0, np.nan)
    df["bb_squeeze"] = (df["bb_width"] < df["bb_width"].rolling(120).mean()).astype(float)

    # --- Volume (MT5 uses tick_volume) ---
    if "volume" not in df.columns and "tick_volume" in df.columns:
        df["volume"] = df["tick_volume"]
    elif "volume" not in df.columns:
        df["volume"] = 0
    obv = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
    df["obv_slope_20"] = obv.rolling(20).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 20 else 0, raw=True
    )
    vol_ma20 = df["volume"].rolling(20).mean()
    vol_ma10 = df["volume"].rolling(10).mean()
    df["vol_ratio_20"] = df["volume"] / vol_ma20.replace(0, np.nan)
    df["vol_ratio_10"] = df["volume"] / vol_ma10.replace(0, np.nan)

    # --- Candlestick patterns ---
    body = (df["close"] - df["open"]).abs()
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["body_ratio"] = body / candle_range
    df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / candle_range
    df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / candle_range

    # Doji: body < 10% of range
    df["is_doji"] = (body / candle_range < 0.10).astype(float)
    # Hammer: small body at top, long lower shadow
    df["is_hammer"] = ((df["lower_shadow"] > 0.6) & (body / candle_range < 0.3)).astype(float)
    # Bullish engulfing
    prev_bearish = (df["open"].shift(1) > df["close"].shift(1))
    curr_bullish = (df["close"] > df["open"])
    df["is_bull_engulf"] = (prev_bearish & curr_bullish &
                            (df["close"] > df["open"].shift(1)) &
                            (df["open"] < df["close"].shift(1))).astype(float)

    # --- Session flags (UTC) ---
    try:
        hour = df.index.hour
    except AttributeError:
        hour = pd.DatetimeIndex(df.index).hour
    df["is_asian_session"] = ((hour >= 0) & (hour < 8)).astype(float)
    df["is_london_session"] = ((hour >= 8) & (hour < 16)).astype(float)
    df["is_ny_session"] = ((hour >= 13) & (hour < 21)).astype(float)

    # --- Calendar ---
    try:
        df["day_of_week"] = df.index.dayofweek
        df["day_of_month"] = df.index.day
        df["month"] = df.index.month
    except AttributeError:
        idx = pd.DatetimeIndex(df.index)
        df["day_of_week"] = idx.dayofweek
        df["day_of_month"] = idx.day
        df["month"] = idx.month

    # --- Select only model features ---
    available = [c for c in feature_cols if c in df.columns]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        log(f"⚠️ Missing features (filling 0): {missing}")
        for c in missing:
            df[c] = 0.0

    result = df[feature_cols].fillna(0).values
    return result[-1:]  # latest bar only


def retrain_walk_forward():
    """Retrain XGBoost on latest features via walk-forward and save model."""
    import xgboost as xgb
    import json

    df, feature_cols = load_feature_template()
    if df is None or len(feature_cols) == 0:
        return None

    # Handle {-1, 0, 1} → {0, 1} (filter out 0 = no-trade)
    df_filtered = df[df["target"] != 0].copy()
    df_filtered["target"] = df_filtered["target"].replace({-1: 0, 1: 1})

    # Use last 5000 bars for training, latest 1000 for validation
    train_data = df_filtered.iloc[:-1000]
    test_data = df_filtered.iloc[-1000:]
    X_train = train_data[feature_cols].fillna(0).values
    y_train = train_data["target"].values.astype(int)
    X_test = test_data[feature_cols].fillna(0).values
    y_test = test_data["target"].values.astype(int)

    model = xgb.XGBClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    model.fit(X_train, y_train)
    train_acc = (model.predict(X_train) == y_train).mean()
    test_acc = (model.predict(X_test) == y_test).mean()
    log(f"Retrained model: train_acc={train_acc:.4f} test_acc={test_acc:.4f}")

    # Save
    out_dir = BASE / "ml" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"xgboost_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pkl"
    with open(path, "wb") as f:
        pickle.dump(model, f)
    log(f"Model saved: {path}")
    return model


# ============================================================
# TRADE EXECUTION
# ============================================================
def place_trade(mt5, direction: int, confidence: float) -> dict | None:
    """Place market order on MT5 demo with B2 stop."""
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if direction == 1 else tick.bid
    stop_distance = B2_STOP_DOLLARS
    sl = price - stop_distance if direction == 1 else price + stop_distance

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
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
        dir_label = "LONG" if direction == 1 else "SHORT"
        log(f"🟢 {dir_label} @ {price:.2f} SL={sl:.2f} conf={confidence:.3f} ticket={result.order}")
        return {"ticket": result.order, "direction": "long" if direction == 1 else "short",
                "entry": price, "sl": sl, "confidence": confidence}
    else:
        err = result.comment if result else "no response"
        log(f"❌ TRADE FAILED: {err}")
        if result:
            log(f"   retcode={result.retcode}")
        return None


# ============================================================
# LOGGING
# ============================================================
def log_trade(mt5, entry: dict | None = None, close_info: dict | None = None,
              pnl_gross: float = 0.0, reason: str = "natural", event: str = "none"):
    """Append trade record to paper_trade_log.csv."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", newline="") as f:
            csv.writer(f).writerow(HEADERS)

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    if entry:
        row = {"timestamp": now_ts, "direction": entry["direction"],
               "entry_price": f"{entry['entry']:.2f}", "exit_price": "",
               "exit_reason": "", "stop_filled_at": "",
               "intended_stop": str(B2_STOP_DOLLARS), "slippage": "0.0",
               "pnl_gross": "", "pnl_net": "", "event_flag": event,
               "notes": f"Open conf={entry['confidence']:.2f} ticket={entry['ticket']}"}
    elif close_info:
        row = {"timestamp": now_ts, "direction": close_info.get("direction", ""),
               "entry_price": f"{close_info.get('entry_price', 0):.2f}",
               "exit_price": f"{close_info.get('exit_price', 0):.2f}",
               "exit_reason": reason,
               "stop_filled_at": f"{close_info.get('stop_filled_at', 0):.2f}",
               "intended_stop": str(B2_STOP_DOLLARS),
               "slippage": f"{close_info.get('slippage', 0.0):.1f}",
               "pnl_gross": f"{pnl_gross:.2f}", "pnl_net": f"{pnl_gross:.2f}",
               "event_flag": event, "notes": close_info.get("notes", "")}
    else:
        return

    with open(CSV_PATH, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=HEADERS).writerow(row)
    log(f"CSV: {row.get('direction','')} PnL={row.get('pnl_gross','')}")


# ============================================================
# MAIN LOOP
# ============================================================
def main_loop(model, feature_cols: list[str], template_df: pd.DataFrame,
              interval_seconds: int = 60):
    """Main trading loop with REAL-TIME price streaming via Telegram."""
    mt5 = ensure_mt5()
    daily_trades = 0
    daily_pnl = 0.0
    current_date = datetime.now(timezone.utc).date()
    last_sent_bid = 0.0
    last_sent_time = 0.0
    startup_msg_sent = False
    min_price_move = 0.10  # Send update when price moves $0.10+ (tighter with 15s interval)
    max_quiet_minutes = 5  # Or force update every 5 min even if flat
    last_retrain_date = None

    while True:
        try:
            now = datetime.now(timezone.utc)
            date_today = now.date()
            hour_utc = now.hour
            elapsed = time.time() - last_sent_time

            # Reset daily counters at UTC midnight
            if date_today != current_date:
                if daily_trades > 0 or daily_pnl != 0:
                    tg(rf"📊 *Day End* {current_date}\nTrades: {daily_trades} | PnL: \${daily_pnl:.2f}")
                current_date = date_today; daily_trades = 0; daily_pnl = 0.0

            # Auto-retrain every day at 6:00 UTC
            if last_retrain_date != date_today and hour_utc == 6:
                log("Daily auto-retrain...")
                new_model = retrain_walk_forward()
                if new_model:
                    model = new_model
                    last_retrain_date = date_today
                    tg(f"🔄 *Model retrained* {date_today}")
                else:
                    log("Auto-retrain failed, keeping current model")

            # Session filter: Europe only (08:00-17:00 UTC = tighter spreads)
            if hour_utc < 8 or hour_utc >= 17:
                time.sleep(60)
                continue

            # Get live data
            tick = mt5.symbol_info_tick(SYMBOL)
            bid = tick.bid; ask = tick.ask
            spread = ask - bid

            # Startup msg once per session
            if not startup_msg_sent:
                session_str = "EU" if 8 <= hour_utc < 17 else "OUT"
                tg(rf"🤖 *Bot Online* | {SYMBOL}\n"
                   rf"Bid: `{bid:.2f}` | Ask: `{ask:.2f}` | Spread: `\${spread:.2f}`\n"
                   rf"Session: `{session_str}` | Stop: `\${B2_STOP_DOLLARS}` | Conf≥`{MIN_CONFIDENCE}`\n"
                   rf"Lot: `{LOT_SIZE}` | Interval: `{interval_seconds}s` | EU only")
                last_sent_bid = bid; last_sent_time = time.time()
                startup_msg_sent = True

            pos = get_open_position(mt5)
            live_df = get_live_data(mt5, 200)
            if live_df is None or len(live_df) < 50:
                time.sleep(30); continue

            # === REAL-TIME PRICE UPDATE TO TELEGRAM ===
            bid_delta = bid - last_sent_bid
            force_send = elapsed > max_quiet_minutes * 60
            price_moved = abs(bid_delta) >= min_price_move

            if force_send or price_moved:
                arrow = "▲" if bid_delta > 0 else "▼" if bid_delta < 0 else "▸"
                delta_str = f"`{bid_delta:+.2f}`" if abs(bid_delta) >= 0.01 else "`±0.00`"

                # Compute confidence
                conf_str = ""
                try:
                    features = compute_features_live(live_df, template_df, feature_cols)
                    if features.shape[1] == len(feature_cols):
                        proba = model.predict_proba(features)
                        conf = float(max(proba[0]))
                        pred = int(model.predict(features)[0])
                        dir_str = "LONG" if pred else "SHORT"
                        conf_str = f"\n{arrow} {dir_str} conf=`{conf:.3f}`"
                except Exception:
                    pass

                pos_str = ""
                if pos:
                    pnl = pos.get("profit", 0)
                    pos_str = f"\n📌 *{pos['direction'].upper()}* PnL: `${pnl:+.2f}`"

                elapsed_str = f"{int(elapsed//60)}m" if elapsed >= 60 else f"{int(elapsed)}s"
                tg(rf"{arrow} XAUUSD `{bid:.2f}` Δ{delta_str} (spread \${spread:.2f}){conf_str}{pos_str}\n"
                   rf"Day: `${daily_pnl:+.2f}` | {elapsed_str} since last")

                last_sent_bid = bid; last_sent_time = time.time()

            # If position open → monitor stop
            if pos:
                current_price = tick.bid if pos["direction"] == "long" else tick.ask
                pnl = pos.get("profit", 0)
                if pos["sl"]:
                    if (pos["direction"] == "long" and current_price <= pos["sl"]) or \
                       (pos["direction"] == "short" and current_price >= pos["sl"]):
                        log(f"STOP HIT: {pos['direction']} @ {current_price:.2f}")
                        tg(f"❤️ *STOP HIT* | {pos['direction']}\n"
                           f"Entry: `{pos['open_price']:.2f}` | Exit: `{current_price:.2f}`\n"
                           f"PnL: `${pnl:+.2f}` | Day PnL: `${daily_pnl + pnl:+.2f}`")
                        log_trade(mt5, close_info={
                            "direction": pos["direction"], "entry_price": pos["open_price"],
                            "exit_price": pos["sl"], "stop_filled_at": pos["sl"],
                            "slippage": 0.0, "notes": f"B2 stop ticket={pos['ticket']}"
                        }, pnl_gross=pnl, reason="stop_hit")
                        daily_trades += 1; daily_pnl += pnl
                time.sleep(60); continue

            # Generate signal
            features = compute_features_live(live_df, template_df, feature_cols)
            if features.shape[1] != len(feature_cols):
                log(f"Feature shape mismatch: {features.shape[1]} vs {len(feature_cols)}")
                time.sleep(60); continue

            proba = model.predict_proba(features)
            confidence = float(max(proba[0]))
            direction = int(model.predict(features)[0])

            if confidence >= MIN_CONFIDENCE:
                entry_price = tick.ask if direction == 1 else tick.bid
                log(f"SIGNAL: {'BUY' if direction == 1 else 'SELL'} conf={confidence:.3f} price={entry_price:.2f}")
                result = place_trade(mt5, direction, confidence)
                if result:
                    log_trade(mt5, entry=result)
                    dir_emoji = "🟢" if direction == 1 else "🔴"
                    tg(rf"{dir_emoji} *TRADE OPEN* {'LONG' if direction == 1 else 'SHORT'}\n"
                       rf"Entry: `{entry_price:.2f}` | SL: `{result['sl']:.2f}`\n"
                       rf"Conf: `{confidence:.3f}` | Risk: `\${B2_STOP_DOLLARS}`")
            else:
                log(f"No signal: max conf={confidence:.3f} < {MIN_CONFIDENCE}")

        except Exception as e:
            log(f"LOOP ERROR: {e}")
            import traceback; traceback.print_exc()

        time.sleep(interval_seconds)


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="GRAXIA-OS Paper Trade Bot")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval seconds")
    parser.add_argument("--retrain", action="store_true", help="Retrain model before starting")
    args = parser.parse_args()

    log("=" * 60)
    log("GRAXIA-OS Paper Trade Bot v2.0 (Mega Features)")
    log("=" * 60)

    # Load model with feature names
    model, model_features = load_best_model()
    if model is None or args.retrain:
        log("Retraining model on latest data...")
        model = retrain_walk_forward()
        if model is None:
            log("FATAL: Cannot load or train a model.")
            return
        model_features = []

    # Use model's feature names if available, else fall back to template
    if model_features:
        feature_cols = model_features
        template_df = None
        log(f"Using model's embedded features: {len(feature_cols)}")
    else:
        template_df, feature_cols = load_feature_template()
        if template_df is None or len(feature_cols) == 0:
            log("FATAL: Feature data not found.")
            return

    log(f"Model: {type(model).__name__}")
    log(f"Features: {len(feature_cols)}")
    log(f"Lot: {LOT_SIZE} | B2 stop: ${B2_STOP_DOLLARS} | Min conf: {MIN_CONFIDENCE}")

    main_loop(model, feature_cols, template_df, interval_seconds=args.interval)


if __name__ == "__main__":
    main()
