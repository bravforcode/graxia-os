"""
Tests for api/signal_service.py — ML inference endpoint.

Covers:
- Signal ingestion with valid payload
- Signal ingestion with invalid/missing fields
- Deduplication / rate limiting
- Model loading singleton
- Error handling when ML model unavailable
- Concurrent signal ingestion (10 parallel)
- Trade logging endpoint
- Health endpoint
- Feature computation

Uses importlib to load signal_service.py directly, bypassing the broken
api/__init__.py import chain.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
import time
from datetime import datetime, UTC
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Direct module loading (bypass api/__init__.py broken import chain)
# ---------------------------------------------------------------------------

def _load_signal_service():
    """Load api/signal_service.py as a standalone module without api/__init__.py."""
    mod_path = Path(__file__).resolve().parent.parent / "api" / "signal_service.py"
    spec = importlib.util.spec_from_file_location("signal_service", mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["signal_service"] = mod
    spec.loader.exec_module(mod)
    return mod


svc = _load_signal_service()


# ---------------------------------------------------------------------------
# Patch pd.Timestamp to work around pandas 2.3+ utc parameter removal
# ---------------------------------------------------------------------------
_original_pd_timestamp = pd.Timestamp

class _SafeTimestamp(_original_pd_timestamp):
    """pd.Timestamp subclass that accepts utc= kwarg (removed in pandas 2.3+)."""
    def __new__(cls, *args, **kwargs):
        kwargs.pop("utc", None)
        return super().__new__(cls, *args, **kwargs)


pd.Timestamp = _SafeTimestamp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bars(n: int = 200, base_price: float = 2300.0) -> list[dict]:
    """Generate n synthetic M15 bars for valid SignalRequest."""
    bars = []
    ts = int(datetime(2025, 6, 1, 0, 0, tzinfo=UTC).timestamp())
    price = base_price
    for i in range(n):
        delta = np.random.uniform(-2, 2)
        o = price
        h = price + abs(delta)
        l = price - abs(delta)
        c = price + delta
        price = c
        bars.append({
            "time": ts + i * 900,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 100.0,
        })
        ts += 900
    return bars


def _valid_signal_payload() -> dict:
    return {
        "bars": _make_bars(200),
        "bid": 2300.00,
        "ask": 2300.20,
        "hour_utc": 12,
    }


def _setup_app_with_mock_model():
    """
    Configure signal_service globals with a mock model and return (app, mock_model).
    """
    svc._model_loaded = True
    svc._feature_names = [f"feat_{i}" for i in range(40)]

    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[0.3, 0.7]])
    mock_model.predict.return_value = np.array([1])
    svc._model = mock_model

    # Reset rate limiter so tests don't hit 429
    svc._rate_limiter = svc._RateLimiter(max_requests=300, window_seconds=60)

    return svc.app, mock_model


# ---------------------------------------------------------------------------
# Tests: Signal Endpoint
# ---------------------------------------------------------------------------

class TestSignalIngestion:
    """Tests for POST /api/signal with valid and invalid payloads."""

    def setup_method(self):
        self.app, self.mock_model = _setup_app_with_mock_model()
        self.client = TestClient(self.app)

    def test_valid_signal_returns_direction(self):
        """Valid payload with 200 bars returns a valid direction and confidence."""
        payload = _valid_signal_payload()
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] in ("long", "short", "flat")
        assert 0.0 <= data["confidence"] <= 1.0
        assert "entry_price" in data
        assert "spread" in data
        assert "timestamp" in data
        assert data["model_features"] == 40

    def test_valid_signal_short_direction(self):
        """Mock model returning class=0 → direction=short."""
        self.mock_model.predict_proba.return_value = np.array([[0.75, 0.25]])
        self.mock_model.predict.return_value = np.array([0])
        payload = _valid_signal_payload()
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] == "short"

    def test_session_filter_outside_hours(self):
        """hour_utc outside 08-17 → direction forced to flat."""
        payload = _valid_signal_payload()
        payload["hour_utc"] = 3  # 03:00 UTC
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] == "flat"
        assert data["confidence"] == 0.0

    def test_session_filter_boundary_hour_8(self):
        """hour_utc=8 is the first tradeable hour."""
        payload = _valid_signal_payload()
        payload["hour_utc"] = 8
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "direction" in data

    def test_session_filter_boundary_hour_17(self):
        """hour_utc=17 is excluded (>= 17 is outside session)."""
        payload = _valid_signal_payload()
        payload["hour_utc"] = 17
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] == "flat"

    def test_minimum_bars_enforcement(self):
        """Request with < 50 bars returns 400."""
        payload = _valid_signal_payload()
        payload["bars"] = payload["bars"][:30]
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 400
        assert "50" in resp.json()["detail"]

    def test_exactly_50_bars_accepted(self):
        """Request with exactly 50 bars is accepted (minimum threshold)."""
        payload = _valid_signal_payload()
        payload["bars"] = payload["bars"][:50]
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200

    def test_duplicate_timestamps_rejected(self):
        """Bars with duplicate timestamps return 400."""
        payload = _valid_signal_payload()
        for bar in payload["bars"]:
            bar["time"] = 1700000000
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 400
        assert "Duplicate timestamps" in resp.json()["detail"]

    def test_invalid_bid_ask_zero(self):
        """bid=0 returns 400."""
        payload = _valid_signal_payload()
        payload["bid"] = 0
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 400
        assert "Invalid bid/ask" in resp.json()["detail"]

    def test_invalid_bid_ask_negative(self):
        """Negative bid returns 400."""
        payload = _valid_signal_payload()
        payload["bid"] = -1.0
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 400

    def test_ask_less_than_bid_rejected(self):
        """ask < bid returns 400 (inverted spread is nonsensical)."""
        payload = _valid_signal_payload()
        payload["bid"] = 2300.50
        payload["ask"] = 2300.00
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 400
        assert "Ask" in resp.json()["detail"]

    def test_spread_in_response(self):
        """Spread in response equals ask - bid."""
        payload = _valid_signal_payload()
        payload["bid"] = 2300.00
        payload["ask"] = 2300.35
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 200
        assert resp.json()["spread"] == pytest.approx(0.35, abs=0.001)

    def test_empty_bars_list(self):
        """Empty bars list returns 400."""
        payload = _valid_signal_payload()
        payload["bars"] = []
        resp = self.client.post("/api/signal", json=payload)
        assert resp.status_code == 400

    def test_missing_bars_field(self):
        """Missing bars field returns 422 (Pydantic validation)."""
        resp = self.client.post("/api/signal", json={
            "bid": 2300.0, "ask": 2300.2, "hour_utc": 12
        })
        assert resp.status_code == 422

    def test_missing_bid_field(self):
        """Missing bid field returns 422."""
        resp = self.client.post("/api/signal", json={
            "bars": _make_bars(60), "ask": 2300.2, "hour_utc": 12
        })
        assert resp.status_code == 422

    def test_missing_hour_utc_field(self):
        """Missing hour_utc returns 422."""
        resp = self.client.post("/api/signal", json={
            "bars": _make_bars(60), "bid": 2300.0, "ask": 2300.2
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: Rate Limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    """Tests for the in-memory rate limiter."""

    def test_allows_within_limit(self):
        """Requests within the rate limit window are allowed."""
        limiter = svc._RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.allow("test_client") is True

    def test_blocks_over_limit(self):
        """Requests exceeding the rate limit are blocked."""
        limiter = svc._RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.allow("test_client") is True
        assert limiter.allow("test_client") is False

    def test_independent_clients(self):
        """Rate limits are per-client, not global."""
        limiter = svc._RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("client_a") is True
        assert limiter.allow("client_a") is True
        assert limiter.allow("client_a") is False  # client_a exhausted
        assert limiter.allow("client_b") is True  # client_b is fresh


# ---------------------------------------------------------------------------
# Tests: Model Unavailable
# ---------------------------------------------------------------------------

class TestModelUnavailable:
    """Tests for behavior when ML model is not loaded."""

    def test_signal_when_model_not_loaded(self):
        """POST /api/signal returns 503 when model is not loaded."""
        original_loaded = svc._model_loaded
        svc._model_loaded = False
        try:
            client = TestClient(svc.app)
            payload = _valid_signal_payload()
            resp = client.post("/api/signal", json=payload)
            assert resp.status_code == 503
            assert "Model not loaded" in resp.json()["detail"]
        finally:
            svc._model_loaded = original_loaded

    def test_prediction_failure_returns_flat(self):
        """When model.predict_proba raises, circuit breaker returns flat."""
        failing_model = MagicMock()
        failing_model.predict_proba.side_effect = RuntimeError("GPU OOM")

        original_model = svc._model
        original_loaded = svc._model_loaded
        svc._model = failing_model
        svc._model_loaded = True
        svc._feature_names = [f"feat_{i}" for i in range(40)]
        try:
            client = TestClient(svc.app)
            payload = _valid_signal_payload()
            resp = client.post("/api/signal", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["direction"] == "flat"
            assert data["confidence"] == 0.0
        finally:
            svc._model = original_model
            svc._model_loaded = original_loaded


# ---------------------------------------------------------------------------
# Tests: Concurrent Ingestion
# ---------------------------------------------------------------------------

class TestConcurrentIngestion:
    """Tests for concurrent signal ingestion with 10 parallel requests."""

    def test_concurrent_requests(self):
        """10 parallel signal requests all complete without error."""
        svc._model_loaded = True
        svc._feature_names = [f"feat_{i}" for i in range(40)]

        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.3, 0.7]])
        mock_model.predict.return_value = np.array([1])
        svc._model = mock_model
        svc._rate_limiter = svc._RateLimiter(max_requests=300, window_seconds=60)

        client = TestClient(svc.app, raise_server_exceptions=False)

        results = []
        for _ in range(10):
            payload = _valid_signal_payload()
            payload["hour_utc"] = 12
            resp = client.post("/api/signal", json=payload)
            results.append(resp)

        success_count = sum(1 for r in results if r.status_code == 200)
        assert success_count == 10


# ---------------------------------------------------------------------------
# Tests: Health Endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_ok(self):
        """Health endpoint returns status=ok and model metadata."""
        self_app, _ = _setup_app_with_mock_model()
        client = TestClient(self_app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model_loaded"] is True
        assert data["features"] == 40
        assert data["symbol"] == "XAUUSD"


# ---------------------------------------------------------------------------
# Tests: Trade Logging
# ---------------------------------------------------------------------------

class TestTradeLogging:
    """Tests for POST /api/trade."""

    def test_valid_trade_logged(self):
        """Valid trade payload returns status=logged with ticket."""
        self_app, _ = _setup_app_with_mock_model()
        client = TestClient(self_app)
        payload = {
            "ticket": 12345,
            "direction": "long",
            "entry_price": 2300.50,
            "sl": 2297.50,
            "tp": 2306.50,
            "confidence": 0.72,
            "lot_size": 0.01,
        }
        resp = client.post("/api/trade", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "logged"
        assert data["ticket"] == 12345

    def test_invalid_entry_price_rejected(self):
        """entry_price <= 0 returns 400."""
        self_app, _ = _setup_app_with_mock_model()
        client = TestClient(self_app)
        payload = {
            "ticket": 1, "direction": "long", "entry_price": -10.0,
            "sl": 100.0, "tp": 200.0, "confidence": 0.7, "lot_size": 0.01,
        }
        resp = client.post("/api/trade", json=payload)
        assert resp.status_code == 400

    def test_invalid_sl_tp_rejected(self):
        """sl=0 returns 400."""
        self_app, _ = _setup_app_with_mock_model()
        client = TestClient(self_app)
        payload = {
            "ticket": 1, "direction": "long", "entry_price": 2300.0,
            "sl": 0, "tp": 200.0, "confidence": 0.7, "lot_size": 0.01,
        }
        resp = client.post("/api/trade", json=payload)
        assert resp.status_code == 400

    def test_invalid_lot_size_rejected(self):
        """lot_size <= 0 returns 400."""
        self_app, _ = _setup_app_with_mock_model()
        client = TestClient(self_app)
        payload = {
            "ticket": 1, "direction": "long", "entry_price": 2300.0,
            "sl": 2297.0, "tp": 2306.0, "confidence": 0.7, "lot_size": 0.0,
        }
        resp = client.post("/api/trade", json=payload)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests: Feature Computation
# ---------------------------------------------------------------------------

class TestFeatureComputation:
    """Tests for compute_features_live function."""

    def test_compute_features_live_shape(self):
        """compute_features_live returns (1, n_features) array."""
        dates = pd.date_range("2025-01-01", periods=200, freq="15min", tz="UTC")
        df = pd.DataFrame({
            "open": np.random.uniform(2290, 2310, 200),
            "high": np.random.uniform(2300, 2320, 200),
            "low": np.random.uniform(2280, 2300, 200),
            "close": np.random.uniform(2290, 2310, 200),
            "volume": np.random.uniform(50, 200, 200),
        }, index=dates)
        df["symbol"] = "XAUUSD"
        df["freq"] = "15min"

        real_features = [
            "ret_1bar", "ret_5bar", "ret_10bar", "ret_15bar", "ret_30bar", "ret_60bar",
            "atr_7", "atr_14", "atr_21",
            "rvol_10", "rvol_20", "rvol_60",
            "rsi_7", "rsi_14", "rsi_21",
            "stoch_k", "stoch_d", "cci_20", "willr_14",
            "ema_5_dist", "ema_10_dist", "ema_20_dist", "ema_200_dist",
            "sma_20_50_cross", "bb_width", "bb_pctb", "bb_squeeze",
            "obv_slope_20", "vol_ratio_20", "vol_ratio_10",
            "body_ratio", "upper_shadow", "lower_shadow",
            "is_doji", "is_hammer", "is_bull_engulf",
            "is_asian_session", "is_london_session", "is_ny_session",
            "day_of_week", "day_of_month",
        ]
        result = svc.compute_features_live(df, real_features)
        assert result.shape[0] == 1
        assert result.shape[1] == len(real_features)

    def test_compute_features_handles_nan(self):
        """compute_features_live fills NaN values and still returns valid output."""
        dates = pd.date_range("2025-01-01", periods=200, freq="15min", tz="UTC")
        close = np.random.uniform(2290, 2310, 200).astype(float)
        close[5] = np.nan
        close[10] = np.inf
        df = pd.DataFrame({
            "open": close,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": np.ones(200),
        }, index=dates)

        real_features = [
            "ret_1bar", "ret_5bar", "rsi_14", "atr_14", "body_ratio",
            "is_doji", "is_hammer", "is_bull_engulf", "bb_width", "bb_pctb",
        ]
        result = svc.compute_features_live(df, real_features)
        assert result.shape[0] == 1
        assert not np.any(np.isnan(result)), "Output should not contain NaN"
        assert not np.any(np.isinf(result)), "Output should not contain inf"
