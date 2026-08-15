"""
Tests for the feature/model contract: ml.feature_store's canonical hash
function, ModelRegistry auto-computing feature_list_hash at registration,
and api/signal_service.py's fail-closed enforcement at live inference time.

Covers Phase 2C (feature-store unification) acceptance criteria:
- register a model with a known feature_list_hash, call live inference with
  a mismatched feature vector -> refused with a clear error, not served.
- matching-hash case -> still serves a prediction normally.
- _load_model() populates _expected_feature_hash from an INDEPENDENT
  ModelRegistry lookup (not a self-hash of the same pickle) so the guard is
  load-bearing in production, not just when a test sets the global by hand.

Uses the same direct-module-load harness as tests/test_signal_service.py to
bypass the broken api/__init__.py import chain.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

os.environ["SIGNAL_SERVICE_API_KEY"] = "test-api-key-12345"

import numpy as np
import pytest
from fastapi.testclient import TestClient

from graxia.packages.quant_os.core.safe_pickle import sign_model_file
from graxia.packages.quant_os.ml.feature_store import LIVE_FEATURE_COLUMNS, compute_feature_list_hash
from graxia.packages.quant_os.ml.model_registry import ModelRegistry


def _load_signal_service():
    """Load api/signal_service.py as a standalone module without api/__init__.py."""
    mod_path = Path(__file__).resolve().parent.parent / "api" / "signal_service.py"
    spec = importlib.util.spec_from_file_location("signal_service_contract", mod_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["signal_service_contract"] = mod
    spec.loader.exec_module(mod)
    return mod


svc = _load_signal_service()

# Patch pd.Timestamp to work around pandas 2.3+ utc parameter removal — same
# workaround as tests/test_signal_service.py (signal_service.py's get_signal()
# constructs pd.Timestamp(b.time, unit="s", utc=True)).
import pandas as pd  # noqa: E402

_original_pd_timestamp = pd.Timestamp


class _SafeTimestamp(_original_pd_timestamp):
    def __new__(cls, *args, **kwargs):
        kwargs.pop("utc", None)
        return super().__new__(cls, *args, **kwargs)


@pytest.fixture(scope="module", autouse=True)
def _patch_pd_timestamp():
    """Replace pd.Timestamp with utc-tolerant wrapper for this module only.

    Uses a fixture so the monkeypatch is scoped to this module's tests and
    does not leak into other test files (fixes module-level pd.Timestamp = assignment).
    """
    original = pd.Timestamp
    pd.Timestamp = _SafeTimestamp
    yield
    pd.Timestamp = original


_API_KEY = "test-api-key-12345"


class _AuthClient:
    def __init__(self, app):
        self._client = TestClient(app, raise_server_exceptions=False)

    def post(self, url, **kwargs):
        headers = kwargs.pop("headers", None) or {}
        headers["X-API-Key"] = _API_KEY
        return self._client.post(url, headers=headers, **kwargs)


def _make_bars(n: int = 200, base_price: float = 2300.0) -> list[dict]:
    from datetime import UTC, datetime

    bars = []
    ts = int(datetime(2025, 6, 1, 0, 0, tzinfo=UTC).timestamp())
    price = base_price
    rng = np.random.RandomState(7)
    for i in range(n):
        delta = rng.uniform(-2, 2)
        o = price
        h = price + abs(delta)
        l = price - abs(delta)
        c = price + delta
        price = c
        bars.append(
            {
                "time": ts + i * 900,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": 100.0,
            }
        )
        ts += 900
    return bars


def _valid_signal_payload() -> dict:
    return {"bars": _make_bars(200), "bid": 2300.00, "ask": 2300.20, "hour_utc": 12}


def _setup_app_with_mock_model(n_features: int = 40):
    """Configure signal_service globals with a mock model; return (app, mock_model)."""
    svc._model_loaded = True
    svc._feature_names = [f"feat_{i}" for i in range(n_features)]
    svc._expected_feature_hash = ""  # reset — each test sets explicitly
    svc._model_version = "test_version"

    mock_model = MagicMock()
    mock_model.predict_proba.return_value = np.array([[0.3, 0.7]])
    mock_model.predict.return_value = np.array([1])
    svc._model = mock_model
    svc._rate_limiter = svc._RateLimiter(max_requests=300, window_seconds=60)
    return svc.app, mock_model


# ---------------------------------------------------------------------------
# compute_feature_list_hash — the canonical hash function itself
# ---------------------------------------------------------------------------


class TestComputeFeatureListHash:
    def test_deterministic(self):
        names = ["ret_1bar", "atr_14", "rsi_14"]
        assert compute_feature_list_hash(names) == compute_feature_list_hash(list(names))

    def test_order_sensitive(self):
        """Reordering the same names must change the hash — column order matters."""
        h1 = compute_feature_list_hash(["a", "b", "c"])
        h2 = compute_feature_list_hash(["c", "b", "a"])
        assert h1 != h2

    def test_different_names_different_hash(self):
        assert compute_feature_list_hash(["a", "b"]) != compute_feature_list_hash(["a", "c"])


# ---------------------------------------------------------------------------
# ModelRegistry auto-computes feature_list_hash at registration
# ---------------------------------------------------------------------------


class TestModelRegistryAutoHash:
    def test_register_model_autocomputes_hash(self, tmp_path):
        registry = ModelRegistry(models_dir=tmp_path)
        feature_list = ["ret_1bar", "atr_14", "rsi_14"]
        meta = registry.register_model(
            {"dummy": "model-stand-in"},
            model_name="unit_test_model",
            model_type="xgboost",
            symbol="XAUUSD",
            timeframe="M15",
            feature_list=feature_list,
            metrics={},
            training_samples=10,
        )
        assert meta.feature_list_hash == compute_feature_list_hash(feature_list)
        assert meta.feature_list_hash != ""

    def test_explicit_hash_respected(self, tmp_path):
        """An explicitly-passed hash is not overwritten (backward compat)."""
        registry = ModelRegistry(models_dir=tmp_path)
        meta = registry.register_model(
            {"dummy": "model"},
            model_name="explicit_hash_model",
            model_type="xgboost",
            symbol="XAUUSD",
            timeframe="M15",
            feature_list=["a", "b"],
            metrics={},
            training_samples=10,
            feature_list_hash="not-a-real-hash",
        )
        assert meta.feature_list_hash == "not-a-real-hash"


# ---------------------------------------------------------------------------
# _load_model() populates _expected_feature_hash from an INDEPENDENT registry
# lookup (proves the guard is wired for production, not just test-settable)
# ---------------------------------------------------------------------------


class TestLoadModelPopulatesExpectedHash:
    def test_load_model_reads_hash_from_registry(self, tmp_path, monkeypatch):
        from sklearn.ensemble import RandomForestClassifier

        registry = ModelRegistry(models_dir=tmp_path)
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        X = np.random.RandomState(0).randn(30, 3)
        y = np.random.RandomState(0).randint(0, 2, 30)
        model.fit(X, y)

        feature_list = ["fa", "fb", "fc"]
        meta = registry.register_model(
            model,
            model_name="xgboost_CONTRACTTEST_live_features",
            model_type="xgboost",
            symbol="CONTRACTTEST",
            timeframe="M15",
            feature_list=feature_list,
            metrics={},
            training_samples=30,
        )

        signing_key = "test-signing-key"
        sign_model_file(Path(meta.artifact_path), signing_key)

        monkeypatch.setattr(svc, "STRATEGY_MODEL_DIR", tmp_path / "does_not_exist")
        monkeypatch.setattr(svc, "MODEL_SAVE_DIR", tmp_path)
        monkeypatch.setattr(svc, "SYMBOL", "CONTRACTTEST")
        monkeypatch.setattr(svc, "MODEL_SIGNING_KEY", signing_key)
        monkeypatch.setattr(svc, "_model_loaded", False)
        monkeypatch.setattr(svc, "_expected_feature_hash", "")

        svc._load_model()

        assert svc._model_loaded is True
        assert svc._feature_names == feature_list
        # The key assertion: the hash was populated from an INDEPENDENT
        # ModelRegistry lookup keyed by version_id == filename stem, not
        # copied from the pickle's own feature_names (which would be tautological).
        assert svc._expected_feature_hash == meta.feature_list_hash
        assert svc._expected_feature_hash == compute_feature_list_hash(feature_list)
        assert svc._expected_feature_hash != ""

    def test_load_model_unregistered_artifact_skips_check(self, tmp_path, monkeypatch):
        """A legacy dict-pickle with no ModelRegistry entry loads with hash-check skipped."""
        import pickle

        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression()
        X = np.random.RandomState(1).randn(20, 2)
        y = np.random.RandomState(1).randint(0, 2, 20)
        model.fit(X, y)

        path = tmp_path / "xgboost_LEGACYTEST_unregistered.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": model, "feature_names": ["x1", "x2"], "model_type": "xgboost", "version": "v1"}, f)
        # Real sklearn objects require a valid HMAC signature to pass
        # safe_pickle's TrustedUnpickler allowlist — sign it (this is orthogonal
        # to the ModelRegistry lookup being tested here: no registry_index.json
        # entry exists for this filename, so the hash-check should still be skipped).
        signing_key = "legacy-test-key"
        sign_model_file(path, signing_key)

        monkeypatch.setattr(svc, "STRATEGY_MODEL_DIR", tmp_path / "does_not_exist")
        monkeypatch.setattr(svc, "MODEL_SAVE_DIR", tmp_path)
        monkeypatch.setattr(svc, "SYMBOL", "LEGACYTEST")
        monkeypatch.setattr(svc, "MODEL_SIGNING_KEY", signing_key)
        monkeypatch.setattr(svc, "_model_loaded", False)
        monkeypatch.setattr(svc, "_expected_feature_hash", "sentinel")

        svc._load_model()

        assert svc._model_loaded is True
        assert svc._feature_names == ["x1", "x2"]
        assert svc._expected_feature_hash == ""  # no registry entry -> check skipped


# ---------------------------------------------------------------------------
# Fail-closed enforcement at /api/signal — the acceptance-criteria tests
# ---------------------------------------------------------------------------


class TestFeatureHashEnforcement:
    def test_matching_hash_serves_prediction_normally(self):
        """Registered model's hash matches the CURRENT CODE's live vocabulary -> 200, real prediction.

        NOTE: the expected hash must be derived from ml.feature_store.LIVE_FEATURE_COLUMNS
        (what compute_live_features() actually computes right now), not from
        svc._feature_names — those two are deliberately different sources; see
        TestFeatureHashEnforcement's module docstring / signal_service.py's
        get_signal() comment for why hashing _feature_names would be tautological.
        """
        app, mock_model = _setup_app_with_mock_model()
        svc._expected_feature_hash = compute_feature_list_hash(LIVE_FEATURE_COLUMNS)

        client = _AuthClient(app)
        resp = client.post("/api/signal", json=_valid_signal_payload())

        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] in ("long", "short", "flat")
        assert mock_model.predict_proba.call_count == 1

    def test_mismatched_hash_refuses_prediction(self):
        """Live feature hash != registered model's hash -> hard refusal, not served."""
        app, mock_model = _setup_app_with_mock_model()
        svc._expected_feature_hash = "0" * 64  # cannot match any real feature-list hash

        client = _AuthClient(app)
        resp = client.post("/api/signal", json=_valid_signal_payload())

        assert resp.status_code == 500
        detail = resp.json()["detail"].lower()
        assert "contract" in detail or "feature" in detail
        # The refusal must happen BEFORE predict_proba is called — not a
        # circuit-breaker "flat" response that happens to also return non-200.
        assert mock_model.predict_proba.call_count == 0

    def test_mismatch_is_not_swallowed_as_flat_circuit_breaker(self):
        """A mismatch must not present as the prediction-failure 'flat' 200 response."""
        app, mock_model = _setup_app_with_mock_model()
        svc._expected_feature_hash = "0" * 64

        client = _AuthClient(app)
        resp = client.post("/api/signal", json=_valid_signal_payload())

        assert resp.status_code != 200
        if resp.status_code == 200:
            assert resp.json().get("direction") != "flat"

    def test_empty_expected_hash_skips_check_backward_compat(self):
        """No registry entry (unregistered/legacy model) -> check skipped, still serves."""
        app, mock_model = _setup_app_with_mock_model()
        svc._expected_feature_hash = ""

        client = _AuthClient(app)
        resp = client.post("/api/signal", json=_valid_signal_payload())

        assert resp.status_code == 200
        assert mock_model.predict_proba.call_count == 1


