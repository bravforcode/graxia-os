"""Tests for CorrelationAgent."""

from __future__ import annotations


from graxia.packages.quant_os.core.agents.correlation_agent import CorrelationAgent
from graxia.packages.quant_os.core.events import BarEvent, SignalEvent


def _bar(symbol: str, close: float) -> BarEvent:
    return BarEvent(source="test", symbol=symbol, close=close, open=close, high=close, low=close)


def test_observe_stores_prices():
    agent = CorrelationAgent(symbols=["XAUUSD", "USDJPY"])
    agent.observe(_bar("XAUUSD", 2000.0))
    agent.observe(_bar("USDJPY", 150.0))
    assert len(agent._filter._prices["XAUUSD"]) == 1
    assert len(agent._filter._prices["USDJPY"]) == 1


def test_observe_ignores_non_bar_events():
    agent = CorrelationAgent()
    agent.observe(SignalEvent(source="test"))
    assert agent._filter._prices == {}


def test_adjustment_returns_1_with_few_prices():
    agent = CorrelationAgent(symbols=["XAUUSD", "USDJPY"])
    agent.set_open_symbols(["XAUUSD", "USDJPY"])
    for i in range(5):
        agent.observe(_bar("XAUUSD", 2000.0 + i))
        agent.observe(_bar("USDJPY", 150.0 + i))
    assert agent.get_adjustment() == 1.0


def test_adjustment_returns_1_no_open_symbols():
    agent = CorrelationAgent()
    assert agent.get_adjustment() == 1.0


def test_high_correlation_reduces_adjustment():
    agent = CorrelationAgent(symbols=["XAUUSD", "USDJPY"])
    agent.set_open_symbols(["XAUUSD", "USDJPY"])
    # Feed 30 bars of perfectly correlated data
    for i in range(30):
        agent.observe(_bar("XAUUSD", 2000.0 + i * 10))
        agent.observe(_bar("USDJPY", 150.0 + i * 0.5))
    adj = agent.get_adjustment()
    assert adj < 1.0


def test_reset_clears_state():
    agent = CorrelationAgent(symbols=["XAUUSD", "USDJPY"])
    agent.observe(_bar("XAUUSD", 2000.0))
    agent.set_open_symbols(["XAUUSD", "USDJPY"])
    agent.reset()
    assert agent._open_symbols == []
    assert agent.get_adjustment() == 1.0


def test_default_symbols_are_multi_asset():
    agent = CorrelationAgent()
    assert "XAUUSD" in agent.TRACKED_SYMBOLS
    assert "EURUSD" in agent.TRACKED_SYMBOLS
    assert "GBPUSD" in agent.TRACKED_SYMBOLS


def test_only_tracked_symbols_accepted():
    agent = CorrelationAgent()
    agent.observe(_bar("BTCUSD", 50000.0))
    assert "BTCUSD" not in agent._filter._prices
