"""Tests for oracle adapter base."""
from graxia.packages.quant_os.oracle.oracle_adapter import OracleAdapter, OracleConfig, StubOracle


def test_oracle_config():
    config = OracleConfig(name="vectorbt", version="1.0", framework="vectorbt")
    assert config.name == "vectorbt"


def test_stub_oracle():
    stub = StubOracle()
    assert stub.is_stub()
    assert stub.run([]) == []
    assert stub.load_strategy({}) is False


def test_stub_oracle_signals():
    stub = StubOracle()
    assert stub.get_signals() == []
    assert stub.get_trades() == []
