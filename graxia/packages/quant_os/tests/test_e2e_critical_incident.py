"""E2E: Missing/invalid SL must produce CRITICAL_INCIDENT or rejection.

KNOWN GAP: Engine does not validate SL direction (e.g. SL above entry for
LONG). The invalid_sl_rejected scenario currently opens a trade. These tests
assert current behavior — upgrade to 0-trade assertion once engine adds
SL direction validation.
"""
from graxia.packages.quant_os.backtest.engine_e2e_fixture import get_all_scenarios, DeterministicStrategy
from graxia.packages.quant_os.backtest.engine import BacktestEngine


def _run_scenario(index):
    scenarios = get_all_scenarios()
    name, config, bars, ts, signals, expected = scenarios[index]
    strategy = DeterministicStrategy(signals)
    engine = BacktestEngine(config)
    engine.set_strategy(strategy)
    ohlcv = {
        "open": [float(b["open"]) for b in bars],
        "high": [float(b["high"]) for b in bars],
        "low": [float(b["low"]) for b in bars],
        "close": [float(b["close"]) for b in bars],
        "volume": [1000] * len(bars),
    }
    engine.load_data(ohlcv, ts)
    return engine.run()


def test_missing_sl_no_trades():
    result = _run_scenario(6)  # missing_sl_rejected
    trades = result.get("trades", [])
    assert len(trades) == 0, f"Expected 0 trades for missing SL, got {len(trades)}"


def test_invalid_sl_no_trades():
    result = _run_scenario(7)  # invalid_sl_rejected
    trades = result.get("trades", [])
    assert len(trades) == 0, f"Expected 0 trades for invalid SL (SL above entry for LONG), got {len(trades)}"
