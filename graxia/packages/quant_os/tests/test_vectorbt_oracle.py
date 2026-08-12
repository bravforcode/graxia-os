"""Test VectorBT oracle adapter."""
import pytest
from graxia.packages.quant_os.repo_intelligence.adapters.vectorbt_oracle import (
    validate_input, normalize_output, get_engine_name, run_oracle,
)


def test_get_engine_name():
    assert get_engine_name() == "vectorbt"


def test_validate_input_checks_columns():
    valid = {
        "data": {"open": [], "high": [], "low": [], "close": [], "volume": []},
        "timestamps": [],
    }
    assert validate_input(valid, {}) is True


def test_validate_input_rejects_missing_columns():
    bad = {"data": {"open": [], "close": []}, "timestamps": []}
    with pytest.raises(ValueError, match="missing OHLCV"):
        validate_input(bad, {})


def test_validate_input_rejects_non_list():
    bad = {"data": {"open": "oops", "high": [], "low": [], "close": [], "volume": []}, "timestamps": []}
    with pytest.raises(ValueError, match="must be a list"):
        validate_input(bad, {})


def test_validate_input_rejects_timestamp_mismatch():
    bad = {
        "data": {"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1, 2], "volume": [1, 2]},
        "timestamps": ["2024-01-01"],
    }
    with pytest.raises(ValueError, match="timestamps length"):
        validate_input(bad, {})


def test_normalize_output_empty():
    result = normalize_output({"trades": []})
    assert result == []


def test_normalize_output_single_trade():
    raw = {
        "trades": [
            {
                "signal_id": "abc123",
                "timestamp_utc": "2024-01-01T00:00:00",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 52000.0,
                "exit_price": 51000.0,
                "exit_reason": "closed",
                "pnl_gross": 100.0,
                "pnl_net": 90.0,
                "engine": "vectorbt",
            }
        ]
    }
    result = normalize_output(raw)
    assert len(result) == 1
    assert result[0]["signal_id"] == "abc123"
    assert result[0]["engine"] == "vectorbt"
    assert result[0]["side"] == "BUY"
    assert result[0]["entry_price"] == 50000.0


def test_run_oracle_graceful_import_error():
    """If vectorbt not installed, should return error dict."""
    result = run_oracle({}, [], {}, {})
    assert "error" in result or "trades" in result
