#!/usr/bin/env python3
"""
BTCUSD ML Paper Trader — OMS-routed paper trading with features_v3 model.
===========================================================================
Loads the v3 XGBoost model, fetches live M15 bars from MT5, computes the
17-feature set matching training, and routes orders through the OMS.

Model:  ml/models/xgboost_v3_BTCUSD_20260703_131150.pkl
        17 features, balanced_acc=0.5228, recall_0=0.41, recall_1=0.64

Usage:
    python scripts/paper_trade_btcusd_ml.py
    python scripts/paper_trade_btcusd_ml.py --interval 900
    python scripts/paper_trade_btcusd_ml.py --threshold 0.60 --vol-target 0.15
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Load .env before anything else
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# ── Config ──────────────────────────────────────────────────
SYMBOL = "BTCUSD"
MODEL_PATH = BASE / "ml" / "models" / "xgboost_v3_BTCUSD_20260703_131150.pkl"
CSV_PATH = BASE / "data" / "btcusd_ml_paper_log.csv"
HEARTBEAT_PATH = BASE / "data" / "btcusd_ml_heartbeat.txt"
STATE_PATH = BASE / "data" / "btcusd_ml_state.json"

# BTCUSD contract specs (Pepperstone Razor)
CONTRACT_SIZE = 1  # 1 lot = 1 BTC
POINT_VALUE = 1.0  # $1 per point
MIN_LOT = 0.01
LOT_STEP = 0.01
MAX_LOT = 1.0
MIN_STOP_POINTS = 50.0  # minimum stop distance in points ($50)

# features_v3 technical indicators — must match training exactly
FEATURES_V3 = [
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_width",
    "atr_ratio",
    "adx_14",
    "dist_ma_20",
    "dist_ma_50",
    "dist_ma_200",
    "ret_1",
    "ret_5",
    "ret_10",
    "atr_14",
    "volume_ratio",
    "high_low_pct",
    "close_open_pct",
]

LOG_HEADERS = [
    "timestamp",
    "signal_id",
    "direction",
    "probability",
    "entry_price",
    "lot_size",
    "stop_loss",
    "take_profit",
    "atr_14",
    "rvol_20",
    "spread",
    "order_status",
    "broker_order_id",
    "pnl",
    "notes",
]


def log(msg: str) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def get_notifier():
    try:
        from core.telegram_notify import TelegramNotifier

        return TelegramNotifier()
    except (RuntimeError, ImportError):
        return None


NOTIFIER = get_notifier()


def tg(msg: str) -> None:
    if NOTIFIER:
        try:
            NOTIFIER.send(msg)
        except Exception:
            pass
    log(msg)


# ── MT5 ─────────────────────────────────────────────────────
_mt5 = None


def ensure_mt5():
    global _mt5
    if _mt5 is not None:
        return _mt5
    import MetaTrader5 as mt5

    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    acct = mt5.account_info()
    if acct is None:
        raise RuntimeError("Cannot read MT5 account info")
    server = acct.server.lower()
    if "demo" not in server and "practice" not in server:
        raise RuntimeError(
            f"LIVE ACCOUNT DETECTED: {acct.server} (login={acct.login}). " "paper_trade requires demo server."
        )
    log(f"MT5 connected — {acct.server} (demo) balance={acct.balance}")
    _mt5 = mt5
    return mt5


def fetch_bars(n_bars: int = 300) -> pd.DataFrame | None:
    """Fetch latest BTCUSD M15 bars from MT5."""
    mt5 = ensure_mt5()
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, n_bars)
    if rates is None or len(rates) == 0:
        log("No bars returned from MT5")
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    # MT5 uses tick_volume for crypto
    if "tick_volume" in df.columns and "volume" not in df.columns:
        df["volume"] = df["tick_volume"]
    elif "real_volume" in df.columns:
        df["volume"] = df["real_volume"]
    log(f"Fetched {len(df)} bars — latest: {df.index[-1]}")
    return df


def get_spread() -> float:
    mt5 = ensure_mt5()
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return 0.0
    return tick.ask - tick.bid


def get_open_position() -> dict | None:
    mt5 = ensure_mt5()
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
            "open_time": datetime.fromtimestamp(pos.time, tz=UTC),
        }
    return None


# ── Feature Engineering ─────────────────────────────────────
def compute_features_v3(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the 17 features_v3 technical indicators on live data.

    Must match training pipeline in train_features_v3.py exactly.
    All indicators are lag-safe (use only past/current bar data).
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]

    out = pd.DataFrame(index=df.index)

    # --- RSI 14 ---
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100 - (100 / (1 + rs))

    # --- MACD (12, 26, 9) ---
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema_12 - ema_26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    # --- Bollinger Band width (20, 2σ) ---
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    out["bb_width"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)

    # --- ATR ratio (ATR14 / close) ---
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    atr_14 = tr.rolling(14).mean()
    out["atr_ratio"] = atr_14 / close.replace(0, np.nan)

    # --- ADX (14) ---
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    atr_smooth = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    out["adx_14"] = dx.rolling(14).mean()

    # --- Distance from MA 20, 50, 200 ---
    for period in [20, 50, 200]:
        ma = close.rolling(period).mean()
        out[f"dist_ma_{period}"] = (close - ma) / ma.replace(0, np.nan)

    # --- Returns ---
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)

    # --- ATR 14 (absolute) ---
    out["atr_14"] = atr_14

    # --- Volume ratio ---
    if "volume" in df.columns:
        vol = df["volume"]
    elif "tick_volume" in df.columns:
        vol = df["tick_volume"]
    else:
        vol = pd.Series(0, index=df.index)
    vol_ma20 = vol.rolling(20).mean()
    out["volume_ratio"] = vol / vol_ma20.replace(0, np.nan)

    # --- High-low pct ---
    out["high_low_pct"] = (high - low) / close.replace(0, np.nan)

    # --- Close-open pct ---
    if "open" in df.columns:
        out["close_open_pct"] = (close - df["open"]) / df["open"].replace(0, np.nan)
    else:
        out["close_open_pct"] = 0.0

    return out


# ── Model ───────────────────────────────────────────────────
def load_model():
    """Load the BTCUSD v3 XGBoost model."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    with open(MODEL_PATH, "rb") as f:
        raw = pickle.load(f)
    if isinstance(raw, dict) and "model" in raw:
        model = raw["model"]
        feature_names = raw.get("feature_names", FEATURES_V3)
        log(f"Model loaded: {MODEL_PATH.name} — {len(feature_names)} features")
        return model, feature_names
    log(f"Model loaded: {MODEL_PATH.name} (raw XGBClassifier)")
    return raw, FEATURES_V3


