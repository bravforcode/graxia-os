"""
GRAXIA Signal Service — lightweight FastAPI for MQL5 EA.

EA sends OHLCV bars via POST /api/signal, service computes features + XGBoost prediction.
Returns JSON: { direction, confidence, sl_distance, entry_price, spread }.

No MT5 dependency — all bar data comes from the EA.
"""

from __future__ import annotations

import hmac
import json
import os
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

from graxia.packages.quant_os.core.safe_pickle import safe_load_model, sign_model_file
from graxia.packages.quant_os.ml.feature_store import (
    LIVE_FEATURE_COLUMNS,
    compute_feature_list_hash,
)
from graxia.packages.quant_os.ml.feature_store import (
    compute_live_features as compute_features_live,
)
from graxia.packages.quant_os.ml.model_registry import ModelRegistry
from graxia.packages.quant_os.risk.circuit_breaker import DEFAULT_STATE_FILE

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

SYMBOL = os.getenv("TRADE_SYMBOL", "XAUUSD")
LOT_SIZE = float(os.getenv("LOT_SIZE", "0.01"))
B2_STOP_DOLLARS = float(os.getenv("B2_STOP", "3.00"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.50"))
# Shared circuit-breaker state file — mirrors KillSwitch's CWD-relative
# data/kill_switch_state.json. Every process that constructs a
# CircuitBreaker must use the same path so a trip in one process is
# honored by the others (risk gate, orchestrator, webhook).
CIRCUIT_BREAKER_STATE_FILE = DEFAULT_STATE_FILE
MODEL_SIGNING_KEY = os.getenv("MODEL_SIGNING_KEY", "")
# Path resolution: env-var-driven with defaults relative to this file's package.
# Works both in Docker (/app mounts) and local dev (relative to repo root).
_THIS_DIR = Path(__file__).resolve().parent  # api/
_PACKAGE_DIR = _THIS_DIR.parent  # quant_os/
LOG_DIR = Path(os.getenv("LOG_DIR", str(_PACKAGE_DIR / "data")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

_model = None
_feature_names: list[str] = []
_model_loaded = False
_model_version: str = ""
_expected_feature_hash: str = ""  # feature_list_hash from ModelRegistry, "" = unregistered (check skipped)
_model_lock = threading.Lock()

# Directories scanned for model artifacts. Env-var-driven, relative to
# _PACKAGE_DIR by default — works both in Docker (mount an env var override)
# and local dev. (Phase 2B.3 fixed LOG_DIR/FEATURES_DIR/MODEL_SAVE_DIR to this
# pattern but missed this one — STRATEGY_MODEL_DIR was still hardcoded /app/.)
STRATEGY_MODEL_DIR = Path(os.getenv("STRATEGY_MODEL_DIR", str(_PACKAGE_DIR / "artifacts" / "strategy_model")))
MODEL_SAVE_DIR = Path(os.getenv("MODEL_SAVE_DIR", str(_PACKAGE_DIR / "ml" / "models")))


def _load_model():
    global _model, _feature_names, _model_loaded, _model_version, _expected_feature_hash
    if _model_loaded:
        return

    with _model_lock:
        if _model_loaded:
            return

        model_dirs = [STRATEGY_MODEL_DIR, MODEL_SAVE_DIR]

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
                    raw = safe_load_model(path, signing_key=MODEL_SIGNING_KEY or None)
                except Exception as e:
                    logger.warning("model.load_error", path=str(path), error=str(e))
                    continue

                # Look up this artifact in the ModelRegistry (keyed by version_id ==
                # filename stem, since ModelRegistry.register_model() names its
                # artifact "{version_id}.pkl"). This is the ONLY place the live
                # feature_list_hash contract gets populated for enforcement in
                # get_signal() below — an independent lookup, not a self-hash of
                # the same pickle, so it actually catches drift/wrong-model loads.
                meta = None
                try:
                    meta = ModelRegistry(models_dir=d).get_model(path.stem)
                except Exception as e:
                    logger.warning("model_registry.lookup_failed", path=str(path), error=str(e))

                if isinstance(raw, dict) and "model" in raw:
                    candidate_model = raw["model"]
                    candidate_features = raw.get("feature_names", [])
                elif meta is not None:
                    # Registry-saved artifacts are the raw model object (registry
                    # pickles `model` directly, not a {"model":...} wrapper) —
                    # the feature list comes from the registry metadata instead.
                    candidate_model = raw
                    candidate_features = meta.feature_list
                else:
                    logger.info("model.loaded_unrecognized_format", path=str(path))
                    continue

                if candidate_features:
                    _model = candidate_model
                    _feature_names = candidate_features
                    _model_version = meta.version_id if meta is not None else path.stem
                    _expected_feature_hash = meta.feature_list_hash if meta is not None else ""
                    if not _expected_feature_hash:
                        logger.warning(
                            "model.unregistered_no_hash_check",
                            path=str(path),
                            reason="model not found in ModelRegistry — feature contract check skipped",
                        )
                    logger.info("model.loaded", path=str(path), features=len(_feature_names))
                    _model_loaded = True
                    return
                else:
                    logger.info("model.loaded_no_features", path=str(path))
                    continue

        # No model with features found — retrain
        _retrain_model()


def _retrain_model():
    """Retrain model using ONLY the 40 features available in live pipeline."""
    global _model, _feature_names, _model_loaded, _model_version, _expected_feature_hash

    import xgboost as xgb

    features_path = (
        Path(os.getenv("FEATURES_DIR", str(_PACKAGE_DIR / "ml" / "models"))) / f"features_v2_{SYMBOL}_15min.parquet"
    )
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
    X_train = train[live_feature_cols].fillna(0).values  # noqa: N806
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

    # Save retrained model via ModelRegistry (instead of a hand-rolled pickle.dump)
    # so it carries a feature_list_hash computed by the same canonical algorithm
    # used at live-inference time (ml.feature_store.compute_feature_list_hash).
    # ModelRegistry writes "{version_id}.pkl" — _load_model() looks up this exact
    # version_id in the registry index to populate _expected_feature_hash for
    # the fail-closed check in get_signal().
    try:
        MODEL_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        registry = ModelRegistry(models_dir=MODEL_SAVE_DIR)
        metadata = registry.register_model(
            _model,
            model_name=f"xgboost_{SYMBOL}_live_features",
            model_type="xgboost",
            symbol=SYMBOL,
            timeframe="M15",
            feature_list=live_feature_cols,
            metrics={},
            training_samples=len(X_train),
        )
        save_path = Path(metadata.artifact_path)
        _model_version = metadata.version_id
        _expected_feature_hash = metadata.feature_list_hash
        logger.info("model.saved_to_disk", path=str(save_path), version_id=metadata.version_id)
        if MODEL_SIGNING_KEY:
            sign_model_file(save_path, MODEL_SIGNING_KEY)
            logger.info("model.signed", path=str(save_path))
        else:
            logger.warning("model.save_unsigned", reason="MODEL_SIGNING_KEY not set")
    except Exception as e:
        logger.warning("model.save_failed", error=str(e))
        _model_version = f"xgboost_{SYMBOL}_live_features"
        _expected_feature_hash = ""

    _model_loaded = True
    logger.info("model.retrained_live_features", features=len(live_feature_cols), samples=len(X_train))


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------
# compute_features_live is imported from ml.feature_store (as compute_live_features)
# above — it is the single feature-computation implementation shared by this
# live-inference path and _retrain_model()'s training-data column selection.
# Kept under its original name here since tests reference svc.compute_features_live
# directly.


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="GRAXIA Signal Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
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
    symbol: str = ""  # the trading symbol (e.g. XAUUSD); populated by EA


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


class RiskGateRequest(BaseModel):
    """Trade pre-approval request — EA calls this BEFORE OrderSend."""

    symbol: str
    direction: str  # MUST be "long" or "short" — validated in endpoint
    entry_price: float
    stop_loss: float
    confidence: float
    lot_size: float = 0.01


class RiskGateResponse(BaseModel):
    allowed: bool
    reason: str
    approved_quantity: float = 0.0


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

        # Fail-closed feature/model contract check — refuse to serve a prediction
        # if the CURRENT CODE's live feature vocabulary (ml.feature_store.LIVE_FEATURE_COLUMNS,
        # i.e. what compute_live_features() actually computes right now) no longer
        # matches the feature_list_hash the loaded model was registered with.
        #
        # This deliberately does NOT hash `_feature_names` here: `_feature_names`
        # is populated from the SAME registry metadata that _expected_feature_hash
        # comes from (see _load_model()), so hashing it would just re-derive
        # _expected_feature_hash from itself — a tautology that can never fail.
        # Hashing LIVE_FEATURE_COLUMNS instead makes this an independent check
        # against what the running code actually computes: if someone edits
        # LIVE_FEATURE_COLUMNS (add/remove/reorder a feature) without retraining
        # and re-registering, this check catches the drift.
        #
        # This is a HARD refusal (raised outside the predict try/except below on
        # purpose): the circuit breaker's except-Exception block returns a "flat"
        # 200 response on prediction errors, which would silently swallow a
        # contract violation instead of surfacing it. An empty _expected_feature_hash
        # means the loaded model has no ModelRegistry entry (legacy/unregistered
        # artifact) — the check is skipped and a warning was already logged at
        # model-load time.
        if _expected_feature_hash:
            live_hash = compute_feature_list_hash(LIVE_FEATURE_COLUMNS)
            if live_hash != _expected_feature_hash:
                logger.error(
                    "signal.feature_hash_mismatch",
                    live_hash=live_hash,
                    expected_hash=_expected_feature_hash,
                    model_version=_model_version,
                )
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Feature/model contract violation: live feature hash does not match "
                        f"the registered model's feature_list_hash (model_version={_model_version}). "
                        "Refusing to serve a prediction."
                    ),
                )

        # Predict with circuit breaker
        if _model is None:
            raise HTTPException(status_code=503, detail="Model not loaded")

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
        raise HTTPException(status_code=500, detail=str(e)) from e


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


@app.post("/api/risk-gate")
async def risk_gate(req: RiskGateRequest, _key: str = Security(verify_signal_api_key)):
    """
    Pre-trade risk gate — EA calls this BEFORE OrderSend.

    Wraps risk/engine.py's 4-layer gate. The EA MUST block on denial.
    This is the single safety boundary between the EA's native OrderSend()
    and the Python risk system.

    Returns ``{"allowed": bool, "reason": str}`` — EA only places order
    when ``allowed=true``.
    """
    from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
    from graxia.packages.quant_os.risk.engine import (
        AccountState,
        PortfolioState,
        RiskEngine,
        Signal,
    )
    from graxia.packages.quant_os.risk.kill_switch import KillSwitch

    # Rate limit: same window as /api/signal (max 30 requests per minute)
    if not _rate_limiter.allow(client_id="risk_gate"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 30 requests/minute.")

    # Validate direction — fail-closed, reject anything not explicitly "long" or "short"
    if req.direction not in ("long", "short"):
        return RiskGateResponse(
            allowed=False,
            reason=f"Invalid direction '{req.direction}' — must be 'long' or 'short'",
            approved_quantity=0.0,
        )

    if req.entry_price <= 0 or req.stop_loss <= 0:
        return RiskGateResponse(
            allowed=False,
            reason=f"Invalid price/sl: entry={req.entry_price}, sl={req.stop_loss}",
            approved_quantity=0.0,
        )

    if req.confidence <= 0:
        return RiskGateResponse(
            allowed=False,
            reason=f"Invalid confidence: {req.confidence}",
            approved_quantity=0.0,
        )

    risk_signal = Signal(
        symbol=req.symbol or SYMBOL,
        conviction=req.confidence,
        entry_price=req.entry_price,
        stop_loss=req.stop_loss,
        direction="BUY" if req.direction == "long" else "SELL",  # safe: validated above
        side="BUY" if req.direction == "long" else "SELL",
        timestamp=datetime.now(UTC),
        timestamp_epoch=time.time(),
        venue="paper",
    )

    engine = RiskEngine(
        kill_switch=KillSwitch(),
        circuit_breaker=CircuitBreaker(state_file=CIRCUIT_BREAKER_STATE_FILE),
    )
    account = AccountState(equity=0.0, balance=0.0)
    portfolio = PortfolioState()

    try:
        verdict = engine.evaluate(risk_signal, account, portfolio)
    except Exception as exc:
        logger.exception("risk_gate.evaluate_failed", error=str(exc))
        # Fail-closed: if the risk engine itself errors, do NOT trade
        return RiskGateResponse(
            allowed=False,
            reason=f"Risk engine error: {exc}",
            approved_quantity=0.0,
        )

    if verdict.approved:
        logger.info(
            "risk_gate.approved",
            symbol=risk_signal.symbol,
            direction=req.direction,
            confidence=req.confidence,
            approved_qty=verdict.approved_quantity,
        )
    else:
        logger.warning(
            "risk_gate.rejected",
            symbol=risk_signal.symbol,
            direction=req.direction,
            reason=verdict.reason,
            reason_code=verdict.reason_code.value if verdict.reason_code else None,
            layer=verdict.layer_failed,
        )

    return RiskGateResponse(
        allowed=verdict.approved,
        reason=verdict.reason,
        approved_quantity=verdict.approved_quantity,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8752, log_level="info")
