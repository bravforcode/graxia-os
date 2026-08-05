"""Khubiev Finance-Grounded Portfolio Strategy
============================================

Implements Khubiev et al. "Finance-Grounded Optimization For Algorithmic
Trading" (arXiv 2509.04541) as a :class:`Strategy` subclass.

Pipeline
--------
1. Load the daily returns of the CORE_UNIVERSE via ``load_asset_data``.
2. Train a small, asset-agnostic return-forecasting model (linear regressor)
   by minimizing one of the paper's finance-grounded loss functions
   (see :mod:`khubiev_losses`). Training uses torch autodiff when available
   for exact gradients (including the drawdown term); otherwise it falls back
   to a numpy OLS warm start plus analytic-gradient descent on a smooth loss.
3. At scoring time, the model maps recent cross-sectional features to raw
   per-asset scores. Scores are turned into a *market-neutral* weight vector
   ``w_t`` with ``1^T w_t = 0`` and ``||w_t||_2 <= 1`` (neutralize the mean,
   then L2-scale to unit leverage).
4. ``generate_signal`` returns BUY / SELL / FLAT for a single symbol based on
   whether that asset's (standardized) weight exceeds ``+threshold`` or
   ``-threshold`` (default 0.05).

The full market-neutral portfolio weights are also exposed directly via
:meth:`KhubievPortfolio.compute_portfolio_weights` so callers (and tests) can
verify neutrality and the L2 cap without going through the per-symbol API.

This module creates NEW files only; it does not modify any existing strategy,
ensemble, or data file.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np

try:  # package import (preferred)
    from ..core.enums import SignalType
    from .base import Signal, Strategy, StrategyConfig
    from .khubiev_losses import (
        MDDLoss,
        ModSharpeAbsLoss,
        ModSharpeLoss,
        RiskAdjLoss,
        SharpeLoss,
        TvrReg,
        max_drawdown,
    )
except ImportError:  # standalone `python strategies/khubiev_portfolio.py`
    import sys
    from pathlib import Path

    # `graxia` package lives under repo root "graxia os" (parents[4]);
    # the `scripts` package lives under quant_os (parents[1]).
    _repo_root = str(Path(__file__).resolve().parents[4])
    _quant_os = str(Path(__file__).resolve().parents[1])
    for _p in (_repo_root, _quant_os):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    from graxia.packages.quant_os.core.enums import SignalType
    from graxia.packages.quant_os.strategies.base import Signal, Strategy, StrategyConfig
    from graxia.packages.quant_os.strategies.khubiev_losses import (
        MDDLoss,
        ModSharpeAbsLoss,
        ModSharpeLoss,
        RiskAdjLoss,
        SharpeLoss,
        TvrReg,
        max_drawdown,
    )

try:  # torch is optional -- graceful fallback to numpy
    import torch

    _TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - depends on environment
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers (mirroring path_b_wrappers._ohlcv_to_series / _series_to_signal)
# ---------------------------------------------------------------------------


def _ohlcv_to_close(ohlcv_data: dict[str, list]) -> np.ndarray:
    """Extract a float close-price array from engine OHLCV lists."""
    close = ohlcv_data.get("close")
    if close is None:
        return np.array([], dtype=float)
    return np.asarray(close, dtype=float)


def _to_signal(signed, symbol, strategy_id, threshold, **kwargs) -> Signal | None:
    """Map a signed weight-like quantity to a BUY/SELL/FLAT Signal."""
    if not np.isfinite(float(signed)) or abs(float(signed)) < threshold:
        return None
    sig_type = SignalType.BUY if float(signed) > 0 else SignalType.SELL
    conf = float(min(1.0, abs(float(signed))))
    return Signal.create(
        strategy_id=str(strategy_id),
        symbol=symbol,
        signal_type=sig_type,
        confidence=conf,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class KhubievPortfolio(Strategy):
    """Finance-grounded, market-neutral portfolio strategy.

    Args:
        symbols: Universe to trade. Defaults to a liquid cross-asset set.
        loss: Which finance-grounded loss to train on. One of
            ``sharpe``, ``mod_sharpe``, ``mod_sharpe_abs`` (default),
            ``risk_adj``, ``mdd``.
        lookback: Number of lagged daily returns used as features per asset.
        leverage: Target L2 norm of the weight vector (default 1.0).
        threshold: |weight| above which we emit BUY/SELL (default 0.05).
        lambda_: RiskAdjLoss drawdown weight (default 0.3).
        gamma: RiskAdjLoss tracking-error weight (default 0.01).
        n_epochs: Training steps (torch path). Default 300.
        lr: Learning rate (torch path). Default 1e-3.
        seed: RNG seed for reproducibility.
        fit_on_init: Train on the universe in ``__init__`` (best effort).
    """

    LOSS_FUNCS = {
        "sharpe": SharpeLoss,
        "mod_sharpe": ModSharpeLoss,
        "mod_sharpe_abs": ModSharpeAbsLoss,
        "risk_adj": RiskAdjLoss,
        "mdd": MDDLoss,
    }

    def __init__(
        self,
        symbols: list[str] | None = None,
        loss: str = "mod_sharpe_abs",
        lookback: int = 5,
        leverage: float = 1.0,
        threshold: float = 0.05,
        lambda_: float = 0.3,
        gamma: float = 0.01,
        n_epochs: int = 300,
        lr: float = 1e-3,
        seed: int = 42,
        fit_on_init: bool = True,
        train_fraction: float = 1.0,
    ):
        config = StrategyConfig(
            name="KhubievPortfolio",
            version="1.0.0",
            symbols=symbols
            or ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30", "BTCUSD"],
            timeframes=["D1"],
            risk_per_trade_pct=1.0,
            max_trades_per_day=7,
            require_trend_confirm=False,
        )
        super().__init__(config)
        self.symbols = list(config.symbols)
        if loss not in self.LOSS_FUNCS:
            raise ValueError(f"unknown loss '{loss}'; choose from {list(self.LOSS_FUNCS)}")
        self.loss_name = loss
        self.lookback = int(lookback)
        self.leverage = float(leverage)
        self.threshold = float(threshold)
        self.lambda_ = float(lambda_)
        self.gamma = float(gamma)
        self.n_epochs = int(n_epochs)
        self.lr = float(lr)
        self.seed = int(seed)
        self.train_fraction = float(train_fraction)
        self.eps = 1e-8

        # Trained state (populated by fit()).
        self.model_W: np.ndarray | None = None  # (K*N, N)
        self.model_b: np.ndarray | None = None  # (N,)
        self._rest_mean: np.ndarray | None = None  # mean of cross-asset feature blocks
        self._score_mean: float = 0.0
        self._score_std: float = 1.0
        self._n_assets: int = len(self.symbols)
        self._trained_on: str | None = None
        self._last_loss_value: float | None = None

        if fit_on_init:
            try:
                self.fit()
            except Exception as exc:  # pragma: no cover - data/env dependent
                warnings.warn(
                    f"KhubievPortfolio: fit() failed ({exc!r}); "
                    "strategy will use momentum fallback in generate_signal.",
                    stacklevel=2,
                )

    # -- feature engineering -------------------------------------------------

    def _build_features(self, returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Stack K lagged returns (flattened) -> features; target = next return.

        Returns (X, Y) where X is (T-K, K*N), Y is (T-K, N).
        """
        T, N = returns.shape
        K = self.lookback
        if T <= K + 1:
            raise ValueError(f"need > {K + 1} rows, got {T}")
        X = np.zeros((T - K, K * N), dtype=float)
        Y = np.zeros((T - K, N), dtype=float)
        for t in range(K, T):
            X[t - K] = returns[t - K:t].ravel(order="C")
            Y[t - K] = returns[t]
        return X, Y

    @staticmethod
    def _neutralize_scale(scores: np.ndarray, leverage: float) -> np.ndarray:
        """Neutralize mean, then L2-scale to ``leverage``.

        Guarantees ``sum(w) == 0`` and ``||w||_2 <= leverage + tiny``.
        """
        scores = np.asarray(scores, dtype=float).ravel()
        centered = scores - scores.mean()
        norm = np.linalg.norm(centered)
        if norm < 1e-12:
            return np.zeros_like(centered)
        return centered / norm * leverage

    # -- training ------------------------------------------------------------

    def fit(self, returns: np.ndarray | None = None) -> "KhubievPortfolio":
        """Train the forecasting model.

        If ``returns`` (T, N) is provided it is used directly; otherwise the
        CORE_UNIVERSE daily returns are loaded from disk via
        ``load_asset_data``. Caches the result on the instance.
        """
        if returns is None:
            returns = self._load_universe_returns()
            if self.train_fraction < 1.0:
                n_train = max(self.lookback + 2, int(returns.shape[0] * self.train_fraction))
                returns = returns[:n_train]
            self._trained_on = "universe"
        else:
            returns = np.asarray(returns, dtype=float)
            if returns.ndim == 1:
                returns = returns.reshape(-1, 1)
            self._n_assets = returns.shape[1]
            self._trained_on = "provided"

        X, Y = self._build_features(returns)
        if _TORCH_AVAILABLE:
            self._train_torch(X, Y)
        else:  # pragma: no cover - exercised only without torch
            self._train_numpy(X, Y)

        # Cross-asset feature-block mean (used to fill missing assets in the
        # per-symbol generate_signal path).
        self._rest_mean = X.mean(axis=0).copy()
        # Score statistics for standardizing per-asset weights.
        raw = X @ self.model_W + self.model_b  # (T-K, N)
        self._score_mean = float(np.mean(raw))
        self._score_std = float(np.std(raw)) or 1.0
        return self

    def _load_universe_returns(self) -> np.ndarray:
        """Load CORE_UNIVERSE daily closes and return a stacked log-return matrix."""
        from scripts.edge_search_all import CORE_UNIVERSE, load_asset_data

        symbols = [s for s in self.symbols if s in CORE_UNIVERSE] or list(CORE_UNIVERSE)
        series: list[np.ndarray] = []
        used: list[str] = []
        for sym in symbols:
            try:
                df = load_asset_data(sym)
            except Exception:
                continue
            if "close" not in df.columns:
                continue
            close = df["close"].to_numpy(dtype=float)
            if len(close) < self.lookback + 2:
                continue
            ret = np.diff(np.log(close))
            series.append(ret)
            used.append(sym)
        if not series:
            raise RuntimeError("no universe returns could be loaded")
        self.symbols = used
        self._n_assets = len(used)
        min_len = min(len(s) for s in series)
        return np.column_stack([s[-min_len:] for s in series])

    def _train_torch(self, X: np.ndarray, Y: np.ndarray) -> None:
        """Exact-gradient training via torch autodiff (drawdown included)."""
        Xt = torch.tensor(X, dtype=torch.float64)
        Yt = torch.tensor(Y, dtype=torch.float64)
        D, N = X.shape[1], Y.shape[1]
        rng = np.random.default_rng(self.seed)
        W = torch.tensor(
            rng.normal(0, 0.01, size=(D, N)), dtype=torch.float64, requires_grad=True
        )
        b = torch.zeros(N, dtype=torch.float64, requires_grad=True)
        opt = torch.optim.Adam([W, b], lr=self.lr)
        last = None
        for _ in range(self.n_epochs):
            opt.zero_grad()
            Z = Xt @ W + b
            Zm = Z - Z.mean(dim=1, keepdim=True)
            nrm = Zm.norm(dim=1, keepdim=True).clamp_min(self.eps)
            Wt = Zm / nrm
            pnl = (Wt * Yt).sum(dim=1)
            loss = self._torch_loss(pnl, Wt, Yt)
            if not torch.isfinite(loss):
                break
            last = loss.item()
            loss.backward()
            opt.step()
        self._last_loss_value = float(last) if last is not None else None
        self.model_W = W.detach().numpy().copy()
        self.model_b = b.detach().numpy().copy()

    def _torch_loss(self, pnl, alpha, r):
        var = pnl.var(unbiased=False) + self.eps
        if self.loss_name == "sharpe":
            return pnl.mean() / var
        if self.loss_name == "mod_sharpe":
            return (alpha - r).mean() * pnl.mean() / var
        if self.loss_name == "mod_sharpe_abs":
            return (alpha - r).abs().mean() * pnl.mean() / var
        if self.loss_name == "risk_adj":
            dd = self._torch_maxdd(pnl)
            te = ((alpha - r) ** 2).mean()
            return -pnl.mean() + self.lambda_ * dd + self.gamma * te
        if self.loss_name == "mdd":
            return -self._torch_dd_min(pnl)
        raise ValueError(self.loss_name)

    @staticmethod
    def _torch_maxdd(pnl):
        curve = torch.cumsum(pnl, dim=0)
        runmax = torch.cummax(curve, dim=0).values
        dd = curve - runmax
        return -dd.min()

    @staticmethod
    def _torch_dd_min(pnl):
        curve = torch.cumsum(pnl, dim=0)
        runmax = torch.cummax(curve, dim=0).values
        return (curve - runmax).min()

    def _train_numpy(self, X: np.ndarray, Y: np.ndarray) -> None:  # pragma: no cover
        """Numpy fallback: OLS warm start + analytic-gradient descent.

        Uses a smooth finance-grounded loss (ModSharpeAbs). For risk_adj/mdd the
        exact drawdown is non-smooth, so we substitute ModSharpeAbs and warn.
        """
        D, N = X.shape[1], Y.shape[1]
        try:
            W = np.linalg.pinv(X) @ Y
        except Exception:
            W = np.zeros((D, N))
        b = Y.mean(axis=0) - X.mean(axis=0) @ W
        if self.loss_name in ("risk_adj", "mdd"):
            warnings.warn(
                "numpy fallback trains on ModSharpeAbsLoss (torch unavailable "
                "for exact RiskAdjLoss/MDDLoss drawdown gradients).",
                stacklevel=2,
            )
        rng = np.random.default_rng(self.seed)
        lr = self.lr
        last = None
        for _ in range(self.n_epochs):
            Z = X @ W + b
            Zm = Z - Z.mean(axis=1, keepdims=True)
            nrm = np.linalg.norm(Zm, axis=1, keepdims=True)
            nrm = np.where(nrm < self.eps, self.eps, nrm)
            Wt = Zm / nrm
            pnl = (Wt * Y).sum(axis=1)
            gW, gb = self._numpy_grad(X, Y, Wt, pnl)
            if not (np.all(np.isfinite(gW)) and np.all(np.isfinite(gb))):
                break
            W = W - lr * gW
            b = b - lr * gb
            last = float(np.mean(pnl))
        self._last_loss_value = last
        self.model_W = W
        self.model_b = b

    def _numpy_grad(self, X, Y, Wt, pnl):  # pragma: no cover
        """Analytic gradient of ModSharpeAbsLoss w.r.t. (W, b)."""
        T, N = Wt.shape
        mean_pnl = pnl.mean()
        var = pnl.var() + self.eps
        sgn = np.sign(Wt - Y)
        A = np.abs(Wt - Y).mean()
        L = A * mean_pnl / var
        dL_dS = A / var
        dL_dV = -L / var
        dL_dA = mean_pnl / var
        M = np.eye(N) - np.ones((N, N)) / N
        gW = np.zeros((X.shape[1], N))
        gb = np.zeros(N)
        I = np.eye(N)
        for t in range(T):
            w = Wt[t]
            r = Y[t]
            x = X[t]
            n = np.linalg.norm(w - w.mean()) + self.eps
            dw_dz = M @ (I - np.outer(w, w)) / n
            dL_dpnl = dL_dS / T + dL_dV * (2.0 / T) * (pnl[t] - mean_pnl)
            dL_dw = dL_dA * (1.0 / T) * sgn[t] + dL_dpnl * r
            dL_dz = dw_dz @ dL_dw
            gW += np.outer(x, dL_dz)
            gb += dL_dz
        return gW / max(T, 1), gb / max(T, 1)

    # -- scoring -------------------------------------------------------------

    def compute_portfolio_weights(self, returns: np.ndarray) -> np.ndarray:
        """Return the market-neutral weight vector for the latest bar.

        Args:
            returns: (T, N) asset-return matrix (any length > lookback).

        Returns:
            w (N,): ``sum(w) == 0`` and ``||w||_2 <= leverage``.
        """
        returns = np.asarray(returns, dtype=float)
        if returns.ndim == 1:
            returns = returns.reshape(-1, 1)
        mismatch = (
            self.model_W is None
            or self.model_b is None
            or returns.shape[1] != self.model_W.shape[1]
        )
        if mismatch:
            # Untrained, or the input's asset count differs from the trained
            # universe: fall back to a momentum-style score from the last row.
            scores = returns[-1]
        else:
            X, _ = self._build_features(returns)
            last = X[-1:]
            raw = last @ self.model_W + self.model_b  # (1, N)
            scores = raw.ravel()
        return self._neutralize_scale(scores, self.leverage)

    def _asset_score(self, symbol: str, ohlcv_data: dict[str, list]) -> float | None:
        """Reconstruct this asset's (standardized) portfolio weight from its
        own OHLCV, filling the other assets' feature blocks with their training
        mean. Returns a signed, standardized quantity (None if untrainable)."""
        close = _ohlcv_to_close(ohlcv_data)
        if close.size < self.lookback + 2:
            return None
        ret = np.diff(np.log(close))
        if ret.size < self.lookback:
            return None
        idx = self.symbols.index(symbol) if symbol in self.symbols else 0
        K = self.lookback
        N = self._n_assets
        x_i = ret[-K:]
        full = np.zeros(K * N, dtype=float)
        if self._rest_mean is not None:
            full[:] = self._rest_mean
        full[idx * K : (idx + 1) * K] = x_i
        if self.model_W is None or self.model_b is None:
            return None
        score_i = float(full @ self.model_W[:, idx] + self.model_b[idx])
        return (score_i - self._score_mean) / max(self._score_std, self.eps)

    # -- Strategy interface --------------------------------------------------

    def required_features(self) -> list[str]:
        return ["khubiev_weights"]

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict[str, Any] | None = None,
        regime=None,
        **kwargs,
    ) -> Signal | None:
        # Fast path: engine may pre-compute the full cross-sectional weights.
        if indicators and "_khubiev_weights" in indicators:
            weights = indicators["_khubiev_weights"]
            if isinstance(weights, dict) and symbol in weights:
                signed = float(weights[symbol])
                return _to_signal(signed, symbol, self.id, self.threshold, regime=regime)
            if isinstance(weights, (list, np.ndarray)) and symbol in self.symbols:
                i = self.symbols.index(symbol)
                signed = float(np.asarray(weights).ravel()[i])
                return _to_signal(signed, symbol, self.id, self.threshold, regime=regime)

        signed = self._asset_score(symbol, ohlcv_data)
        if signed is None:
            return None
        return _to_signal(signed, symbol, self.id, self.threshold, regime=regime)


if __name__ == "__main__":
    # Standalone smoke check (no pytest required).
    rng = np.random.default_rng(7)
    T, N = 1200, 6
    mu = rng.normal(0.0, 0.002, size=N)
    returns = rng.normal(mu, 0.01, size=(T, N))

    strat = KhubievPortfolio(symbols=[f"ASSET{i}" for i in range(N)], fit_on_init=False)
    strat.fit(returns)
    w = strat.compute_portfolio_weights(returns)
    assert abs(float(np.sum(w))) < 1e-6, "weights not market-neutral"
    assert np.linalg.norm(w) <= strat.leverage + 1e-6, "L2 cap breached"
    print("weights sum   =", float(np.sum(w)))
    print("weights |w|_2 =", float(np.linalg.norm(w)))

    close = np.cumprod(np.exp(np.concatenate([[0.0], returns[:, 0]]))) * 100.0
    ohlcv = {"close": close.tolist()}
    sig = strat.generate_signal("ASSET0", ohlcv)
    print("sample signal =", sig)

    print(f"torch available: {_TORCH_AVAILABLE}")
    print("KhubievPortfolio smoke OK")
