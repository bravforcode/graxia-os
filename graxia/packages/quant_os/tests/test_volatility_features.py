"""Tests for volatility features V1-V7 and HAR model."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Import by file path to avoid shadowing from monorepo core/ package
_root = Path(__file__).resolve().parent.parent

_vol_spec = importlib.util.spec_from_file_location(
    "core.volatility_features", str(_root / "core" / "volatility_features.py")
)
_vol = importlib.util.module_from_spec(_vol_spec)
sys.modules[_vol_spec.name] = _vol
_vol_spec.loader.exec_module(_vol)

_har_spec = importlib.util.spec_from_file_location("ml.har_model", str(_root / "ml" / "har_model.py"))
_har = importlib.util.module_from_spec(_har_spec)
sys.modules[_har_spec.name] = _har
_har_spec.loader.exec_module(_har)

VolatilityFeatures = _vol.VolatilityFeatures
build_volatility_features = _vol.build_volatility_features
compute_garman_klass_vol = _vol.compute_garman_klass_vol
compute_parkinson_vol = _vol.compute_parkinson_vol
compute_realized_vol = _vol.compute_realized_vol
compute_vol_autocorr = _vol.compute_vol_autocorr
compute_vol_of_vol = _vol.compute_vol_of_vol
compute_vol_ratio = _vol.compute_vol_ratio
compute_vol_regime = _vol.compute_vol_regime
HARModel = _har.HARModel
HARResult = _har.HARResult


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    n = 300
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    close = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.02))
    high = close * (1 + np.abs(np.random.randn(n) * 0.01))
    low = close * (1 - np.abs(np.random.randn(n) * 0.01))
    open_ = close * (1 + np.random.randn(n) * 0.005)
    volume = np.random.randint(1000, 10000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def realized_vol_series(sample_ohlcv) -> pd.Series:
    """Compute realized vol from sample data."""
    return compute_realized_vol(sample_ohlcv["close"], window=20)


# --- V1-V7 individual feature tests ---


def test_parkinson_vol_positive(sample_ohlcv):
    vol = compute_parkinson_vol(sample_ohlcv["high"], sample_ohlcv["low"])
    vol_clean = vol.dropna()
    assert (vol_clean >= 0).all()
    assert len(vol_clean) > 0


def test_garman_klass_vol_positive(sample_ohlcv):
    vol = compute_garman_klass_vol(
        sample_ohlcv["open"],
        sample_ohlcv["high"],
        sample_ohlcv["low"],
        sample_ohlcv["close"],
    )
    vol_clean = vol.dropna()
    assert (vol_clean >= 0).all()
    assert len(vol_clean) > 0


def test_realized_vol_positive(sample_ohlcv):
    vol = compute_realized_vol(sample_ohlcv["close"])
    vol_clean = vol.dropna()
    assert (vol_clean >= 0).all()
    assert len(vol_clean) > 0


def test_vol_of_vol_positive(realized_vol_series):
    vov = compute_vol_of_vol(realized_vol_series)
    vov_clean = vov.dropna()
    assert (vov_clean >= 0).all()


def test_vol_regime_labels(sample_ohlcv):
    vol = compute_realized_vol(sample_ohlcv["close"], window=20)
    regime = compute_vol_regime(vol)
    valid = regime.dropna()
    assert set(valid.unique()).issubset({"LOW", "MED", "HIGH"})


def test_vol_ratio_positive(sample_ohlcv):
    vol_short = compute_realized_vol(sample_ohlcv["close"], 5)
    vol_long = compute_realized_vol(sample_ohlcv["close"], 60)
    ratio = compute_vol_ratio(vol_short, vol_long)
    ratio_clean = ratio.dropna()
    assert (ratio_clean > 0).all()


def test_vol_autocorr_range(realized_vol_series):
    autocorr = compute_vol_autocorr(realized_vol_series)
    autocorr_clean = autocorr.dropna()
    assert (autocorr_clean >= -1).all()
    assert (autocorr_clean <= 1).all()


def test_build_volatility_features(sample_ohlcv):
    features = build_volatility_features(sample_ohlcv)
    assert isinstance(features, VolatilityFeatures)
    assert len(features.parkinson.dropna()) > 0
    assert len(features.garman_klass.dropna()) > 0
    assert len(features.realized_vol.dropna()) > 0
    assert len(features.vol_of_vol.dropna()) > 0
    assert len(features.vol_ratio.dropna()) > 0


# --- HAR model tests ---


def test_har_fit_coefficients(realized_vol_series):
    model = HARModel()
    result = model.fit(realized_vol_series)
    assert "b0" in result
    assert "b1" in result
    assert "b2" in result
    assert "b3" in result
    assert "r_squared" in result
    assert result["n_observations"] > 0


def test_har_predict_positive(realized_vol_series):
    model = HARModel()
    model.fit(realized_vol_series)
    forecast = model.predict(realized_vol_series, steps=5)
    assert len(forecast) == 5
    assert (forecast >= 0).all()


def test_har_predict_raises_unfitted(realized_vol_series):
    model = HARModel()
    with pytest.raises(ValueError, match="not fitted"):
        model.predict(realized_vol_series)


def test_har_evaluate_r_squared(realized_vol_series):
    model = HARModel()
    result = model.evaluate(realized_vol_series, test_size=60)
    assert isinstance(result, HARResult)
    assert len(result.forecast) == 60
    assert len(result.residuals) == 60
    assert isinstance(result.r_squared, float)
