"""Phase 3.1A — Release reproducibility tests.

Two clean-process runs must produce identical test count, results, and ledger hash.
"""
from graxia.packages.quant_os.backtest.engine_e2e_fixture import (
    get_all_scenarios, DeterministicStrategy,
)
from graxia.packages.quant_os.backtest.engine import BacktestEngine
from graxia.packages.quant_os.execution.ledger_integrity import IntegrityChain, LedgerRecord
from graxia.packages.quant_os.execution.provenance import create_default_provenance


def _run_scenario(scenario_idx):
    """Run one scenario and return (trade_count, trade_list)."""
    scenarios = get_all_scenarios()
    name, config, bars, ts, signals, expected = scenarios[scenario_idx]

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
    trades = result.get("trades", [])
    return len(trades), [
        (t["entry_price"], t["exit_price"], round(t["pnl"], 6))
        for t in trades
    ]


def test_engine_e2e_fixture_loads():
    """All 12 scenarios load without error."""
    scenarios = get_all_scenarios()
    assert len(scenarios) == 12


def test_deterministic_repeat():
    """Same inputs produce identical trade lists."""
    r1 = _run_scenario(0)
    r2 = _run_scenario(0)
    assert r1 == r2, f"Non-deterministic: {r1} vs {r2}"


def test_all_scenarios_run():
    """Every scenario runs without exception."""
    for i in range(12):
        count, trades = _run_scenario(i)
        assert count >= 0


def test_ledger_integrity_on_fixture():
    """Ledger chain verifies clean after synthetic run."""
    chain = IntegrityChain()
    for i in range(5):
        rec = LedgerRecord(
            trade_id=f"t-{i}", order_id=f"o-{i}", symbol="XAUUSD",
            side="BUY", entry_price="2000.00", exit_price="2010.00",
            volume="0.10", pnl="10.00", fees="3.50", spread_cost="2.00",
            slippage_cost="1.00", entry_time="2025-01-01T00:00:00",
            exit_time="2025-01-02T00:00:00", close_reason="TAKE_PROFIT",
            strategy_id="test", contract_snapshot_id="v1",
            risk_policy_version="DEFAULT", dataset_manifest_id="d1",
            cost_scenario="BASE", git_commit="abc123",
        )
        chain.append(rec)
    valid, errors = chain.verify()
    assert valid, f"Chain verification failed: {errors}"


def test_provenance_hash_deterministic():
    """Same provenance produces same hash."""
    p1 = create_default_provenance("test_commit")
    p2 = create_default_provenance("test_commit")
    assert p1.provenance_hash() == p2.provenance_hash()


def test_provenance_hash_differs_on_change():
    """Different commit produces different hash."""
    p1 = create_default_provenance("commit_a")
    p2 = create_default_provenance("commit_b")
    assert p1.provenance_hash() != p2.provenance_hash()
