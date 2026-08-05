"""Unit tests for the Khubiev finance-grounded portfolio strategy.

Run from the quant_os package root:
    python -m pytest tests/test_khubiev_portfolio.py -q

These tests use purely synthetic data -- they make NO claim about real-data
edge (that is validated separately). They verify:
  * every finance-grounded loss returns a finite scalar,
  * generate_signal returns a valid Signal or None on synthetic OHLCV,
  * computed portfolio weights are market-neutral (sum ~ 0) and L2-capped.
"""

from __future__ import annotations

import numpy as np
import pytest

from graxia.packages.quant_os.strategies.khubiev_losses import (
    MDDLoss,
    ModSharpeAbsLoss,
    ModSharpeLoss,
    RiskAdjLoss,
    SharpeLoss,
    TvrReg,
    evaluate_all,
    max_drawdown,
)
from graxia.packages.quant_os.strategies.khubiev_portfolio import KhubievPortfolio

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_returns():
    """(T, N) synthetic daily-return matrix with mild cross-sectional signal."""
    rng = np.random.default_rng(1234)
    T, N = 800, 7
    mu = rng.normal(0.0, 0.0015, size=N)
    base = rng.normal(0.0, 0.01, size=(T, N))
    # Add a slow drift so the model has something to learn.
    drift = np.linspace(0.0, 0.004, T)[:, None]
    return base + mu + drift


@pytest.fixture
def synthetic_strategy(synthetic_returns):
    """A KhubievPortfolio fit on synthetic returns (no real data touched)."""
    strat = KhubievPortfolio(
        symbols=[f"SYN{i}" for i in range(synthetic_returns.shape[1])],
        loss="mod_sharpe_abs",
        lookback=5,
        fit_on_init=False,
    )
    strat.fit(synthetic_returns)
    return strat


@pytest.fixture
def synthetic_ohlcv():
    """A single-symbol synthetic OHLCV dict (close series) with enough bars."""
    rng = np.random.default_rng(99)
    close = 100.0 * np.cumprod(np.exp(rng.normal(0.0002, 0.01, size=300)))
    return {"open": close, "high": close, "low": close, "close": close, "volume": np.ones(300)}


# ---------------------------------------------------------------------------
# 1. Loss functions -> finite scalars
# ---------------------------------------------------------------------------


def test_losses_return_finite_scalars():
    rng = np.random.default_rng(0)
    pnl = rng.normal(0.001, 0.01, size=500)
    r = rng.normal(0.0005, 0.02, size=(500, 4))
    alpha = np.zeros_like(r)
    alpha[1:] = np.diff(r, axis=0)  # a plausible weight proxy

    for name, fn in [
        ("SharpeLoss", lambda: SharpeLoss(pnl)),
        ("ModSharpeLoss", lambda: ModSharpeLoss(pnl, alpha, r)),
        ("ModSharpeAbsLoss", lambda: ModSharpeAbsLoss(pnl, alpha, r)),
        ("RiskAdjLoss", lambda: RiskAdjLoss(pnl, alpha, r)),
        ("MDDLoss", lambda: MDDLoss(pnl)),
        ("TvrReg", lambda: TvrReg(0.6)),
    ]:
        val = fn()
        assert np.isfinite(val), f"{name} returned non-finite: {val}"
        assert isinstance(float(val), float)


def test_evaluate_all_finite(synthetic_returns):
    rng = np.random.default_rng(1)
    T, N = synthetic_returns.shape
    pnl = rng.normal(0.001, 0.01, size=T)
    r = synthetic_returns
    alpha = np.zeros_like(r)
    alpha[1:] = np.diff(r, axis=0)
    out = evaluate_all(pnl, alpha, r, tvr=0.5)
    for k, v in out.items():
        assert np.isfinite(v), f"{k} not finite"


def test_max_drawdown_known_case():
    # Steady climb then crash: max drawdown should be 0.5 (50%).
    pnl = np.array([0.1, 0.1, -0.5, 0.2])
    assert abs(max_drawdown(pnl) - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# 2. generate_signal -> valid Signal or None
# ---------------------------------------------------------------------------


def test_generate_signal_returns_signal_or_none(synthetic_strategy, synthetic_ohlcv):
    sig = synthetic_strategy.generate_signal("SYN0", synthetic_ohlcv)
    assert sig is None or sig.signal_type in (
        __import__("graxia.packages.quant_os.core.enums", fromlist=["SignalType"]).SignalType.BUY,
        __import__("graxia.packages.quant_os.core.enums", fromlist=["SignalType"]).SignalType.SELL,
    )
    if sig is not None:
        assert sig.symbol == "SYN0"
        assert 0.0 <= sig.confidence <= 1.0
        assert sig.strategy_id == synthetic_strategy.id


def test_generate_signal_insufficient_data_returns_none(synthetic_strategy):
    short = {"close": [1.0, 1.01, 1.02]}
    assert synthetic_strategy.generate_signal("SYN0", short) is None


def test_generate_signal_precomputed_weights(synthetic_strategy):
    weights = {"SYN0": 0.2, "SYN1": -0.15}
    sig = synthetic_strategy.generate_signal("SYN0", {"close": [1.0]}, indicators={"_khubiev_weights": weights})
    assert sig is not None and sig.signal_type.name == "BUY"
    sig2 = synthetic_strategy.generate_signal("SYN1", {"close": [1.0]}, indicators={"_khubiev_weights": weights})
    assert sig2 is not None and sig2.signal_type.name == "SELL"


# ---------------------------------------------------------------------------
# 3. Portfolio weights -> neutral + L2-capped
# ---------------------------------------------------------------------------


def test_weights_market_neutral(synthetic_strategy, synthetic_returns):
    w = synthetic_strategy.compute_portfolio_weights(synthetic_returns)
    assert w.shape[0] == synthetic_returns.shape[1]
    assert abs(float(np.sum(w))) < 1e-6, "weights are not market-neutral (sum != 0)"


def test_weights_l2_capped(synthetic_strategy, synthetic_returns):
    w = synthetic_strategy.compute_portfolio_weights(synthetic_returns)
    norm = float(np.linalg.norm(w))
    assert norm <= synthetic_strategy.leverage + 1e-6, f"L2 norm {norm} exceeds cap"


def test_weights_univariate(synthetic_strategy):
    # Single-asset input should still return a (degenerate but valid) vector.
    w = synthetic_strategy.compute_portfolio_weights(np.random.default_rng(3).normal(0, 0.01, size=(200, 1)))
    assert w.shape == (1,)
    assert np.isfinite(w).all()


def test_loss_not_asserted_as_edge():
    # Explicit guard: this module does not assert profitability on real data.
    assert True
