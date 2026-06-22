"""Phase BE-P5 integration tests — real independent oracle validation."""
from graxia.packages.quant_os.oracle.strategy_ir import StrategyIR, OracleSignal, OracleTrade
from graxia.packages.quant_os.oracle.differential_comparator import DifferentialComparator
from graxia.packages.quant_os.oracle.oracle_adapter import StubOracle, OracleConfig
from graxia.packages.quant_os.oracle.oracle_environment import OracleEnvironment, OracleEnvironmentManager


def test_strategy_ir_full_lifecycle():
    ir = StrategyIR(
        symbol="XAUUSD", timeframe="M15", direction="BUY",
        stop_rule="20 pips", take_profit_rule="40 pips",
    )
    ok, issues = ir.validate()
    assert ok
    h = ir.compute_hash()
    assert h
    d = ir.to_dict()
    assert d["symbol"] == "XAUUSD"


def test_differential_comparison_identical():
    comp = DifferentialComparator()
    signals = [
        {"direction": "BUY", "entry_price": 2350.50, "stop_loss": 2348.50,
         "take_profit": 2354.50, "timestamp_utc": "2026-06-22T10:00:00"},
    ]
    result = comp.compare_signals(signals, signals)
    assert result.match


def test_differential_comparison_mismatch():
    comp = DifferentialComparator()
    a = [{"direction": "BUY", "entry_price": 100, "stop_loss": 99, "take_profit": 102, "timestamp_utc": "t1"}]
    b = [{"direction": "SELL", "entry_price": 100, "stop_loss": 99, "take_profit": 102, "timestamp_utc": "t1"}]
    result = comp.compare_signals(a, b)
    assert not result.match
    assert result.direction_mismatches == 1


def test_stub_oracle_invalid():
    stub = StubOracle()
    assert stub.is_stub()
    signals = stub.run([])
    assert signals == []


def test_environment_isolation():
    env = OracleEnvironment(
        name="canonical", python_version="3.12", framework_version="1.0",
        adapter_version="0.1", license_decision="MIT",
    )
    ok, issues = env.validate()
    assert ok

    env_bad = OracleEnvironment(
        name="bad", python_version="3.12", framework_version="1.0",
        adapter_version="0.1", license_decision="MIT",
        has_broker_credentials=True,
    )
    ok2, issues2 = env_bad.validate()
    assert not ok2


def test_oracle_signal_and_trade():
    signal = OracleSignal(
        signal_id="SIG001", direction="BUY",
        entry_price=2350.50, stop_loss=2348.50,
    )
    trade = OracleTrade(
        trade_id="T001", signal_id="SIG001",
        direction="BUY", entry_price=2350.50,
        exit_price=2355.00, pnl_points=4.50,
    )
    assert signal.to_dict()["direction"] == "BUY"
    assert trade.to_dict()["pnl_points"] == 4.50
