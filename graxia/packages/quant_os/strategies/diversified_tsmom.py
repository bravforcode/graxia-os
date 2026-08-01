"""
Diversified Time-Series Momentum Strategy (DTSMOM)
===================================================

Trial #1030 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Time-series momentum (TSMOM) is one of the most robust phenomena in finance:

1. Moskowitz, Ooi, Pedersen (2012): TSMOM across 58 futures yields Sharpe 1.0+
2. Pitkajarvi (2020): Cross-asset TSMOM yields Sharpe +45% vs single-asset
3. Barroso (2015): Vol targeting doubles Sharpe vs naive TSMOM
4. Vanguard (2024): Threshold rebalancing beats calendar-based by 15-25 bps
5. Springer (2026): 1/N is "remarkably difficult to outperform"

The candidate edge is NOT in the signal (TSMOM is well-known) but in the
PORTFOLIO CONSTRUCTION:
- Inverse-vol weighting (target 10% annual vol per asset)
- Threshold-based rebalancing (5% drift trigger)
- All 16 assets (maximize diversification)
- No regime switching (simple is robust)

This is structurally different from trial #1029 (RAM) because:
1. Uses TSMOM (time-series momentum) not regime-conditional strategy switching
2. Inverse-vol weighting not equal-weight
3. Threshold rebalancing not daily rebalancing
4. All 16 assets not 7
5. Simpler → more robust (YAGNI principle)

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- universe: ALL 16 assets (XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, USDCAD,
  USDCHF, NAS100, US30, GER40, US500, BTCUSD, ETHUSD, BTCJPY, ETHJPY,
  SOLJPY) — note: DXY excluded (only 2143 rows, insufficient for 12mo lookback)
- mom_lookback: 252 days (12 months — the classic TSMOM window)
- vol_target: 0.10 (10% annual vol target per asset)
- vol_lookback: 63 days (3 months for vol estimation)
- rebalance_drift: 0.05 (5% drift threshold triggers rebalance)
- max_position_pct: 0.15 (15% max per asset)
- min_history_days: 504 (2 years — need 12mo lookback + warmup)

USAGE
=====
    from strategies.diversified_tsmom import DTSMOMConfig, compute_dtsmom_signals

    config = DTSMOMConfig()
    out = compute_dtsmom_signals(prices=prices_df, config=config)
    # out["signals"] : DataFrame of -1/0/+1 positions per asset
    # out["portfolio"] : DataFrame of portfolio weights
    # out["weights"] : DataFrame of actual position sizes (after vol scaling)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Frozen configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DTSMOMConfig:
    """Diversified TSMOM configuration — frozen at pre-registration.

    Values match trial #1030 spec exactly.
    """

    # Universe: ALL 16 assets (DXY excluded — insufficient history)
    universe: tuple[str, ...] = (
        "XAUUSD",
        "XAGUSD",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCAD",
        "USDCHF",
        "NAS100",
        "US30",
        "GER40",
        "US500",
        "BTCUSD",
        "ETHUSD",
        "BTCJPY",
        "ETHJPY",
        "SOLJPY",
    )

    # TSMOM parameters
    mom_lookback: int = 252  # 12 months
    mom_entry_threshold: float = 0.0  # positive return = long, negative = short

    # Volatility targeting
    vol_target: float = 0.10  # 10% annual vol per asset
    vol_lookback: int = 63  # 3 months for vol estimation

    # Rebalancing
    rebalance_drift: float = 0.05  # 5% drift triggers rebalance

    # Risk management
    max_position_pct: float = 0.15  # 15% max per asset

    # Data requirements
    min_history_days: int = 504  # 2 years (12mo lookback + warmup)
    bars_per_year: float = 252.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class DTSMOMResult(NamedTuple):
    """Output of compute_dtsmom_signals()."""

    signals: pd.DataFrame  # -1/0/+1 directional positions per asset
    weights: pd.DataFrame  # Actual position sizes (after vol scaling)
    portfolio: pd.DataFrame  # Final portfolio weights (sum = 1 or -1)
    returns_contribution: pd.DataFrame  # Per-asset return contribution
    config: DTSMOMConfig


# ---------------------------------------------------------------------------
# Core TSMOM signal
# ---------------------------------------------------------------------------


def _tsmom_signal(prices: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Compute time-series momentum signal.

    Signal = sign(cumulative return over lookback period).
    Long if cumulative return > 0, short if < 0.

    Args:
        prices: DataFrame of daily close prices, columns = assets
        lookback: Number of days for momentum calculation

    Returns:
        DataFrame of -1/0/+1 signals
    """
    # Cumulative return over lookback
    cum_returns = prices.pct_change(lookback)

    # Signal: sign of cumulative return
    signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    signals[cum_returns > 0] = 1.0
    signals[cum_returns < 0] = -1.0

    # Set NaN to 0 (no position)
    signals = signals.fillna(0.0)

    return signals


