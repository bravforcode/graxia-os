"""
Finance-Grounded Loss Functions (Khubiev et al., arXiv 2509.04541)
===============================================================

Asset-agnostic, numpy implementations of the portfolio loss functions from
"Finance-Grounded Optimization For Algorithmic Trading".

All functions accept array-like inputs and return a single finite scalar
(unless the input is degenerate, in which case they degrade gracefully to 0.0).

Conventions
-----------
pnl : portfolio returns per period, 1-D array (T,)
alpha : portfolio weights per period, 2-D array (T, N)  (the "w_t")
r    : asset returns per period,      2-D array (T, N)  (the "r_t")
eps  : numerical stabilizer for variance denominators (default 1e-8)

The losses are written to be *minimized*. Where a formula defines a quantity
that should be *maximized* (e.g. the Sharpe ratio), the loss is the negative
of that quantity; the functions here return exactly the formula given in the
paper/spec so the caller can negate as needed.
"""

from __future__ import annotations

from typing import Union

import numpy as np

ArrayLike = Union[np.ndarray, list, tuple]


def _as1d(a: ArrayLike) -> np.ndarray:
    """Coerce input to a flat float ndarray."""
    return np.asarray(a, dtype=float).ravel()


def _as2d(a: ArrayLike) -> np.ndarray:
    """Coerce input to a 2-D float ndarray (at least one column)."""
    arr = np.asarray(a, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


def _cum_max(x: np.ndarray) -> np.ndarray:
    """Running maximum (inclusive) along the 1-D array."""
    return np.maximum.accumulate(x)


def max_drawdown(pnl: ArrayLike) -> float:
    """Positive maximum drawdown magnitude of a return stream.

    DD_t = C_t - max_{u<=t} C_u,  C_t = cumsum(pnl)
    max_drawdown = -min_t DD_t   (>= 0)
    """
    pnl = _as1d(pnl)
    if pnl.size == 0:
        return 0.0
    curve = np.cumsum(pnl)
    dd = curve - _cum_max(curve)
    return float(-dd.min())


def drawdown_path(pnl: ArrayLike) -> np.ndarray:
    """Full drawdown path DD_t (<= 0) for a return stream."""
    pnl = _as1d(pnl)
    if pnl.size == 0:
        return np.zeros(0)
    curve = np.cumsum(pnl)
    return curve - _cum_max(curve)


def sharpe_ratio(pnl: ArrayLike, eps: float = 1e-8) -> float:
    """Mean return divided by variance (the Sharpe-like numerator/denominator)."""
    pnl = _as1d(pnl)
    if pnl.size == 0:
        return 0.0
    return float(np.mean(pnl) / (np.var(pnl) + eps))


def SharpeLoss(pnl: ArrayLike, eps: float = 1e-8) -> float:
    """SharpeLoss = E[pnl] / (Var(pnl) + eps).

    Maximize (minimize the negative of) this quantity.
    """
    return sharpe_ratio(pnl, eps)


def ModSharpeLoss(pnl: ArrayLike, alpha: ArrayLike, r: ArrayLike, eps: float = 1e-8) -> float:
    """ModSharpeLoss = E[alpha - r] * E[pnl] / (Var(pnl) + eps).

    E[alpha - r] is the expected tracking gap between portfolio weights and
    asset returns (a measure of how "active" the book is).
    """
    pnl = _as1d(pnl)
    alpha = _as2d(alpha)
    r = _as2d(r)
    tracking = float(np.mean(alpha - r))
    return float(tracking * np.mean(pnl) / (np.var(pnl) + eps))


def ModSharpeAbsLoss(pnl: ArrayLike, alpha: ArrayLike, r: ArrayLike, eps: float = 1e-8) -> float:
    """ModSharpeAbsLoss = E[|alpha - r|] * E[pnl] / (Var(pnl) + eps).

    Like ModSharpeLoss but uses the absolute tracking gap (robust to sign).
    """
    pnl = _as1d(pnl)
    alpha = _as2d(alpha)
    r = _as2d(r)
    tracking = float(np.mean(np.abs(alpha - r)))
    return float(tracking * np.mean(pnl) / (np.var(pnl) + eps))


def RiskAdjLoss(
    pnl: ArrayLike,
    alpha: ArrayLike,
    r: ArrayLike,
    lambda_: float = 0.3,
    gamma: float = 0.01,
    eps: float = 1e-8,
) -> float:
    """RiskAdjLoss = -E[pnl] + lambda*DrawDown + gamma*E[(alpha - r)^2].

    -E[pnl]        : reward (lower loss => higher expected return)
    lambda*DrawDown: penalize the (positive) maximum drawdown magnitude
    gamma*E[(..)^2]: penalize mean squared tracking error vs asset returns

    Defaults: lambda=0.3, gamma=0.01.
    """
    pnl = _as1d(pnl)
    alpha = _as2d(alpha)
    r = _as2d(r)
    mean_pnl = float(np.mean(pnl))
    drawdown = max_drawdown(pnl)
    tracking = float(np.mean((alpha - r) ** 2))
    return float(-mean_pnl + lambda_ * drawdown + gamma * tracking)


def MDDLoss(pnl: ArrayLike, eps: float = 1e-8) -> float:
    """MDDLoss = -min_t DD_t, with DD_t = C_t - max_{u<=t} C_u, C_t = cumsum(pnl).

    Equivalent to the positive maximum-drawdown magnitude.
    """
    pnl = _as1d(pnl)
    if pnl.size == 0:
        return 0.0
    curve = np.cumsum(pnl)
    dd = curve - _cum_max(curve)
    return float(-dd.min())


def TvrReg(
    tvr: ArrayLike,
    lambda_: float = 1.0,
    tb: float = 1.0,
    bb: float = 0.3,
    eps: float = 1e-8,
) -> float:
    """Band Turnover Regularization.

    TvrReg = lambda * (max(0, tvr - tb) + max(0, bb - tvr))

    Penalizes portfolio turnover `tvr` when it exits the band [bb, tb].
    Inside the band the penalty is zero. Defaults: lambda=1.0, tb=1.0, bb=0.3.
    """
    tvr = float(np.asarray(tvr, dtype=float).mean())
    return float(lambda_ * (max(0.0, tvr - tb) + max(0.0, bb - tvr)))


def evaluate_all(
    pnl: ArrayLike,
    alpha: ArrayLike,
    r: ArrayLike,
    tvr: float | None = None,
    lambda_: float = 0.3,
    gamma: float = 0.01,
) -> dict[str, float]:
    """Convenience: compute every loss on a single (pnl, alpha, r) sample.

    Returns a dict of loss_name -> scalar. Useful for reporting / sanity checks.
    """
    pnl = _as1d(pnl)
    alpha = _as2d(alpha)
    r = _as2d(r)
    out: dict[str, float] = {
        "SharpeLoss": SharpeLoss(pnl),
        "ModSharpeLoss": ModSharpeLoss(pnl, alpha, r),
        "ModSharpeAbsLoss": ModSharpeAbsLoss(pnl, alpha, r),
        "RiskAdjLoss": RiskAdjLoss(pnl, alpha, r, lambda_=lambda_, gamma=gamma),
        "MDDLoss": MDDLoss(pnl),
    }
    if tvr is not None:
        out["TvrReg"] = TvrReg(tvr)
    return out


if __name__ == "__main__":
    # Smoke check: synthetic, finite, deterministic.
    rng = np.random.default_rng(0)
    pnl = rng.normal(0.001, 0.01, size=500)
    r = rng.normal(0.0005, 0.02, size=(500, 4))
    alpha = np.zeros_like(r)
    alpha[1:] = np.diff(r, axis=0)  # a plausible weight proxy
    res = evaluate_all(pnl, alpha, r, tvr=0.6)
    for k, v in res.items():
        assert np.isfinite(v), f"{k} not finite"
        print(f"{k:18s} = {v:.6f}")
    print("khubiev_losses OK")
