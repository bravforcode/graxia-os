"""Tests for Backtesting.py oracle adapter."""
import sys
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.repo_intelligence.adapters.backtesting_py_oracle import (
    get_engine_name,
    normalize_output,
    validate_input,
    run_oracle,
)


def test_get_engine_name():
    assert get_engine_name() == "backtesting_py"


def test_validate_input_valid():
    manifest = {
        "columns": {"Open", "High", "Low", "Close", "Volume"},
        "frequency": "1d",
    }
    assert validate_input(manifest, {}) is True


def test_validate_input_missing_columns():
    manifest = {"columns": {"Open", "Close"}, "frequency": "1d"}
    with pytest.raises(ValueError, match="Missing OHLCV"):
        validate_input(manifest, {})


def test_validate_input_bad_frequency():
    manifest = {
        "columns": {"Open", "High", "Low", "Close", "Volume"},
        "frequency": "2h",
    }
    with pytest.raises(ValueError, match="Unsupported frequency"):
        validate_input(manifest, {})


def test_normalize_output():
    import pandas as pd

    trades = pd.DataFrame({
        "EntryTime": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-05")],
        "EntryPrice": [100.0, 200.0],
        "ExitPrice": [110.0, 190.0],
        "Size": [1.0, -1.0],
        "PnL": [10.0, 10.0],
        "ExitReason": ["Closed", "Stop"],
    })
    signals = normalize_output({"trades": trades}, symbol="BTC-USD")

    assert len(signals) == 2
    assert signals[0]["side"] == "long"
    assert signals[1]["side"] == "short"
    assert signals[0]["entry_price"] == 100.0
    assert signals[0]["exit_price"] == 110.0
    assert signals[0]["engine"] == "backtesting_py"
    assert signals[0]["pnl_gross"] == 10.0
    assert signals[1]["exit_reason"] == "Stop"


def test_run_oracle_graceful_import_error():
    # Ensure backtesting is not importable
    real_modules = dict(sys.modules)
    sys.modules.pop("backtesting", None)
    sys.modules["backtesting"] = None  # make import fail
    try:
        result = run_oracle(
            data={"Open": [1], "High": [2], "Low": [0.5], "Close": [1.5], "Volume": [100]},
            timestamps=["2024-01-01"],
            strategy_params={},
            contract_spec={"symbol": "TEST"},
        )
        assert result["engine"] == "backtesting_py"
        assert result["error"] == "backtesting not installed"
    finally:
        sys.modules.update(real_modules)
