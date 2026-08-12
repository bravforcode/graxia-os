"""Tests for strategy IR."""
from graxia.packages.quant_os.oracle.strategy_ir import StrategyIR, OracleSignal, OracleTrade


def test_strategy_ir_creation():
    ir = StrategyIR(
        symbol="XAUUSD", timeframe="M15", direction="BUY",
        stop_rule="20 pips", take_profit_rule="40 pips",
    )
    ok, issues = ir.validate()
    assert ok


def test_strategy_ir_hash():
    ir = StrategyIR(symbol="XAUUSD", timeframe="M15", direction="BUY")
    h = ir.compute_hash()
    assert h
    # Same IR = same hash
    ir2 = StrategyIR(symbol="XAUUSD", timeframe="M15", direction="BUY")
    assert ir.compute_hash() == ir2.compute_hash()


def test_strategy_ir_validation_fails():
    ir = StrategyIR()
    ok, issues = ir.validate()
    assert not ok
    assert any("symbol" in i for i in issues)


def test_oracle_signal_creation():
    signal = OracleSignal(
        signal_id="SIG001", direction="BUY",
        entry_price=2350.50, stop_loss=2348.50,
    )
    d = signal.to_dict()
    assert d["direction"] == "BUY"


def test_oracle_trade_creation():
    trade = OracleTrade(
        trade_id="T001", signal_id="SIG001",
        direction="BUY", entry_price=2350.50,
        exit_price=2355.00, pnl_points=4.50,
    )
    d = trade.to_dict()
    assert d["pnl_points"] == 4.50