# ---------------------------------------------------------------------------
# Organic drift: the REAL proof — no manual _expected_feature_hash poking.
# Registers a model through ModelRegistry, loads it through the real
# _load_model() path, and hits the real /api/signal endpoint. Simulates
# "the live feature-computation code's vocabulary changed since this model
# was registered" by registering with a feature_list that differs from the
# CURRENT ml.feature_store.LIVE_FEATURE_COLUMNS.
# ---------------------------------------------------------------------------


class TestOrganicFeatureDrift:
    def _register_and_load(self, tmp_path, monkeypatch, feature_list, symbol):
        from sklearn.ensemble import RandomForestClassifier

        registry = ModelRegistry(models_dir=tmp_path)
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        n = len(feature_list)
        X = np.random.RandomState(0).randn(40, n)
        y = np.random.RandomState(0).randint(0, 2, 40)
        model.fit(X, y)

        meta = registry.register_model(
            model,
            model_name=f"xgboost_{symbol}_live_features",
            model_type="xgboost",
            symbol=symbol,
            timeframe="M15",
            feature_list=feature_list,
            metrics={},
            training_samples=40,
        )
        signing_key = "organic-drift-test-key"
        sign_model_file(Path(meta.artifact_path), signing_key)

        monkeypatch.setattr(svc, "STRATEGY_MODEL_DIR", tmp_path / "does_not_exist")
        monkeypatch.setattr(svc, "MODEL_SAVE_DIR", tmp_path)
        monkeypatch.setattr(svc, "SYMBOL", symbol)
        monkeypatch.setattr(svc, "MODEL_SIGNING_KEY", signing_key)
        monkeypatch.setattr(svc, "_model_loaded", False)
        monkeypatch.setattr(svc, "_expected_feature_hash", "")
        svc._rate_limiter = svc._RateLimiter(max_requests=300, window_seconds=60)

        svc._load_model()  # REAL population path — no manual hash poke anywhere here
        return meta

    def test_model_trained_on_current_vocabulary_serves_normally(self, tmp_path, monkeypatch):
        """No drift: registered feature_list == today's LIVE_FEATURE_COLUMNS -> 200."""
        meta = self._register_and_load(tmp_path, monkeypatch, list(LIVE_FEATURE_COLUMNS), "NODRIFT")

        assert svc._model_loaded is True
        assert svc._expected_feature_hash == meta.feature_list_hash
        assert svc._expected_feature_hash == compute_feature_list_hash(LIVE_FEATURE_COLUMNS)

        client = _AuthClient(svc.app)
        resp = client.post("/api/signal", json=_valid_signal_payload())
        assert resp.status_code == 200

    def test_model_trained_on_stale_vocabulary_is_refused(self, tmp_path, monkeypatch):
        """Drift: model registered BEFORE a feature was dropped from
        LIVE_FEATURE_COLUMNS (simulating a code change with no retrain) ->
        refused. Uses the REAL _load_model() population path end-to-end —
        this is the organic-drift proof the sentinel-based tests above don't
        provide."""
        drifted_feature_list = list(LIVE_FEATURE_COLUMNS)[:-1]  # missing the last canonical feature
        meta = self._register_and_load(tmp_path, monkeypatch, drifted_feature_list, "DRIFTED")

        assert svc._model_loaded is True
        # Sanity: population from the registry worked, and this genuinely is a
        # different hash than what today's code would compute — not a manual poke.
        assert svc._expected_feature_hash == meta.feature_list_hash
        assert svc._expected_feature_hash != compute_feature_list_hash(LIVE_FEATURE_COLUMNS)

        client = _AuthClient(svc.app)
        resp = client.post("/api/signal", json=_valid_signal_payload())

        assert resp.status_code == 500
        detail = resp.json()["detail"].lower()
        assert "contract" in detail or "feature" in detail