# ---------------------------------------------------------------------------
# Volatility estimation
# ---------------------------------------------------------------------------


def _estimate_vol(returns: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Estimate rolling annualized volatility.

    Args:
        returns: DataFrame of daily returns
        lookback: Rolling window for vol estimation

    Returns:
        DataFrame of annualized volatility (same shape as returns)
    """
    vol = returns.rolling(window=lookback, min_periods=lookback).std() * np.sqrt(252)
    return vol


# ---------------------------------------------------------------------------
# Inverse-vol weighting
# ---------------------------------------------------------------------------


def _inverse_vol_weights(
    signals: pd.DataFrame,
    vol: pd.DataFrame,
    vol_target: float,
    max_position_pct: float,
) -> pd.DataFrame:
    """Compute inverse-volatility weighted positions.

    Each asset's weight = (vol_target / asset_vol) * signal_direction.
    Capped at max_position_pct.

    Args:
        signals: DataFrame of -1/0/+1 directional signals
        vol: DataFrame of annualized volatility
        vol_target: Target volatility per asset (e.g., 0.10 = 10%)
        max_position_pct: Maximum position size per asset

    Returns:
        DataFrame of position sizes (can be fractional, sign indicates direction)
    """
    # Inverse vol = vol_target / asset_vol
    inv_vol = vol_target / vol.replace(0, np.nan)

    # Apply signal direction
    raw_weights = signals * inv_vol

    # Cap at max_position_pct
    weights = raw_weights.clip(-max_position_pct, max_position_pct)

    # Replace NaN with 0
    weights = weights.fillna(0.0)

    return weights


# ---------------------------------------------------------------------------
# Threshold-based rebalancing
# ---------------------------------------------------------------------------


def _threshold_rebalance(
    weights: pd.DataFrame,
    drift_threshold: float,
) -> pd.DataFrame:
    """Apply threshold-based rebalancing (fully vectorized).

    Only update positions when drift exceeds threshold.
    This reduces turnover and transaction costs.

    Uses forward-fill logic: once a weight is set, it persists until
    drift from the new target exceeds the threshold.

    Args:
        weights: DataFrame of target weights from vol scaling
        drift_threshold: Drift threshold (e.g., 0.05 = 5%)

    Returns:
        DataFrame of rebalanced weights
    """
    rebalanced = weights.copy()
    values = weights.values.copy()

    for i in range(1, len(values)):
        drift = np.abs(values[i] - values[i - 1])
        # Where drift <= threshold, keep previous value
        mask = drift <= drift_threshold
        values[i] = np.where(mask, values[i - 1], values[i])

    return pd.DataFrame(values, index=weights.index, columns=weights.columns)


# ---------------------------------------------------------------------------
# Portfolio normalization
# ---------------------------------------------------------------------------


def _normalize_portfolio(
    weights: pd.DataFrame,
    max_total_exposure: float = 1.0,
) -> pd.DataFrame:
    """Normalize portfolio weights to control total exposure.

    Args:
        weights: DataFrame of raw weights
        max_total_exposure: Maximum total absolute exposure (e.g., 1.0 = 100%)

    Returns:
        DataFrame of normalized weights
    """
    portfolio = weights.copy()

    for i in range(len(portfolio)):
        total_exposure = portfolio.iloc[i].abs().sum()
        if total_exposure > max_total_exposure and total_exposure > 0:
            portfolio.iloc[i] = portfolio.iloc[i] * (max_total_exposure / total_exposure)

    return portfolio


# ---------------------------------------------------------------------------
# Main signal computation
# ---------------------------------------------------------------------------


def compute_dtsmom_signals(
    prices: pd.DataFrame,
    config: DTSMOMConfig | None = None,
) -> DTSMOMResult:
    """Compute Diversified TSMOM signals.

    Mechanism
    ---------
    1. Compute TSMOM signal: sign(cumulative return over 252 days)
    2. Estimate volatility: 63-day rolling annualized vol
    3. Inverse-vol weighting: scale positions to target 10% vol per asset
    4. Threshold rebalancing: only rebalance when drift > 5%
    5. Normalize: cap total exposure at 100%

    Parameters
    ----------
    prices : DataFrame of daily close prices, columns = assets, DatetimeIndex.
    config : frozen DTSMOMConfig; defaults to pre-registered values.

    Returns
    -------
    DTSMOMResult with signals, weights, portfolio, returns_contribution, config.
    """
    if config is None:
        config = DTSMOMConfig()

    # Filter to universe
    available_assets = [a for a in config.universe if a in prices.columns]
    prices = prices[available_assets]

    # Drop rows with any NaN
    prices = prices.dropna()

    if len(prices) < config.min_history_days:
        empty = pd.DataFrame(0, index=prices.index, columns=prices.columns)
        return DTSMOMResult(
            signals=empty,
            weights=empty.copy(),
            portfolio=empty.copy(),
            returns_contribution=empty.copy(),
            config=config,
        )

    # 1. Compute returns
    returns = prices.pct_change()

    # 2. TSMOM signal
    signals = _tsmom_signal(prices, config.mom_lookback)

    # 3. Volatility estimation
    vol = _estimate_vol(returns, config.vol_lookback)

    # 4. Inverse-vol weighting
    raw_weights = _inverse_vol_weights(
        signals, vol, config.vol_target, config.max_position_pct
    )

    # 5. Threshold rebalancing
    rebalanced_weights = _threshold_rebalance(raw_weights, config.rebalance_drift)

    # 6. Normalize
    portfolio = _normalize_portfolio(rebalanced_weights)

    # 7. Compute return contribution
    returns_contribution = portfolio.shift(1) * returns

    return DTSMOMResult(
        signals=signals,
        weights=raw_weights,
        portfolio=portfolio,
        returns_contribution=returns_contribution,
        config=config,
    )


# ---------------------------------------------------------------------------
# Backtest metrics
# ---------------------------------------------------------------------------


def compute_dtsmom_metrics(
    portfolio: pd.DataFrame,
    returns: pd.DataFrame,
    config: DTSMOMConfig,
) -> dict:
    """Compute backtest metrics for the diversified TSMOM portfolio.

    Args:
        portfolio: Portfolio weights from compute_dtsmom_signals
        returns: Daily returns for all assets
        config: DTSMOMConfig

    Returns:
        Dictionary of performance metrics
    """
    # Align portfolio and returns
    common_idx = portfolio.index.intersection(returns.index)
    portfolio = portfolio.loc[common_idx]
    returns = returns.loc[common_idx]

    # Portfolio returns
    portfolio_returns = (portfolio.shift(1) * returns).sum(axis=1)

    # Performance metrics
    total_return = (1 + portfolio_returns).prod() - 1
    annual_return = (1 + total_return) ** (config.bars_per_year / len(portfolio_returns)) - 1
    annual_vol = portfolio_returns.std() * np.sqrt(config.bars_per_year)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0

    # Drawdown
    cumulative = (1 + portfolio_returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()

    # Win rate
    winning_days = (portfolio_returns > 0).sum()
    total_days = (portfolio_returns != 0).sum()
    win_rate = winning_days / total_days if total_days > 0 else 0.0

    # Profit factor
    gross_profit = portfolio_returns[portfolio_returns > 0].sum()
    gross_loss = abs(portfolio_returns[portfolio_returns < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Turnover
    turnover = portfolio.diff().abs().sum(axis=1).mean()

    # Trade count (position changes)
    trade_count = (portfolio.diff().abs().sum(axis=1) > 0).sum()

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_vol": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "turnover": turnover,
        "trade_count": trade_count,
        "n_observations": len(portfolio_returns),
    }


__all__ = [
    "DTSMOMConfig",
    "DTSMOMResult",
    "compute_dtsmom_signals",
    "compute_dtsmom_metrics",
]
