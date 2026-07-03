"""Tests for Backtrader oracle adapter."""

from graxia.packages.quant_os.repo_intelligence.adapters.backtrader_oracle import (
    get_engine_name,
    normalize_output,
    run_oracle,
    validate_input,
)


def test_get_engine_name():
    assert get_engine_name() == "backtrader"


def test_validate_input_valid():
    manifest = {"columns": ["open", "high", "low", "close", "volume"], "timeframe": "1d"}
    params = {"entry_threshold": 0.01}
    assert validate_input(manifest, params) is True


def test_validate_input_missing_columns():
    manifest = {"columns": ["close"], "timeframe": "1d"}
    params = {}
    try:
        validate_input(manifest, params)
        assert False, "should have raised"
    except ValueError as e:
        assert "missing" in str(e)


def test_validate_input_bad_timeframe():
    manifest = {"columns": ["open", "high", "low", "close", "volume"], "timeframe": "2m"}
    params = {}
    try:
        validate_input(manifest, params)
        assert False, "should have raised"
    except ValueError as e:
        assert "unsupported" in str(e)


def test_validate_input_no_timeframe():
    manifest = {"columns": ["open", "high", "low", "close", "volume"]}
    params = {}
    try:
        validate_input(manifest, params)
        assert False, "should have raised"
    except ValueError as e:
        assert "timeframe" in str(e)


def test_normalize_output_basic():
    raw = {
        "trades": [
            {
                "signal_id": "sig-1",
                "exit_timestamp": "2025-01-01T00:00:00Z",
                "symbol": "EURUSD",
                "side": "long",
                "entry_price": 1.1,
                "stop_loss": 1.09,
                "take_profit": 1.12,
                "exit_price": 1.11,
                "exit_reason": "tp",
                "pnl_gross": 100.0,
                "pnl_net": 99.5,
            }
        ]
    }
    result = normalize_output(raw)
    assert len(result) == 1
    sig = result[0]
    assert sig["engine"] == "backtrader"
    assert sig["symbol"] == "EURUSD"
    assert sig["side"] == "long"
    assert sig["pnl_gross"] == 100.0
    assert sig["pnl_net"] == 99.5
    assert sig["exit_reason"] == "tp"


def test_normalize_output_empty_trades():
    result = normalize_output({"trades": []})
    assert result == []


def test_normalize_output_adds_engine():
    raw = {"trades": [{"entry_price": 1.0}]}
    result = normalize_output(raw)
    assert result[0]["engine"] == "backtrader"
    assert isinstance(result[0]["signal_id"], str)


def test_run_oracle_graceful_import_error():
    """run_oracle returns error dict when backtrader isn't importable."""
    import builtins
    import unittest.mock as mock

    real_import = builtins.__import__

    def block_backtrader(name, *args, **kwargs):
        if name == "backtrader":
            raise ImportError("mocked: backtrader not installed")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=block_backtrader):
        result = run_oracle(
            data={"close": [1.0, 2.0, 3.0]},
            timestamps=[],
            strategy_params={},
            contract_spec={"symbol": "TEST"},
        )
        assert result["engine"] == "backtrader"
        assert "error" in result
        assert "backtrader" in result["error"].lower() or "not installed" in result["error"].lower()


def test_run_oracle_empty_data():
    """run_oracle with no data returns empty trades without needing backtrader."""
    result = run_oracle(
        data={},
        timestamps=[],
        strategy_params={},
        contract_spec={"symbol": "TEST"},
    )
    assert result["engine"] == "backtrader"
    assert result.get("trades") == []