# ---------------------------------------------------------------------------
# MLTrainer's optional `registry` param actually registers, with a correct hash
# ---------------------------------------------------------------------------


class TestMLTrainerRegistryIntegration:
    def test_train_with_registry_registers_model_with_correct_hash(self, tmp_path):
        from graxia.packages.quant_os.ml.pipeline import FeatureSet, MLTrainer

        rng = np.random.RandomState(0)
        n = 300
        feature_names = ["f1", "f2", "f3"]
        features = [{name: float(rng.randn()) for name in feature_names} for _ in range(n)]
        labels = [int(rng.randint(0, 2)) for _ in range(n)]
        timestamps = [None] * n

        feature_set = FeatureSet(
            features=features,
            labels=labels,
            timestamps=timestamps,
            feature_names=feature_names,
            symbol="TESTSYM",
            timeframe="M15",
        )

        registry = ModelRegistry(models_dir=tmp_path)
        trainer = MLTrainer(model_dir=str(tmp_path / "raw_pickles"))
        result = trainer.train(feature_set, model_type="xgboost", test_ratio=0.2, registry=registry)

        assert result.is_trained is True

        registered = registry.list_models(symbol="TESTSYM")
        assert len(registered) == 1
        meta = registered[0]
        assert meta.feature_list == feature_names
        assert meta.feature_list_hash == compute_feature_list_hash(feature_names)
        assert meta.feature_list_hash != ""

    def test_train_without_registry_is_unchanged(self, tmp_path):
        """registry=None (the default) must not change existing behavior."""
        from graxia.packages.quant_os.ml.pipeline import FeatureSet, MLTrainer

        rng = np.random.RandomState(1)
        n = 300
        feature_names = ["f1", "f2"]
        features = [{name: float(rng.randn()) for name in feature_names} for _ in range(n)]
        labels = [int(rng.randint(0, 2)) for _ in range(n)]

        feature_set = FeatureSet(
            features=features,
            labels=labels,
            timestamps=[None] * n,
            feature_names=feature_names,
        )

        trainer = MLTrainer(model_dir=str(tmp_path))
        result = trainer.train(feature_set, model_type="xgboost", test_ratio=0.2)
        assert result.is_trained is True
        assert result.feature_list == feature_names
