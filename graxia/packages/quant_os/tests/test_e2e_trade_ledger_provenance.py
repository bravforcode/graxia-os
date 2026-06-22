"""E2E: Trade records must carry provenance fields."""
from graxia.packages.quant_os.backtest.engine_e2e_fixture import get_all_scenarios, DeterministicStrategy
from graxia.packages.quant_os.backtest.engine import BacktestEngine


def test_trades_have_provenance():
    scenarios = get_all_scenarios()
    name, config, bars, ts, signals, expected = scenarios[0]
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
    result = engine.run()
    for trade in result.get("trades", []):
        assert "strategy_id" in trade
        assert "execution_quality" in trade
        assert "entry_spread_cost" in trade
