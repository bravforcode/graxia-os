"""B2: VaR and correlation risk check tests."""

import asyncio
import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

# Add the packages dir so quant_os is importable as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from quant_os.core.enums import OrderSide
from quant_os.execution.order import Order
from quant_os.risk.engine import RiskEngine


def _make_order(symbol="XAUUSD", side=OrderSide.BUY, qty=0.1):
    order = MagicMock(spec=Order)
    order.symbol = symbol
    order.side = side
    order.quantity = qty
    order.trading_mode = "PAPER"
    order.price = 2000.0
    order.stop_price = 1990.0
    order.strategy_id = "test"
    order.order_id = "test-001"
    return order


def _engine():
    return RiskEngine()


# ── var_95 static helper ──────────────────────────────────────────────


def test_var_95_basic():
    rng = np.random.default_rng(42)
    returns = rng.normal(0.001, 0.02, size=252)
    var = RiskEngine.var_95(returns)
    assert var > 0, "VaR should be positive for typical return distributions"
    assert isinstance(var, float)


def test_var_95_all_zero_returns():
    returns = np.zeros(100)
    var = RiskEngine.var_95(returns)
    assert var == 0.0


def test_var_95_empty_array():
    var = RiskEngine.var_95(np.array([]))
    assert var == 0.0


def test_var_95_short_history():
    returns = np.array([-0.03, -0.01, 0.005, 0.02, 0.01])
    var = RiskEngine.var_95(returns)
    assert var >= 0.0
    assert isinstance(var, float)


def test_var_95_single_element():
    var = RiskEngine.var_95(np.array([-0.05]))
    assert var == pytest.approx(0.05)


def test_var_95_negative_returns_high_var():
    returns = np.full(50, -0.01)
    var = RiskEngine.var_95(returns)
    assert var == pytest.approx(0.01, abs=1e-10)


# ── check_var_exposure ────────────────────────────────────────────────


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_var_check_passes_within_limit():
    engine = _engine()
    order = _make_order()
    returns = np.random.default_rng(1).normal(0.001, 0.005, size=252)
    result = _run(engine.check_var_exposure(order, returns, max_var_pct=0.02))
    assert result.passed
    assert result.check_type == "VAR_EXPOSURE"


def test_var_check_rejects_when_breached():
    engine = _engine()
    order = _make_order()
    returns = np.random.default_rng(2).normal(-0.05, 0.1, size=252)
    result = _run(engine.check_var_exposure(order, returns, max_var_pct=0.02))
    assert not result.passed
    assert result.check_type == "VAR_EXPOSURE"
    assert "exceeds" in result.reason


def test_var_check_empty_returns():
    engine = _engine()
    order = _make_order()
    result = _run(engine.check_var_exposure(order, np.array([]), max_var_pct=0.02))
    assert result.passed


def test_var_check_custom_threshold():
    engine = _engine()
    order = _make_order()
    returns = np.random.default_rng(3).normal(0.0, 0.015, size=252)
    result_tight = _run(engine.check_var_exposure(order, returns, max_var_pct=0.001))
    result_loose = _run(engine.check_var_exposure(order, returns, max_var_pct=0.50))
    assert not result_tight.passed
    assert result_loose.passed


# ── check_correlation_exposure ─────────────────────────────────────────


def test_corr_check_passes_low_correlation():
    engine = _engine()
    order = _make_order("GBPUSD")
    positions = {"EURUSD": 0.5, "USDJPY": 0.3}
    corr_matrix = {
        "GBPUSD": {"EURUSD": 0.3, "USDJPY": 0.1},
        "EURUSD": {"GBPUSD": 0.3, "USDJPY": 0.5},
    }
    result = _run(engine.check_correlation_exposure(order, positions, corr_matrix, threshold=0.8))
    assert result.passed


def test_corr_check_rejects_high_correlation():
    engine = _engine()
    order = _make_order("GBPUSD")
    positions = {"EURUSD": 0.5, "USDJPY": 0.3}
    corr_matrix = {
        "GBPUSD": {"EURUSD": 0.95, "USDJPY": 0.1},
        "EURUSD": {"GBPUSD": 0.95, "USDJPY": 0.5},
    }
    result = _run(engine.check_correlation_exposure(order, positions, corr_matrix, threshold=0.8))
    assert not result.passed
    assert result.check_type == "CORRELATION_EXPOSURE"
    assert "exceeds" in result.reason


def test_corr_check_unknown_symbol_passes():
    engine = _engine()
    order = _make_order("BTCUSD")
    positions = {"EURUSD": 0.5}
    corr_matrix = {"EURUSD": {"EURUSD": 1.0}}
    result = _run(engine.check_correlation_exposure(order, positions, corr_matrix, threshold=0.8))
    assert result.passed


def test_corr_check_empty_positions():
    engine = _engine()
    order = _make_order("GBPUSD")
    corr_matrix = {"GBPUSD": {"EURUSD": 0.9}}
    result = _run(engine.check_correlation_exposure(order, {}, corr_matrix, threshold=0.8))
    assert result.passed


def test_corr_check_exact_threshold_rejects():
    engine = _engine()
    order = _make_order("GBPUSD")
    positions = {"EURUSD": 1.0}
    corr_matrix = {"GBPUSD": {"EURUSD": 0.81}, "EURUSD": {"GBPUSD": 0.81}}
    result = _run(engine.check_correlation_exposure(order, positions, corr_matrix, threshold=0.8))
    assert not result.passed


def test_corr_check_zero_weight_ignored():
    engine = _engine()
    order = _make_order("GBPUSD")
    positions = {"EURUSD": 0.0}
    corr_matrix = {"GBPUSD": {"EURUSD": 0.99}, "EURUSD": {"GBPGBP": 0.99}}
    result = _run(engine.check_correlation_exposure(order, positions, corr_matrix, threshold=0.8))
    assert result.passed


def test_corr_check_negative_correlation_passes():
    engine = _engine()
    order = _make_order("GBPUSD")
    positions = {"EURUSD": 0.5}
    corr_matrix = {"GBPUSD": {"EURUSD": -0.9}, "EURUSD": {"GBPUSD": -0.9}}
    result = _run(engine.check_correlation_exposure(order, positions, corr_matrix, threshold=0.8))
    assert result.passed
