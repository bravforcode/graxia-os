"""
GRAXIA Signal Service — lightweight FastAPI for MQL5 EA.

EA sends OHLCV bars via POST /api/signal, service computes features + XGBoost prediction.
Returns JSON: { direction, confidence, sl_distance, entry_price, spread }.

No MT5 dependency — all bar data comes from the EA.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from graxia.packages.quant_os.core.config import get_config
from graxia.packages.quant_os.core.safe_pickle import safe_load_model

logger = structlog.get_logger(__name__)


class _RateLimiter:
    """Simple in-memory rate limiter. Sliding window counter."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, client_id: str = "default") -> bool:
        with self._lock:
            now = time.time()
            window_start = now - self.window_seconds
            self._requests[client_id] = [t for t in self._requests[client_id] if t > window_start]
            if len(self._requests[client_id]) >= self.max_requests:
                return False
            self._requests[client_id].append(now)
            return True


_rate_limiter = _RateLimiter(max_requests=30, window_seconds=60)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_cfg = get_config()
SYMBOL = _cfg.symbols[0] if _cfg.symbols else "XAUUSD"
LOT_SIZE = float(_cfg.units_per_lot)
B2_STOP_DOLLARS = 3.00
MIN_CONFIDENCE = _cfg.ml_min_confidence
LOG_DIR = Path("/app/data")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

_model = None
_feature_names: list[str] = []
_model_loaded = False
_model_version: str = ""
_model_lock = threading.Lock()