# ── Position Sizing (vol targeting) ─────────────────────────
def compute_position_size(
    atr_14: float,
    balance: float,
    vol_target: float = 0.15,
    risk_per_trade: float = 0.01,
) -> float:
    """Vol-targeting position size for BTCUSD.

    Formula: lots = (balance * vol_target) / (atr_14 * contract_size * sqrt(96))
    Capped by risk_per_trade and MAX_LOT.
    """
    if atr_14 <= 0:
        return MIN_LOT

    # Vol-targeting: daily_vol ≈ atr_14 * sqrt(96 bars/day)
    daily_vol = atr_14 * np.sqrt(96)
    if daily_vol <= 0:
        return MIN_LOT

    # Target dollar risk = balance * vol_target / sqrt(252) per day
    target_daily_risk = balance * vol_target / np.sqrt(252)
    lots_raw = target_daily_risk / (daily_vol * CONTRACT_SIZE)

    # Risk cap: max loss per trade = balance * risk_per_trade
    # Stop at 2× ATR → max_loss = 2 * atr_14 * lots * contract_size
    stop_distance = 2.0 * atr_14
    max_loss_per_lot = stop_distance * CONTRACT_SIZE
    risk_cap_lots = (balance * risk_per_trade) / max_loss_per_lot if max_loss_per_lot > 0 else MAX_LOT

    lots = min(lots_raw, risk_cap_lots, MAX_LOT)
    lots = max(round(lots / LOT_STEP) * LOT_STEP, MIN_LOT)

    return lots


