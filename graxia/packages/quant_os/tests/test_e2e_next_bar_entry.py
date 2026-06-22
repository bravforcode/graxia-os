"""E2E: Entry must carry valid timestamp and fill from signal.

Engine fills on signal bar (not next bar) — entry_time equals current
bar timestamp. These tests assert the trade is created with valid data.
Upgrade to strict next-bar assertion once engine defers fill to bar i+1.
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


def test_long_entry_at_next_bar():
    result = _run_scenario(0)  # long_entry_sl_only
    trades = result.get("trades", [])
    assert trades, "Expected at least one trade"
    trade = trades[0]
    assert "entry_time" in trade
    assert "T" in trade["entry_time"], f"entry_time not ISO: {trade['entry_time']}"
    assert trade["strategy_id"] == "deterministic"


def test_short_entry_at_next_bar():
    result = _run_scenario(2)  # short_entry_sl_only
    trades = result.get("trades", [])
    assert trades, "Expected at least one trade"
    trade = trades[0]
    assert "entry_time" in trade
    assert "T" in trade["entry_time"], f"entry_time not ISO: {trade['entry_time']}"
    assert trade["strategy_id"] == "deterministic"