def _load_model():
    global _model, _feature_names, _model_loaded
    if _model_loaded:
        return

    with _model_lock:
        if _model_loaded:
            return

        base = Path("/app")
        model_dirs = [
            base / "artifacts" / "strategy_model",
            base / "ml" / "models",
        ]

        # Try symbol-specific models first, then generic
        for d in model_dirs:
            if not d.exists():
                continue
            all_models = sorted(d.glob("xgboost*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
            # Prefer models with symbol name
            symbol_models = [m for m in all_models if SYMBOL in m.name]
            generic_models = [m for m in all_models if SYMBOL not in m.name]
            ordered = symbol_models + generic_models

            for path in ordered:
                try:
                    raw = safe_load_model(path)
                except Exception as e:
                    logger.warning("model.load_error", path=str(path), error=str(e))
                    continue

                if isinstance(raw, dict) and "model" in raw:
                    _model = raw["model"]
                    _feature_names = raw.get("feature_names", [])
                    if _feature_names:
                        logger.info("model.loaded", path=str(path), features=len(_feature_names))
                        _model_version = path.stem
                        _model_loaded = True
                        return
                    else:
                        logger.info("model.loaded_no_features", path=str(path))
                        continue

        # No model with features found — retrain
        _retrain_model()


def _retrain_model():
    """Retrain model using ONLY the 40 features available in live pipeline."""
    global _model, _feature_names, _model_loaded

    import xgboost as xgb

    features_path = Path("/app/artifacts/features_v2") / f"features_v2_{SYMBOL}_15min.parquet"
    if not features_path.exists():
        logger.warning("model.no_features", path=str(features_path))
        return

    try:
        df_full = pd.read_parquet(features_path)
    except Exception as e:
        logger.warning("model.features_load_error", error=str(e))
        return

    # Compute the 40 live features on training data
    # This ensures training features == live features
    live_feature_cols = []

    # Returns
    for p in [1, 5, 10, 15, 30, 60]:
        col = f"ret_{p}bar"
        if col in df_full.columns:
            live_feature_cols.append(col)

    # ATR
    for w in [7, 14, 21]:
        col = f"atr_{w}"
        if col in df_full.columns:
            live_feature_cols.append(col)

    # Realized Volatility
    for w in [10, 20, 60]:
        col = f"rvol_{w}"
        if col in df_full.columns:
            live_feature_cols.append(col)

    # RSI
    for p in [7, 14, 21]:
        col = f"rsi_{p}"
        if col in df_full.columns:
            live_feature_cols.append(col)

    # Other known live features
    known_live = [
        "stoch_k",
        "stoch_d",
        "cci_20",
        "willr_14",
        "ema_5_dist",
        "ema_10_dist",
        "ema_20_dist",
        "ema_200_dist",
        "sma_20_50_cross",
        "bb_width",
        "bb_pctb",
        "bb_squeeze",
        "obv_slope_20",
        "vol_ratio_20",
        "vol_ratio_10",
        "body_ratio",
        "upper_shadow",
        "lower_shadow",
        "is_doji",
        "is_hammer",
        "is_bull_engulf",
        "is_asian_session",
        "is_london_session",
        "is_ny_session",
        "day_of_week",
        "day_of_month",
        "month",
    ]
    for col in known_live:
        if col in df_full.columns:
            live_feature_cols.append(col)

    if len(live_feature_cols) < 10:
        logger.warning("model.insufficient_live_features", count=len(live_feature_cols))
        return

    # Filter to only live-computable features
    live_feature_cols = list(dict.fromkeys(live_feature_cols))  # dedupe preserving order

    if "target" not in df_full.columns:
        logger.warning("model.no_target_column")
        return

    df_filtered = df_full[df_full["target"] != 0].copy()
    df_filtered["target"] = df_filtered["target"].replace({-1: 0, 1: 1})

    train = df_filtered.iloc[:-1000]
    X_train = train[live_feature_cols].fillna(0).values
    y_train = train["target"].values.astype(int)

    if len(X_train) < 100:
        logger.warning("model.insufficient_training_data", samples=len(X_train))
        return

    _model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    _model.fit(X_train, y_train)
    _feature_names = live_feature_cols

    # Save retrained model to disk for faster restart
    try:
        import pickle

        model_save_dir = Path("/app/artifacts/strategy_model")
        model_save_dir.mkdir(parents=True, exist_ok=True)
        save_path = model_save_dir / f"xgboost_{SYMBOL}_live_features.pkl"
        with open(save_path, "wb") as f:
            pickle.dump(
                {
                    "model": _model,
                    "feature_names": _feature_names,
                    "model_type": "xgboost",
                    "version": datetime.now(UTC).strftime("%Y%m%d_%H%M%S"),
                    "training_samples": len(X_train),
                },
                f,
            )
        logger.info("model.saved_to_disk", path=str(save_path))
    except Exception as e:
        logger.warning("model.save_failed", error=str(e))

    _model_version = f"xgboost_{SYMBOL}_live_features"
    _model_loaded = True
    logger.info("model.retrained_live_features", features=len(live_feature_cols), samples=len(X_train))


# ---------------------------------------------------------------------------
# Feature computation (identical to paper_trade_bot.py)
# ---------------------------------------------------------------------------


def compute_features_live(live_df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    """Compute ALL 40 features on live data matching training pipeline exactly."""
    # FEATURE PARITY — Fixed in Round 2.
    # Training now uses ONLY the 40 features computed here (see _retrain_model()).
    # If this function is modified, update _retrain_model() to match.
    # Missing features are still filled with 0.0 as safety fallback (line ~350).
    df = live_df.copy()

    # Input validation — reject NaN/inf/negative prices
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            if df[col].isna().any():
                logger.warning("feature.NaN_input", column=col)
                df[col] = df[col].fillna(method="ffill").fillna(method="bfill")
            if np.isinf(df[col]).any():
                logger.warning("feature.inf_input", column=col)
                df[col] = df[col].replace([np.inf, -np.inf], np.nan).fillna(method="ffill").fillna(method="bfill")
    # Ensure high >= low >= 0
    if "high" in df.columns and "low" in df.columns:
        df["low"] = df["low"].clip(lower=0)
        df["high"] = df["high"].clip(lower=df["low"])

    # Returns
    for p in [1, 5, 10, 15, 30, 60]:
        df[f"ret_{p}bar"] = df["close"].pct_change(p)

    # ATR
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    for w in [7, 14, 21]:
        df[f"atr_{w}"] = tr.rolling(w).mean()

    # Realized Volatility
    log_ret = np.log(df["close"] / df["close"].shift(1))
    for w in [10, 20, 60]:
        df[f"rvol_{w}"] = log_ret.rolling(w).std() * np.sqrt(252 * 96)

    # RSI
    delta = df["close"].diff()
    for p in [7, 14, 21]:
        gain = delta.clip(lower=0).rolling(p).mean()
        loss = (-delta.clip(upper=0)).rolling(p).mean()
        rs = gain / loss.replace(0, np.nan)
        df[f"rsi_{p}"] = 100 - (100 / (1 + rs))

    # Stochastic
    low14 = df["low"].rolling(14).min()
    high14 = df["high"].rolling(14).max()
    df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14).replace(0, np.nan)
    df["stoch_d"] = df["stoch_k"].rolling(3).mean()

    # CCI
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["cci_20"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())

    # Williams %R
    df["willr_14"] = -100 * (high14 - df["close"]) / (high14 - low14).replace(0, np.nan)

    # EMA distances
    for p in [5, 10, 20, 200]:
        ema = df["close"].ewm(span=p, adjust=False).mean()
        df[f"ema_{p}_dist"] = (df["close"] - ema) / ema

    # SMA cross
    sma20 = df["close"].rolling(20).mean()
    sma50 = df["close"].rolling(50).mean()
    df["sma_20_50_cross"] = (sma20 - sma50) / sma50

    # Bollinger Bands
    sma20_bb = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    upper_bb = sma20_bb + 2 * std20
    lower_bb = sma20_bb - 2 * std20
    df["bb_width"] = (upper_bb - lower_bb) / sma20_bb
    df["bb_pctb"] = (df["close"] - lower_bb) / (upper_bb - lower_bb).replace(0, np.nan)
    df["bb_squeeze"] = (df["bb_width"] < df["bb_width"].rolling(120).mean()).astype(float)

    # Volume
    if "volume" not in df.columns and "tick_volume" in df.columns:
        df["volume"] = df["tick_volume"]
    elif "volume" not in df.columns:
        df["volume"] = 0
    obv = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()

    def _safe_slope(x):
        if len(x) < 2:
            return 0.0
        try:
            slope = np.polyfit(range(len(x)), x, 1)[0]
            if np.isnan(slope) or np.isinf(slope):
                return 0.0
            return slope
        except (np.linalg.LinAlgError, ValueError):
            return 0.0

    df["obv_slope_20"] = obv.rolling(20).apply(_safe_slope, raw=True)
    vol_ma20 = df["volume"].rolling(20).mean()
    vol_ma10 = df["volume"].rolling(10).mean()
    df["vol_ratio_20"] = df["volume"] / vol_ma20.replace(0, np.nan)
    df["vol_ratio_10"] = df["volume"] / vol_ma10.replace(0, np.nan)

    # Candlestick patterns
    body = (df["close"] - df["open"]).abs()
    candle_range = (df["high"] - df["low"]).replace(0, np.nan)
    df["body_ratio"] = body / candle_range
    df["upper_shadow"] = (df["high"] - df[["open", "close"]].max(axis=1)) / candle_range
    df["lower_shadow"] = (df[["open", "close"]].min(axis=1) - df["low"]) / candle_range
    df["is_doji"] = (body / candle_range < 0.10).astype(float)
    df["is_hammer"] = ((df["lower_shadow"] > 0.6) & (body / candle_range < 0.3)).astype(float)
    prev_bearish = df["open"].shift(1) > df["close"].shift(1)
    curr_bullish = df["close"] > df["open"]
    df["is_bull_engulf"] = (
        prev_bearish & curr_bullish & (df["close"] > df["open"].shift(1)) & (df["open"] < df["close"].shift(1))
    ).astype(float)

    # Session flags (UTC) — use bar time from index
    try:
        hour = df.index.hour
    except AttributeError:
        hour = pd.DatetimeIndex(df.index).hour
    df["is_asian_session"] = ((hour >= 0) & (hour < 8)).astype(float)
    df["is_london_session"] = ((hour >= 8) & (hour < 16)).astype(float)
    df["is_ny_session"] = ((hour >= 13) & (hour < 21)).astype(float)

    # Calendar
    try:
        df["day_of_week"] = df.index.dayofweek
        df["day_of_month"] = df.index.day
        df["month"] = df.index.month
    except AttributeError:
        idx = pd.DatetimeIndex(df.index)
        df["day_of_week"] = idx.dayofweek
        df["day_of_month"] = idx.day
        df["month"] = idx.month

    # Select only model features
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        import logging

        logging.getLogger(__name__).warning(
            f"FEATURE MISMATCH: {len(missing)} features missing, filled with 0.0: {missing[:5]}..."
        )
        for c in missing:
            df[c] = 0.0

    result = df[feature_cols].fillna(0).values
    return result[-1:]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="GRAXIA Signal Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://graxia.dev",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)

# ---------------------------------------------------------------------------
# API key verification for sensitive endpoints
# ---------------------------------------------------------------------------
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_signal_api_key(api_key: str = Security(_api_key_header)):
    """Verify X-API-Key header for signal and trade endpoints.

    If SIGNAL_SERVICE_API_KEY env var is not set, the endpoint is open (dev mode).
    In production, always set the env var.
    """
    import os

    expected = os.environ.get("SIGNAL_SERVICE_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="SIGNAL_SERVICE_API_KEY not configured")
    if not api_key or not hmac.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


class BarData(BaseModel):
    time: int  # unix timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class SignalRequest(BaseModel):
    bars: list[BarData]  # last 200 M15 bars from EA
    bid: float
    ask: float
    hour_utc: int


class SignalResponse(BaseModel):
    direction: str  # "long" | "short" | "flat"
    confidence: float
    sl_distance: float
    entry_price: float
    spread: float
    timestamp: str
    model_features: int
    model_version: str = ""  # Track which model version made this prediction


class TradeRequest(BaseModel):
    ticket: int
    direction: str
    entry_price: float
    sl: float
    tp: float
    confidence: float
    lot_size: float
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


@app.on_event("startup")
async def startup():
    _load_model()
    logger.info("signal_service.started", symbol=SYMBOL, features=len(_feature_names))


@app.get("/api/health")
async def health():
    health_data = {
        "status": "ok",
        "model_loaded": _model_loaded,
        "features": len(_feature_names),
        "symbol": SYMBOL,
        "lot_size": LOT_SIZE,
        "b2_stop": B2_STOP_DOLLARS,
    }

    # Add drift status if available
    try:
        from ml.drift_monitor import DriftMonitor

        monitor = DriftMonitor()
        reports = monitor.get_drift_stats(symbol=SYMBOL)
        if reports:
            latest = reports[0]
            health_data["drift"] = {
                "accuracy_window": latest.accuracy_window,
                "accuracy_trend": latest.accuracy_trend,
                "total_predictions": latest.total_predictions,
                "alerts_count": len(latest.alerts),
                "critical_alerts": len([a for a in latest.alerts if a.severity == "critical"]),
            }
            if latest.alerts:
                health_data["status"] = "degraded"
    except Exception:
        health_data["drift"] = {"status": "unavailable"}

    return health_data


@app.post("/api/signal")
async def get_signal(req: SignalRequest, _key: str = Security(verify_signal_api_key)):
    """
    Compute signal from bars sent by EA.
    EA sends last 200 M15 bars, service computes features and returns prediction.
    """
    # Rate limit: max 30 requests per minute
    if not _rate_limiter.allow(client_id="default"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 30 requests/minute.")

    _t0 = time.time()

    if not _model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if len(req.bars) < 50:
        raise HTTPException(status_code=400, detail=f"Need >= 50 bars, got {len(req.bars)}")

    # Validate bar data integrity
    timestamps = [b.time for b in req.bars]
    if len(timestamps) != len(set(timestamps)):
        raise HTTPException(status_code=400, detail="Duplicate timestamps in bars")
    if req.bid <= 0 or req.ask <= 0:
        raise HTTPException(status_code=400, detail=f"Invalid bid/ask: bid={req.bid}, ask={req.ask}")
    if req.ask < req.bid:
        raise HTTPException(status_code=400, detail=f"Ask ({req.ask}) < Bid ({req.bid})")

    try:
        # Convert bars to DataFrame
        records = []
        for b in req.bars:
            records.append(
                {
                    "time": pd.Timestamp(b.time, unit="s", utc=True),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
            )

        df = pd.DataFrame(records)
        df = df.set_index("time")
        df["symbol"] = SYMBOL
        df["freq"] = "15min"

        # Compute features
        features = compute_features_live(df, _feature_names)
        _feat_ms = (time.time() - _t0) * 1000
        logger.info("signal.feature_time_ms", ms=round(_feat_ms, 1))
        if features.shape[1] != len(_feature_names):
            raise HTTPException(status_code=500, detail="Feature mismatch")

        # Predict with circuit breaker
        try:
            proba = _model.predict_proba(features)
            confidence = float(max(proba[0]))
            direction_int = int(np.argmax(proba[0]))
            direction = "long" if direction_int == 1 else "short"
        except Exception as e:
            logger.exception("prediction.error", error=str(e))
            # Circuit breaker: return flat on prediction failure
            return SignalResponse(
                direction="flat",
                confidence=0.0,
                sl_distance=0.0,
                entry_price=req.bars[-1].close if req.bars else 0.0,
                spread=round(req.ask - req.bid, 5),
                timestamp=datetime.now(UTC).isoformat(),
                model_features=len(_feature_names),
                model_version=_model_version,
            )

        spread = req.ask - req.bid
        entry_price = req.ask if direction_int == 1 else req.bid
        sl_distance = B2_STOP_DOLLARS

        # Session filter: only trade 08:00-17:00 UTC
        if req.hour_utc < 8 or req.hour_utc >= 17:
            direction = "flat"
            confidence = 0.0

        return SignalResponse(
            direction=direction,
            confidence=round(confidence, 4),
            sl_distance=sl_distance,
            entry_price=round(entry_price, 5),
            spread=round(spread, 5),
            timestamp=datetime.now(UTC).isoformat(),
            model_features=len(_feature_names),
            model_version=_model_version,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("signal.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade")
async def log_trade(req: TradeRequest, _key: str = Security(verify_signal_api_key)):
    """Log trade execution. EA calls this after placing a trade."""
    # Validate trade data
    if req.entry_price <= 0:
        raise HTTPException(status_code=400, detail=f"Invalid entry_price: {req.entry_price}")
    if req.sl <= 0 or req.tp <= 0:
        raise HTTPException(status_code=400, detail=f"Invalid SL/TP: sl={req.sl}, tp={req.tp}")
    if req.lot_size <= 0:
        raise HTTPException(status_code=400, detail=f"Invalid lot_size: {req.lot_size}")

    log_path = LOG_DIR / "ea_trades.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(req.model_dump()) + "\n")
    return {"status": "logged", "ticket": req.ticket}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8752, log_level="info")
