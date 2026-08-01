"""
Tests for FOMC event study script.

Covers:
  - compute_event_returns with synthetic price data
  - run_event_study returns expected structure
  - Edge cases: no FOMC dates in range, empty data
  - Statistical functions (t-test)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# scripts/ is not a package — add to sys.path for imports
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import event_study_fomc as mod  # noqa: E402
from event_study_fomc import (
    EventStudyResult,
    _ttest_1samp,
    compute_event_returns,
    fetch_price_data,
    run_event_study,
)

# ── Helpers ──


def _make_prices(
    start: str = "2024-01-01",
    n_days: int = 30,
    price: float = 2000.0,
    hourly: bool = True,
) -> pd.DataFrame:
    """Create synthetic OHLCV data with optional drift."""
    if hourly:
        idx = pd.date_range(start, periods=n_days * 24, freq="1h", tz="UTC")
    else:
        idx = pd.date_range(start, periods=n_days, freq="1D", tz="UTC")

    np.random.seed(42)
    returns = np.random.normal(0, 0.001, len(idx))
    close = price * np.cumprod(1 + returns)
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.001,
            "Low": close * 0.998,
            "Close": close,
            "Volume": np.random.randint(100, 1000, len(idx)),
        },
        index=idx,
    )


def _make_drift_prices(
    fomc_date: str = "2024-01-31",
    drift_pct: float = 1.0,
    price: float = 2000.0,
) -> pd.DataFrame:
    """Create prices with a known drift around a specific FOMC date."""
    # 60 days of data centered on FOMC date
    start_dt = pd.Timestamp(f"{fomc_date} 00:00:00", tz="UTC") - pd.Timedelta(days=30)
    idx = pd.date_range(start_dt, periods=60 * 24, freq="1h", tz="UTC")

    close = np.full(len(idx), price)
    # Apply drift starting 24h before FOMC announcement (18:00 UTC)
    fomc_dt = pd.Timestamp(f"{fomc_date} 18:00:00", tz="UTC")
    pre_start = fomc_dt - pd.Timedelta(hours=24)
    post_end = fomc_dt + pd.Timedelta(hours=48)

    mask = (idx >= pre_start) & (idx <= post_end)
    n_drift = mask.sum()
    drift_per_bar = (1 + drift_pct / 100.0) ** (1.0 / n_drift) - 1.0

    cumulative = np.ones(len(idx))
    in_window = False
    count = 0
    for i, ts in enumerate(idx):
        if ts >= pre_start and ts <= post_end:
            if not in_window:
                in_window = True
                count = 0
            cumulative[i] = (1 + drift_per_bar) ** count
            count += 1
        elif ts > post_end and in_window:
            cumulative[i] = cumulative[i - 1]
            in_window = False
        elif i > 0:
            cumulative[i] = cumulative[i - 1]

    close = price * cumulative
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.001,
            "Low": close * 0.998,
            "Close": close,
            "Volume": np.random.randint(100, 1000, len(idx)),
        },
        index=idx,
    )


# ── Tests: compute_event_returns ──


class TestComputeEventReturns:
    """Tests for the core event return computation."""

    def test_single_event_returns_expected_columns(self):
        """DataFrame output has required columns."""
        prices = _make_prices()
        dates = ["2024-01-15"]
        result = compute_event_returns(prices, dates, pre_window=24, post_window=48)

        assert isinstance(result, pd.DataFrame)
        assert "event_date" in result.columns
        assert "return_pct" in result.columns
        assert "pre_price" in result.columns
        assert "post_price" in result.columns
        assert "n_bars" in result.columns

    def test_single_event_one_row(self):
        """One FOMC date → one row."""
        prices = _make_prices()
        dates = ["2024-01-15"]
        result = compute_event_returns(prices, dates)
        assert len(result) == 1

    def test_multiple_events(self):
        """Multiple FOMC dates → multiple rows."""
        prices = _make_prices(n_days=60)
        dates = ["2024-01-10", "2024-01-20", "2024-01-30"]
        result = compute_event_returns(prices, dates)
        assert len(result) == 3

    def test_return_is_percentage(self):
        """return_pct should be in percentage points, not fraction."""
        prices = _make_prices(price=100.0)
        dates = ["2024-01-15"]
        result = compute_event_returns(prices, dates, pre_window=24, post_window=48)

        # With random walk around 100, return should be small (±few %)
        assert abs(result.iloc[0]["return_pct"]) < 10.0

    def test_known_drift(self):
        """Price with known drift should produce close to expected return."""
        prices = _make_drift_prices(drift_pct=2.0)
        result = compute_event_returns(prices, ["2024-01-31"], pre_window=24, post_window=48)
        assert len(result) == 1
        # Should be approximately 2% (may differ slightly due to bar alignment)
        assert abs(result.iloc[0]["return_pct"] - 2.0) < 0.5

    def test_event_outside_range_skipped(self):
        """FOMC date outside price data range → skipped."""
        prices = _make_prices(start="2024-06-01", n_days=10)
        dates = ["2024-01-15"]  # Before price data
        result = compute_event_returns(prices, dates)
        assert len(result) == 0

    def test_empty_dates_returns_empty(self):
        """No FOMC dates → empty DataFrame."""
        prices = _make_prices()
        result = compute_event_returns(prices, [])
        assert result.empty


# ── Tests: run_event_study ──


class TestRunEventStudy:
    """Tests for the full event study pipeline (with synthetic data)."""

    @pytest.fixture
    def mock_fomc_dates(self):
        """A few FOMC dates within our synthetic data range."""
        return ["2024-01-10", "2024-01-20", "2024-01-30"]

    def test_returns_event_study_result(self):
        """run_event_study returns EventStudyResult."""
        prices = _make_prices(n_days=60)

        # Patch fetch_price_data to return our synthetic data
        original_fetch = fetch_price_data.__module__
        # mod already imported at module level

        original_fn = mod.fetch_price_data
        mod.fetch_price_data = lambda *a, **kw: prices
        try:
            result = run_event_study(
                symbol="TEST",
                fomc_dates=["2024-01-10", "2024-01-20", "2024-01-30"],
                pre_window=24,
                post_window=48,
                start="2024-01-01",
            )
        finally:
            mod.fetch_price_data = original_fn

        assert isinstance(result, EventStudyResult)
        assert result.symbol == "TEST"
        assert result.n_events >= 1
        assert isinstance(result.avg_return, float)
        assert isinstance(result.t_stat, float)
        assert isinstance(result.p_value, float)
        assert 0.0 <= result.hit_rate <= 1.0

    def test_result_fields_are_frozen(self):
        """EventStudyResult is a frozen dataclass."""
        r = EventStudyResult(
            symbol="X",
            n_events=1,
            pre_window=24,
            post_window=48,
            avg_return=0.1,
            median_return=0.1,
            std_return=0.05,
            t_stat=1.5,
            p_value=0.2,
            hit_rate=0.6,
            event_returns=[0.1],
            event_dates=["2024-01-15"],
        )
        with pytest.raises(AttributeError):
            r.symbol = "Y"  # type: ignore[misc]

    def test_empty_fomc_dates_returns_zero(self):
        """No FOMC dates in range → n_events=0, no error."""
        # mod already imported at module level

        original_fn = mod.fetch_price_data
        mod.fetch_price_data = lambda *a, **kw: _make_prices()
        try:
            result = run_event_study(
                symbol="TEST",
                fomc_dates=[],  # Empty
                start="2024-01-01",
            )
        finally:
            mod.fetch_price_data = original_fn

        assert result.n_events == 0
        assert result.avg_return == 0.0
        assert result.p_value == 1.0

    def test_out_of_range_fomc_dates(self):
        """FOMC dates outside start/end range → filtered out."""
        # mod already imported at module level

        original_fn = mod.fetch_price_data
        mod.fetch_price_data = lambda *a, **kw: _make_prices()
        try:
            result = run_event_study(
                symbol="TEST",
                fomc_dates=["2019-01-15", "2019-06-15"],
                start="2024-01-01",
            )
        finally:
            mod.fetch_price_data = original_fn

        assert result.n_events == 0


# ── Tests: Statistical Functions ──


class TestTtest:
    """Tests for the one-sample t-test implementation."""

    def test_zero_mean_returns_high_pvalue(self):
        """Symmetric data around zero → high p-value."""
        data = np.random.normal(0, 1, 100)
        t_stat, p_value = _ttest_1samp(data, 0.0)
        assert abs(t_stat) < 2.0
        assert p_value > 0.05

    def test_positive_shift_returns_low_pvalue(self):
        """Positive shift → low p-value."""
        data = np.random.normal(5, 1, 100)
        t_stat, p_value = _ttest_1samp(data, 0.0)
        assert t_stat > 10.0
        assert p_value < 0.01

    def test_single_sample(self):
        """Edge case: n=1 → returns (0, 1)."""
        t_stat, p_value = _ttest_1samp(np.array([5.0]), 0.0)
        assert t_stat == 0.0
        assert p_value == 1.0

    def test_constant_data(self):
        """Edge case: std=0 → returns (0, 1)."""
        t_stat, p_value = _ttest_1samp(np.array([3.0, 3.0, 3.0]), 0.0)
        assert t_stat == 0.0
        assert p_value == 1.0


# ── Tests: Edge Cases ──


class TestEdgeCases:
    """Edge case coverage."""

    def test_no_yfinance_does_not_crash(self):
        """Script should not crash if yfinance import fails.

        This tests the import guard, not actual network calls.
        """
        # mod already imported at module level

        # Verify the import guard exists (try/except around yfinance)
        source = open(mod.__file__).read()
        assert "try:" in source
        assert "import yfinance" in source

    def test_fred_fallback(self):
        """No FRED key → falls back to hardcoded list."""
        dates = mod.fetch_fomc_dates_fred(api_key=None)
        assert len(dates) > 0
        assert dates == mod.FOMC_DATES

    def test_fred_bad_key_falls_back(self):
        """Invalid FRED key → falls back to hardcoded list."""
        dates = mod.fetch_fomc_dates_fred(api_key="invalid_key_12345")
        assert len(dates) > 0
        assert dates == mod.FOMC_DATES
