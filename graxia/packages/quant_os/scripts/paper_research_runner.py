#!/usr/bin/env python3
"""
Paper Trade Runner — Research mode.
Logs every signal, trade, and outcome for measurement.
"""

import csv
import time
from datetime import UTC, datetime
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import xgboost as xgb

BASE = Path(__file__).parent.parent
LOG_DIR = BASE / "logs" / "paper_research"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Config
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
CONF_THRESHOLD = 0.75
MAX_POSITIONS = 1
STOP_LOSS_USD = 6.30  # B2 stop
TAKE_PROFIT_USD = 12.60  # 2:1 RR
LOT_SIZE = 0.01

# CSV log
TRADE_LOG = LOG_DIR / "trades.csv"
SIGNAL_LOG = LOG_DIR / "signals.csv"


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg))


def ensure_mt5():
    if not mt5.initialize():
        error = mt5.last_error()
        raise RuntimeError("MT5 init failed: %s" % str(error))
    info = mt5.account_info()
    if info and "demo" not in info.server.lower() and "practice" not in info.server.lower():
        raise RuntimeError("LIVE ACCOUNT: %s" % info.server)
    log("MT5 connected: %s" % info.server)
    return mt5


def get_bars(mt5, symbol, timeframe, n=200):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def compute_features(df):
    close = df["close"].values.astype(float)
    returns = np.diff(close) / close[:-1]
    returns = np.concatenate([[0], returns])

    features = pd.DataFrame(index=df.index)
    features["return_1"] = returns
    features["return_5"] = pd.Series(returns).rolling(5).mean().values
    features["return_10"] = pd.Series(returns).rolling(10).mean().values
    features["vol_10"] = pd.Series(returns).rolling(10).std().values
    features["vol_20"] = pd.Series(returns).rolling(20).std().values
    features["vol_ratio"] = features["vol_10"] / (features["vol_20"] + 1e-10)
    features["hour_utc"] = df.index.hour
    features["is_london"] = ((df.index.hour >= 7) & (df.index.hour < 17)).astype(int)
    features["is_ny"] = ((df.index.hour >= 12) & (df.index.hour < 22)).astype(int)
    return features


def load_model():
    """Load or train a simple model."""
    model_path = BASE / "ml" / "models" / "paper_research_xgb.pkl"
    if model_path.exists():
        import pickle

        with open(model_path, "rb") as f:
            return pickle.load(f)

    # Train on historical data
    log("Training model on historical data...")
    df = pd.read_csv(BASE / "data" / "XAUUSD_H1.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")

    features = compute_features(df)
    target = (features["return_1"].shift(-1) > 0).astype(int)
    features = features.join(target.rename("target")).dropna()

    feature_cols = [c for c in features.columns if c not in ["target"]]
    X = features[feature_cols].values.astype(np.float32)
    y = features["target"].values

    model = xgb.XGBClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X, y)

    # Save
    model_path.parent.mkdir(parents=True, exist_ok=True)
    import pickle

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    log("Model saved: %s" % model_path.name)

    return model


def log_signal(signal_data):
    """Log signal to CSV."""
    file_exists = SIGNAL_LOG.exists()
    with open(SIGNAL_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=signal_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(signal_data)


def log_trade(trade_data):
    """Log trade to CSV."""
    file_exists = TRADE_LOG.exists()
    with open(TRADE_LOG, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=trade_data.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade_data)


def get_open_positions(mt5, symbol):
    positions = mt5.positions_get(symbol=symbol)
    return positions if positions else []


def main():
    log("Starting paper research runner...")
    mt5 = ensure_mt5()
    model = load_model()

    feature_cols = [
        "return_1",
        "return_5",
        "return_10",
        "vol_10",
        "vol_20",
        "vol_ratio",
        "hour_utc",
        "is_london",
        "is_ny",
    ]

    cycle = 0
    while True:
        cycle += 1
        try:
            # Get latest bars
            df = get_bars(mt5, SYMBOL, TIMEFRAME, 200)
            if df is None or len(df) < 50:
                log("Insufficient data, waiting...")
                time.sleep(60)
                continue

            # Compute features
            features = compute_features(df)
            latest = features.iloc[[-1]]
            X = latest[feature_cols].values.astype(np.float32)

            # Predict
            proba = model.predict_proba(X)[0]
            conf = max(proba)
            direction = 1 if proba[1] > proba[0] else -1

            # Session filter
            hour = df.index[-1].hour
            is_session = 7 <= hour < 22  # London or NY

            # Log signal
            signal = {
                "time": datetime.now(UTC).isoformat(),
                "symbol": SYMBOL,
                "direction": "BUY" if direction == 1 else "SELL",
                "confidence": round(conf, 4),
                "price": float(df["close"].iloc[-1]),
                "hour_utc": hour,
                "is_session": is_session,
                "threshold": CONF_THRESHOLD,
            }
            log_signal(signal)

            # Check if we should trade
            positions = get_open_positions(mt5, SYMBOL)
            if len(positions) >= MAX_POSITIONS:
                if cycle % 10 == 0:
                    log("Positions full (%d), waiting..." % len(positions))
                time.sleep(300)
                continue

            if conf < CONF_THRESHOLD:
                if cycle % 10 == 0:
                    log("Conf %.2f < %.2f, no trade" % (conf, CONF_THRESHOLD))
                time.sleep(300)
                continue

            if not is_session:
                if cycle % 10 == 0:
                    log("Outside session (hour=%d), no trade" % hour)
                time.sleep(300)
                continue

            # Place trade
            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                continue

            price = tick.ask if direction == 1 else tick.bid
            sl = price - STOP_LOSS_USD if direction == 1 else price + STOP_LOSS_USD
            tp = price + TAKE_PROFIT_USD if direction == 1 else price - TAKE_PROFIT_USD

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": LOT_SIZE,
                "type": mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 10,
                "magic": 123456,
                "comment": "RESEARCH conf=%.2f" % conf,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                side = "LONG" if direction == 1 else "SHORT"
                log("OPEN %s @ %.2f SL=%.2f TP=%.2f conf=%.2f ticket=%d" % (side, price, sl, tp, conf, result.order))

                trade = {
                    "open_time": datetime.now(UTC).isoformat(),
                    "symbol": SYMBOL,
                    "side": side,
                    "entry_price": price,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "confidence": round(conf, 4),
                    "ticket": result.order,
                    "status": "OPEN",
                }
                log_trade(trade)
            else:
                err = result.comment if result else "no response"
                log("ORDER FAILED: %s" % err)

            time.sleep(300)  # Wait 5 minutes

        except KeyboardInterrupt:
            log("Stopped by user")
            break
        except Exception as e:
            log("Error: %s" % str(e))
            time.sleep(60)

    mt5.shutdown()
    log("Done")


if __name__ == "__main__":
    main()
