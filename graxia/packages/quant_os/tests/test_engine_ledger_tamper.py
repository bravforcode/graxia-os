"""Phase 3.1A.1 — Actual engine ledger tamper test.

Uses real engine output, not synthetic records.
"""
import pytest
from graxia.packages.quant_os.backtest.engine_e2e_fixture import get_all_scenarios, DeterministicStrategy
from graxia.packages.quant_os.backtest.engine import BacktestEngine
from graxia.packages.quant_os.execution.ledger_integrity import IntegrityChain, LedgerRecord


def _run_engine_scenario(scenario_idx=0):
    """Run engine and return trade list."""
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
    return result.get("trades", [])


def _trades_to_chain(trades):
    """Convert engine trade dicts to IntegrityChain."""
    chain = IntegrityChain()
    for t in trades:
        rec = LedgerRecord(
            trade_id=t["id"],
            order_id="",
            symbol=t["symbol"],
            side=t["side"],
            entry_price=str(t["entry_price"]),
            exit_price=str(t["exit_price"]),
            volume=str(t["quantity"]),
            pnl=str(t["pnl"]),
            fees=str(t["fees"]),
            spread_cost=str(t.get("entry_spread_cost", 0)),
            slippage_cost=str(t.get("entry_slippage_cost", 0)),
            entry_time=str(t["entry_time"]),
            exit_time=str(t["exit_time"]),
            close_reason=t["close_reason"],
            strategy_id=t.get("strategy_id", ""),
            contract_snapshot_id="test",
            risk_policy_version="DEFAULT",
            dataset_manifest_id="test",
            cost_scenario="BASE",
            git_commit="test",
        )
        chain.append(rec)
    return chain


def test_engine_ledger_verifies_clean():
    """Real engine output -> ledger chain must verify clean."""
    trades = _run_engine_scenario(0)
    if not trades:
        pytest.skip("No trades in scenario 0")
    chain = _trades_to_chain(trades)
    valid, errors = chain.verify()
    assert valid, f"Chain verification failed: {errors}"


def test_tamper_entry_price_detected():
    """Mutating entry_price must be detected."""
    trades = _run_engine_scenario(0)
    if not trades:
        pytest.skip("No trades")
    chain = _trades_to_chain(trades)
    chain._records[0].entry_price = "99999.99"
    valid, errors = chain.verify()
    assert not valid, "Tamper not detected"


def test_tamper_pnl_detected():
    """Mutating pnl must be detected."""
    trades = _run_engine_scenario(0)
    if not trades:
        pytest.skip("No trades")
    chain = _trades_to_chain(trades)
    chain._records[0].pnl = "999999.99"
    valid, errors = chain.verify()
    assert not valid


def test_tamper_cost_detected():
    """Mutating spread_cost must be detected."""
    trades = _run_engine_scenario(0)
    if not trades:
        pytest.skip("No trades")
    chain = _trades_to_chain(trades)
    chain._records[0].spread_cost = "0.00"
    valid, errors = chain.verify()
    assert not valid


def test_tamper_provenance_detected():
    """Mutating strategy_id must be detected."""
    trades = _run_engine_scenario(0)
    if not trades:
        pytest.skip("No trades")
    chain = _trades_to_chain(trades)
    chain._records[0].strategy_id = "HACKED"
    valid, errors = chain.verify()
    assert not valid


def test_tamper_reorder_detected():
    """Reordering records must be detected."""
    trades = _run_engine_scenario(10)
    chain = _trades_to_chain(trades)
    chain._records[0], chain._records[1] = chain._records[1], chain._records[0]
    valid, errors = chain.verify()
    assert not valid


def test_run_seal_deterministic():
    """Same engine run -> same seal."""
    trades = _run_engine_scenario(0)
    if not trades:
        pytest.skip("No trades")
    chain1 = _trades_to_chain(trades)
    seal1 = chain1.compute_run_seal("manifest")
    chain2 = _trades_to_chain(trades)
    seal2 = chain2.compute_run_seal("manifest")
    assert seal1 == seal2
