"""Risk engine unit tests -- Monte Carlo, scaling gates, and ladder logic."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.risk.monte_carlo import bootstrap_equity_paths
from core.risk.scaling_gate import (
    GateConfig,
    GateResult,
    check_gate_5,
    check_gate_6,
    evaluate_ladder,
)
from core.risk.scaling_ladder import (
    LADDER_A_GATES,
    LADDER_B_GATES,
    get_current_lot,
    next_gate_info,
)


def _bullish_pnls(n=300, seed=1):
    rng = np.random.default_rng(seed)
    return rng.normal(2.0, 5.0, size=n)


def _bearish_pnls(n=300, seed=2):
    rng = np.random.default_rng(seed)
    return rng.normal(-1.5, 5.0, size=n)


def _flat_pnls(n=300, seed=3):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 5.0, size=n)


def test_bootstrap_bullish_pnl():
    pnls = _bullish_pnls()
    result = bootstrap_equity_paths(pnls, n_sims=2000, n_trades_forward=540)
    assert result["prob_ruin"] < 1.0
    assert result["median_ending_balance"] > 5000.0
    assert "equity_paths" in result
    assert result["equity_paths"].shape == (2000, 540)


def test_bootstrap_bearish_pnl():
    pnls = _bearish_pnls()
    result = bootstrap_equity_paths(pnls, n_sims=2000, n_trades_forward=540)
    assert result["prob_ruin"] > 0.0


def test_lot_multiplier_scales():
    pnls = _bullish_pnls(seed=42)
    r1 = bootstrap_equity_paths(pnls, n_sims=2000, lot_multiplier=1.0)
    r2 = bootstrap_equity_paths(pnls, n_sims=2000, lot_multiplier=2.0)
    assert r2["prob_ruin"] >= r1["prob_ruin"]
    up1 = r1["median_ending_balance"] - 5000.0
    up2 = r2["median_ending_balance"] - 5000.0
    assert abs(up2) > abs(up1) * 0.5


def test_kill_switch_detection():
    pnls = _bearish_pnls(seed=5)
    r_tight = bootstrap_equity_paths(pnls, n_sims=2000, starting_balance=5000.0, kill_switch_balance=4900.0)
    r_wide = bootstrap_equity_paths(pnls, n_sims=2000, starting_balance=5000.0, kill_switch_balance=1000.0)
    assert r_tight["prob_ruin"] >= r_wide["prob_ruin"]


def test_empty_trades_raises():
    try:
        bootstrap_equity_paths(np.array([]))
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_gate_5_passes_with_good_data():
    pnls = _bullish_pnls(n=1000, seed=10)
    config = GateConfig(
        name="Gate 5: Paper Validation",
        min_trades=300,
        min_t_stat=1.5,
        min_win_rate=0.50,
        min_sharpe=0.2,
        min_months=1,
        min_balance=5000.0,
        max_prob_ruin_current=0.50,
        max_prob_ruin_next=0.50,
    )
    result = check_gate_5(pnls, 5000.0, config)
    assert result.passed
    assert result.prob_ruin < 1.0
    assert isinstance(result, GateResult)


def test_gate_5_fails_with_few_trades():
    pnls = _bullish_pnls(n=50, seed=10)
    config = GateConfig(
        name="Gate 5: Paper Validation",
        min_trades=300,
        min_t_stat=1.5,
        min_win_rate=0.50,
        min_sharpe=0.2,
        min_months=1,
        min_balance=5000.0,
        max_prob_ruin_current=0.50,
        max_prob_ruin_next=0.50,
    )
    result = check_gate_5(pnls, 5000.0, config)
    assert not result.passed
    assert "BLOCKED" in result.decision


def test_gate_6_blocks_high_ruin():
    pnls = _bearish_pnls(n=1000, seed=20)
    config = GateConfig(
        name="Gate 6: Live Scaling",
        min_trades=100,
        min_t_stat=0.0,
        min_win_rate=0.0,
        min_sharpe=0.0,
        min_months=1,
        min_balance=5000.0,
        max_prob_ruin_current=0.01,
        max_prob_ruin_next=0.01,
    )
    result = check_gate_6(pnls, 5000.0, config, next_lot_mult=2.0)
    assert not result.passed


def test_gate_6_empty_raises():
    config = GateConfig(
        name="Gate 6: Test",
        min_trades=100,
        min_t_stat=0.0,
        min_win_rate=0.0,
        min_sharpe=0.0,
        min_months=1,
        min_balance=5000.0,
        max_prob_ruin_current=0.05,
        max_prob_ruin_next=0.02,
    )
    try:
        check_gate_6(np.array([]), 5000.0, config, 2.0)
        assert False, "should have raised"
    except ValueError:
        pass


def test_evaluate_ladder():
    pnls_periods = [
        _bullish_pnls(n=600, seed=30),
        _bullish_pnls(n=600, seed=31),
        _bullish_pnls(n=600, seed=32),
    ]
    gates = LADDER_A_GATES[:3]
    results = evaluate_ladder(pnls_periods, gates, 5000.0)
    assert len(results) == 3
    for r in results:
        assert isinstance(r, GateResult)


def test_ladder_b_tighter_than_ladder_a():
    for ga, gb in zip(LADDER_A_GATES, LADDER_B_GATES, strict=False):
        assert gb.max_prob_ruin_current < ga.max_prob_ruin_current
        assert gb.max_prob_ruin_next < ga.max_prob_ruin_next


def test_get_current_lot():
    assert get_current_lot(300, 0) == 0.01
    assert get_current_lot(600, 1) == 0.02
    assert get_current_lot(1200, 2) == 0.03
    assert get_current_lot(2000, 3) == 0.04


def test_next_gate_info():
    gate = next_gate_info(0.01, 600)
    assert gate is not None
    assert "0.01" in gate.name
    gate = next_gate_info(0.04, 3000)
    assert gate is None


def test_plot_equity_paths_no_matplotlib():
    from core.risk.monte_carlo import plot_equity_paths

    pnls = _bullish_pnls()
    result = bootstrap_equity_paths(pnls, n_sims=100, n_trades_forward=100)
    plot_equity_paths(result["equity_paths"], title="Test Plot")