# ── OMS Order Routing ───────────────────────────────────────
def submit_order_oms(
    signal_id: str,
    side: str,
    quantity: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """Submit order through the OMS (not direct MT5).

    Falls back to direct MT5 if OMS is unavailable.
    Returns order result dict.
    """
    # Try OMS path first
    try:
        from execution.broker_adapter import MT5BrokerAdapter
        from execution.oms import OMS

        adapter = MT5BrokerAdapter()
        oms = OMS(adapters={"mt5": adapter}, risk_engine=None)
        order = oms.submit_order(
            signal_id=signal_id,
            symbol=SYMBOL,
            asset_class="crypto",
            side=side,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trace_id=f"btcusd_ml_{signal_id[:8]}",
        )
        log(f"OMS order submitted: {order.id} status={order.status}")
        return {
            "status": "submitted",
            "order_id": str(order.id),
            "broker_order_id": order.broker_order_id,
            "side": side,
            "quantity": quantity,
        }
    except Exception as e:
        log(f"OMS unavailable ({e}), falling back to direct MT5")
        return _submit_direct_mt5(side, quantity, stop_loss, take_profit)


def _submit_direct_mt5(
    side: str,
    quantity: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> dict:
    """Direct MT5 order submission (fallback)."""
    mt5 = ensure_mt5()
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return {"status": "error", "reason": "no tick"}

    price = tick.ask if side == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": quantity,
        "type": order_type,
        "price": price,
        "sl": stop_loss or 0.0,
        "tp": take_profit or 0.0,
        "deviation": 20,
        "magic": 20260703,
        "comment": "BTCUSD-ML",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"MT5 order filled: ticket={result.order} price={result.price}")
        return {
            "status": "filled",
            "broker_order_id": str(result.order),
            "fill_price": result.price,
            "side": side,
            "quantity": quantity,
        }
    else:
        err = result.comment if result else "no response"
        log(f"MT5 order FAILED: {err}")
        return {"status": "error", "reason": err}


def close_position_oms(broker_position_id: str, volume: float) -> dict:
    """Close position through OMS."""
    try:
        from execution.broker_adapter import MT5BrokerAdapter
        from execution.oms import OMS

        adapter = MT5BrokerAdapter()
        oms = OMS(adapters={"mt5": adapter}, risk_engine=None)
        order = oms.close_position(
            symbol=SYMBOL,
            broker_position_id=broker_position_id,
            volume=volume,
            asset_class="crypto",
            signal_id=f"close_{uuid.uuid4().hex[:8]}",
        )
        return {"status": "closed", "order_id": str(order.id)}
    except Exception as e:
        log(f"OMS close failed ({e}), using direct MT5")
        return _close_direct_mt5(broker_position_id, volume)


def _close_direct_mt5(ticket: str, volume: float) -> dict:
    mt5 = ensure_mt5()
    pos = mt5.positions_get(ticket=int(ticket))
    if not pos:
        return {"status": "error", "reason": "position not found"}
    pos = pos[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.bid if pos.type == 0 else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": close_type,
        "position": int(ticket),
        "price": price,
        "deviation": 20,
        "magic": 20260703,
        "comment": "BTCUSD-ML-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"status": "closed", "fill_price": result.price}
    return {"status": "error", "reason": result.comment if result else "no response"}


# ── Logging ─────────────────────────────────────────────────
def log_signal(row: dict) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def write_heartbeat() -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_PATH.write_text(datetime.now(UTC).isoformat())


# ── Main Loop ───────────────────────────────────────────────
def run_loop(
    model,
    feature_names: list[str],
    threshold: float = 0.55,
    vol_target: float = 0.15,
    risk_per_trade: float = 0.01,
    interval_seconds: int = 900,
    stop_atr_mult: float = 2.0,
    tp_atr_mult: float = 3.0,
    max_open_positions: int = 1,
) -> None:
    """Main trading loop — runs every interval_seconds (default: 15min = M15 bar)."""
    state = load_state()
    daily_trades = state.get("daily_trades", 0)
    daily_pnl = state.get("daily_pnl", 0.0)
    current_date = datetime.now(UTC).date().isoformat()

    mt5 = ensure_mt5()
    acct = mt5.account_info()
    balance = acct.balance if acct else 10_000.0

    tg(
        f"🤖 *BTCUSD ML Paper Trader*\n"
        f"Model: `{MODEL_PATH.name}`\n"
        f"Threshold: `{threshold}` | Vol target: `{vol_target}`\n"
        f"Balance: `${balance:,.2f}` | Interval: `{interval_seconds}s`"
    )

    while True:
        try:
            now = datetime.now(UTC)
            today = now.date().isoformat()

            # Reset daily counters
            if today != current_date:
                if daily_trades > 0:
                    tg(f"📊 *Day End* {current_date} | Trades: {daily_trades} | PnL: `${daily_pnl:+.2f}`")
                current_date = today
                daily_trades = 0
                daily_pnl = 0.0

            # Refresh balance
            acct = mt5.account_info()
            balance = acct.balance if acct else balance

            # Check for open position
            pos = get_open_position()

            # Fetch bars and compute features
            bars = fetch_bars(300)
            if bars is None or len(bars) < 200:
                log("Insufficient bars, waiting...")
                time.sleep(60)
                continue

            features_df = compute_features_v3(bars)
            latest = features_df.iloc[-1:]

            # Check for NaN in features
            if latest[feature_names].isna().any(axis=1).iloc[0]:
                log("NaN in features, waiting for more data...")
                time.sleep(60)
                continue

            X = latest[feature_names].values
            proba = model.predict_proba(X)[0]
            prob_buy = float(proba[1])  # P(class=1 = buy)
            prob_sell = float(proba[0])  # P(class=0 = sell)
            pred = int(model.predict(X)[0])

            atr_14 = float(latest["atr_14"].iloc[0])
            spread = get_spread()
            current_price = bars["close"].iloc[-1]

            log(
                f"Signal: pred={pred} P(buy)={prob_buy:.4f} P(sell)={prob_sell:.4f} "
                f"ATR={atr_14:.2f} spread={spread:.2f} price={current_price:.2f}"
            )

            write_heartbeat()

            # ── Position management ──
            if pos:
                # Already have a position — monitor only
                pnl = pos.get("profit", 0)
                log(f"Open {pos['direction']} @ {pos['open_price']:.2f} PnL={pnl:+.2f}")

                # Close if signal reverses with high confidence
                reverse_conf = prob_sell if pos["direction"] == "long" else prob_buy
                if reverse_conf > threshold + 0.10:
                    log(f"Reversal signal (conf={reverse_conf:.4f}), closing position")
                    result = close_position_oms(str(pos["ticket"]), pos["volume"])
                    log(f"Close result: {result}")

                    # Calculate PnL
                    if result.get("fill_price"):
                        if pos["direction"] == "long":
                            pnl = (result["fill_price"] - pos["open_price"]) * pos["volume"] * CONTRACT_SIZE
                        else:
                            pnl = (pos["open_price"] - result["fill_price"]) * pos["volume"] * CONTRACT_SIZE
                        daily_pnl += pnl

                    log_signal(
                        {
                            "timestamp": now.isoformat(),
                            "signal_id": f"close_{uuid.uuid4().hex[:8]}",
                            "direction": pos["direction"],
                            "probability": f"{reverse_conf:.4f}",
                            "entry_price": f"{pos['open_price']:.2f}",
                            "lot_size": f"{pos['volume']:.2f}",
                            "stop_loss": f"{pos['sl']:.2f}",
                            "take_profit": f"{pos['tp']:.2f}",
                            "atr_14": f"{atr_14:.2f}",
                            "rvol_20": "",
                            "spread": f"{spread:.2f}",
                            "order_status": result.get("status", ""),
                            "broker_order_id": result.get("broker_order_id", ""),
                            "pnl": f"{pnl:+.2f}",
                            "notes": "reversal_close",
                        }
                    )

                time.sleep(interval_seconds)
                continue

            # ── No position — check for entry signal ──
            # Skip if spread too wide (> 0.5% of price for BTC)
            spread_pct = spread / current_price if current_price > 0 else 999
            if spread_pct > 0.005:
                log(f"Spread too wide: {spread_pct:.4%} > 0.5%, skipping")
                time.sleep(interval_seconds)
                continue

            signal_id = f"btcusd_{uuid.uuid4().hex[:12]}"

            if prob_buy > threshold:
                # BUY signal
                lot_size = compute_position_size(atr_14, balance, vol_target, risk_per_trade)
                stop_loss = current_price - stop_atr_mult * atr_14
                take_profit = current_price + tp_atr_mult * atr_14

                # Enforce minimum stop distance
                if (current_price - stop_loss) < MIN_STOP_POINTS:
                    stop_loss = current_price - MIN_STOP_POINTS

                log(f"BUY signal: prob={prob_buy:.4f} lots={lot_size} SL={stop_loss:.2f} TP={take_profit:.2f}")

                result = submit_order_oms(
                    signal_id=signal_id,
                    side="buy",
                    quantity=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                daily_trades += 1
                log_signal(
                    {
                        "timestamp": now.isoformat(),
                        "signal_id": signal_id,
                        "direction": "buy",
                        "probability": f"{prob_buy:.4f}",
                        "entry_price": f"{current_price:.2f}",
                        "lot_size": f"{lot_size:.2f}",
                        "stop_loss": f"{stop_loss:.2f}",
                        "take_profit": f"{take_profit:.2f}",
                        "atr_14": f"{atr_14:.2f}",
                        "rvol_20": "",
                        "spread": f"{spread:.2f}",
                        "order_status": result.get("status", ""),
                        "broker_order_id": result.get("broker_order_id", ""),
                        "pnl": "",
                        "notes": f"vol_target={vol_target}",
                    }
                )

                tg(
                    f"🟢 *BTCUSD LONG*\n"
                    f"Entry: `{current_price:.2f}` | SL: `{stop_loss:.2f}` | TP: `{take_profit:.2f}`\n"
                    f"Prob: `{prob_buy:.4f}` | Lots: `{lot_size}` | ATR: `{atr_14:.2f}`"
                )

            elif prob_sell > threshold:
                # SELL signal
                lot_size = compute_position_size(atr_14, balance, vol_target, risk_per_trade)
                stop_loss = current_price + stop_atr_mult * atr_14
                take_profit = current_price - tp_atr_mult * atr_14

                if (stop_loss - current_price) < MIN_STOP_POINTS:
                    stop_loss = current_price + MIN_STOP_POINTS

                log(f"SELL signal: prob={prob_sell:.4f} lots={lot_size} SL={stop_loss:.2f} TP={take_profit:.2f}")

                result = submit_order_oms(
                    signal_id=signal_id,
                    side="sell",
                    quantity=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                daily_trades += 1
                log_signal(
                    {
                        "timestamp": now.isoformat(),
                        "signal_id": signal_id,
                        "direction": "sell",
                        "probability": f"{prob_sell:.4f}",
                        "entry_price": f"{current_price:.2f}",
                        "lot_size": f"{lot_size:.2f}",
                        "stop_loss": f"{stop_loss:.2f}",
                        "take_profit": f"{take_profit:.2f}",
                        "atr_14": f"{atr_14:.2f}",
                        "rvol_20": "",
                        "spread": f"{spread:.2f}",
                        "order_status": result.get("status", ""),
                        "broker_order_id": result.get("broker_order_id", ""),
                        "pnl": "",
                        "notes": f"vol_target={vol_target}",
                    }
                )

                tg(
                    f"🔴 *BTCUSD SHORT*\n"
                    f"Entry: `{current_price:.2f}` | SL: `{stop_loss:.2f}` | TP: `{take_profit:.2f}`\n"
                    f"Prob: `{prob_sell:.4f}` | Lots: `{lot_size}` | ATR: `{atr_14:.2f}`"
                )

            else:
                log(f"No signal: P(buy)={prob_buy:.4f} P(sell)={prob_sell:.4f} < threshold={threshold}")

            # Save state
            save_state(
                {
                    "last_run": now.isoformat(),
                    "daily_trades": daily_trades,
                    "daily_pnl": daily_pnl,
                    "current_date": current_date,
                    "balance": balance,
                    "last_prob_buy": prob_buy,
                    "last_prob_sell": prob_sell,
                    "last_atr": atr_14,
                }
            )

        except KeyboardInterrupt:
            log("Interrupted — shutting down")
            break
        except Exception as e:
            log(f"LOOP ERROR: {e}")
            import traceback

            traceback.print_exc()

        time.sleep(interval_seconds)


# ── CLI ─────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="BTCUSD ML Paper Trader")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval seconds (default: 900 = 15min)")
    parser.add_argument("--threshold", type=float, default=0.55, help="Min probability to enter (default: 0.55)")
    parser.add_argument("--vol-target", type=float, default=0.15, help="Annualized vol target (default: 0.15)")
    parser.add_argument("--risk", type=float, default=0.01, help="Max risk per trade as fraction (default: 0.01)")
    parser.add_argument("--stop-mult", type=float, default=2.0, help="Stop loss = ATR * multiplier (default: 2.0)")
    parser.add_argument("--tp-mult", type=float, default=3.0, help="Take profit = ATR * multiplier (default: 3.0)")
    args = parser.parse_args()

    log("=" * 60)
    log("BTCUSD ML Paper Trader v1.0")
    log(f"Model: {MODEL_PATH}")
    log(f"Threshold: {args.threshold} | Vol target: {args.vol_target}")
    log(f"Stop: {args.stop_mult}×ATR | TP: {args.tp_mult}×ATR")
    log("=" * 60)

    model, feature_names = load_model()
    log(f"Features ({len(feature_names)}): {feature_names}")

    run_loop(
        model=model,
        feature_names=feature_names,
        threshold=args.threshold,
        vol_target=args.vol_target,
        risk_per_trade=args.risk,
        interval_seconds=args.interval,
        stop_atr_mult=args.stop_mult,
        tp_atr_mult=args.tp_mult,
    )


if __name__ == "__main__":
    main()
