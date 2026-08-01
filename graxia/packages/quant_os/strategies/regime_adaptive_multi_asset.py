"""
Regime-Adaptive Multi-Asset Strategy (RAM) — Volatility-Based Regime
====================================================================

Trial #1029 in the quant_os edge-search ledger.

ECONOMIC RATIONALE
==================
Markets alternate between two regimes:
1. Low-volatility regime: Calm, trending markets. Momentum works.
2. High-volatility regime: Chaotic, mean-reverting markets. Mean-reversion works.

The candidate edge is regime-conditional strategy selection:
- Detect regime via cross-asset volatility analysis (not correlation)
- Switch between momentum (low-vol) and mean-reversion (high-vol) based on regime
- Apply to multiple assets simultaneously with equal-weight diversification

This is structurally different from all REJECTED trials because:
1. Uses volatility-based regime detection (not correlation-based)
2. Switches strategy type based on regime (not just position sizing)
3. Diversifies across multiple assets (not single-asset bets)

PRE-REGISTERED PARAMETERS (FROZEN)
===================================
- universe: 7 assets (XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30)
- vol_lookback_short: 20 days (short-term volatility)
- vol_lookback_long: 200 days (long-term volatility reference)
- vol_low_threshold: 0.7 (short/long < 0.7 = low vol)
- vol_high_threshold: 1.3 (short/long > 1.3 = high vol)
- mom_lookback: 20 days
- mom_entry_z: 1.0 (z-score entry for momentum)
- mr_lookback: 20 days
- mr_entry_z: 2.0 (z-score entry for mean-reversion)
- max_position_pct: 0.15 (15% max per asset)
- stop_loss_atr: 2.0
- take_profit_atr: 3.0

USAGE
=====
    from strategies.regime_adaptive_multi_asset import RAMConfig, compute_ram_signals

    config = RAMConfig()
    out = compute_ram_signals(
        prices=prices_df,  # DataFrame of daily close prices
        config=config,
    )
    # out["signals"] : DataFrame of -1/0/+1 positions per asset
    # out["regime"] : Series of "low_vol"/"high_vol"/"normal"
    # out["portfolio"] : DataFrame of portfolio weights
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
class RAMConfig:
    """Regime-Adaptive Multi-Asset configuration — frozen at pre-registration.

    Values match trial #1029 spec exactly.
    """

    # Universe: 7 assets with sufficient history
    universe: tuple[str, ...] = (
        "XAUUSD",
        "XAGUSD",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "NAS100",
        "US30",
    )

    # Volatility regime detection parameters
    vol_lookback_short: int = 20
    vol_lookback_long: int = 200
    vol_low_threshold: float = 0.7  # short/long < 0.7 = low vol
    vol_high_threshold: float = 1.3  # short/long > 1.3 = high vol

    # Momentum parameters (used in low-vol regime)
    mom_lookback: int = 20
    mom_entry_z: float = 1.0

    # Mean-reversion parameters (used in high-vol regime)
    mr_lookback: int = 20
    mr_entry_z: float = 2.0

    # Risk management
    max_position_pct: float = 0.15
    stop_loss_atr: float = 2.0
    take_profit_atr: float = 3.0

    # Data requirements
    min_history_days: int = 252
    bars_per_year: float = 252.0


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class RAMResult(NamedTuple):
    """Output of compute_ram_signals()."""

    signals: pd.DataFrame  # -1/0/+1 positions per asset
    regime: pd.Series  # "low_vol"/"high_vol"/"normal"
    regime_score: pd.Series  # Vol ratio (short/long)
    portfolio: pd.DataFrame  # Portfolio weights (equal-weight across active)
    config: RAMConfig


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------


def _annualized_vol(returns: pd.Series, window: int) -> pd.Series:
    """Calculate rolling annualized volatility."""
    return returns.rolling(window=window, min_periods=window).std() * np.sqrt(252)


def _detect_regime(
    returns_matrix: pd.DataFrame,
    vol_lookback_short: int,
    vol_lookback_long: int,
    vol_low_threshold: float,
    vol_high_threshold: float,
) -> tuple[pd.Series, pd.Series]:
    """Detect regime from cross-asset volatility analysis.

    Args:
        returns_matrix: DataFrame of daily returns, columns = assets
        vol_lookback_short: Short-term volatility window
        vol_lookback_long: Long-term volatility reference
        vol_low_threshold: Short/long < this = low vol
        vol_high_threshold: Short/long > this = high vol

    Returns:
        Tuple of (regime_series, regime_score_series)
    """
    # Compute volatility for each asset
    vol_short = returns_matrix.rolling(
        window=vol_lookback_short, min_periods=vol_lookback_short
    ).std() * np.sqrt(252)

    vol_long = returns_matrix.rolling(
        window=vol_lookback_long, min_periods=vol_lookback_long
    ).std() * np.sqrt(252)

    # Compute vol ratio (short/long) for each asset
    vol_ratio = vol_short / vol_long.replace(0, np.nan)

    # Average vol ratio across assets
    avg_vol_ratio = vol_ratio.mean(axis=1)

    # Classify regime
    regimes = []
    for i in range(len(avg_vol_ratio)):
        ratio = avg_vol_ratio.iloc[i]
        if np.isnan(ratio):
            regimes.append("normal")
        elif ratio < vol_low_threshold:
            regimes.append("low_vol")
        elif ratio > vol_high_threshold:
            regimes.append("high_vol")
        else:
            regimes.append("normal")

    regime_series = pd.Series(
        regimes, index=returns_matrix.index, name="regime"
    )
    score_series = pd.Series(
        avg_vol_ratio.values, index=returns_matrix.index, name="regime_score"
    )

    return regime_series, score_series


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------


def _generate_momentum_signals(
    prices: pd.DataFrame,
    lookback: int,
    entry_z: float,
) -> pd.DataFrame:
    """Generate momentum signals (buy winners, sell losers).

    Used in low-vol regime.
    """
    signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

    returns = prices.pct_change()

    for asset in prices.columns:
        for i in range(lookback, len(prices)):
            window = returns[asset].iloc[i - lookback : i]
            current_return = returns[asset].iloc[i]

            if window.std() > 0:
                z = (current_return - window.mean()) / window.std()

                if z > entry_z:
                    signals.iloc[i][asset] = 1.0  # Long
                elif z < -entry_z:
                    signals.iloc[i][asset] = -1.0  # Short

    return signals


def _generate_mean_reversion_signals(
    prices: pd.DataFrame,
    lookback: int,
    entry_z: float,
) -> pd.DataFrame:
    """Generate mean-reversion signals (buy oversold, sell overbought).

    Used in high-vol regime.
    """
    signals = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

    for asset in prices.columns:
        for i in range(lookback, len(prices)):
            window = prices[asset].iloc[i - lookback : i]
            current_price = prices[asset].iloc[i]

            if window.std() > 0:
                z = (current_price - window.mean()) / window.std()

                if z < -entry_z:
                    signals.iloc[i][asset] = 1.0  # Long (oversold)
                elif z > entry_z:
                    signals.iloc[i][asset] = -1.0  # Short (overbought)

    return signals


# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------


def _construct_portfolio(
    signals: pd.DataFrame,
    max_position_pct: float,
) -> pd.DataFrame:
    """Equal-weight portfolio across all assets with positions.

    Args:
        signals: DataFrame of -1/0/+1 positions per asset
        max_position_pct: Maximum position size per asset

    Returns:
        DataFrame of portfolio weights
    """
    portfolio = signals.copy()

    # Equal-weight across assets with positions
    for i in range(len(portfolio)):
        active = portfolio.iloc[i] != 0
        if active.sum() > 0:
            portfolio.iloc[i] = portfolio.iloc[i] / active.sum()

    # Apply position limits
    portfolio = portfolio.clip(-max_position_pct, max_position_pct)

    return portfolio


# ---------------------------------------------------------------------------
# Main signal computation
# ---------------------------------------------------------------------------


def compute_ram_signals(
    prices: pd.DataFrame,
    config: RAMConfig | None = None,
) -> RAMResult:
    """Compute Regime-Adaptive Multi-Asset signals.

    Mechanism
    ---------
    1. Compute daily returns for all assets.
    2. Detect regime via cross-asset volatility analysis:
       - Short-term vol / Long-term vol < 0.7 → low vol (momentum)
       - Short-term vol / Long-term vol > 1.3 → high vol (mean-reversion)
       - Otherwise → normal (no positions)
    3. Generate signals based on regime:
       - Low-vol: Momentum (z-score of recent returns)
       - High-vol: Mean-reversion (z-score of price deviation from mean)
       - Normal: No positions
    4. Construct equal-weight portfolio across active assets.

    Parameters
    ----------
    prices : DataFrame of daily close prices, columns = assets, DatetimeIndex.
    config : frozen RAMConfig; defaults to pre-registered values.

    Returns
    -------
    RAMResult with signals, regime, regime_score, portfolio, config.
    """
    if config is None:
        config = RAMConfig()

    # Filter to universe
    available_assets = [a for a in config.universe if a in prices.columns]
    prices = prices[available_assets]

    # Drop rows with any NaN
    prices = prices.dropna()

    if len(prices) < config.min_history_days:
        empty_signals = pd.DataFrame(
            0, index=prices.index, columns=prices.columns
        )
        empty_regime = pd.Series("normal", index=prices.index, name="regime")
        empty_score = pd.Series(np.nan, index=prices.index, name="regime_score")
        return RAMResult(
            signals=empty_signals,
            regime=empty_regime,
            regime_score=empty_score,
            portfolio=empty_signals.copy(),
            config=config,
        )

    # 1. Compute returns
    returns = prices.pct_change().dropna()

    # 2. Detect regime
    regime, regime_score = _detect_regime(
        returns,
        config.vol_lookback_short,
        config.vol_lookback_long,
        config.vol_low_threshold,
        config.vol_high_threshold,
    )

    # Align returns with regime
    returns_aligned = returns.loc[regime.index]

    # 3. Generate signals
    mom_signals = _generate_momentum_signals(
        prices.loc[regime.index],
        config.mom_lookback,
        config.mom_entry_z,
    )

    mr_signals = _generate_mean_reversion_signals(
        prices.loc[regime.index],
        config.mr_lookback,
        config.mr_entry_z,
    )

    # 4. Combine signals based on regime
    combined_signals = pd.DataFrame(
        0.0, index=regime.index, columns=prices.columns
    )

    low_vol_mask = regime == "low_vol"
    high_vol_mask = regime == "high_vol"

    combined_signals.loc[low_vol_mask] = mom_signals.loc[low_vol_mask]
    combined_signals.loc[high_vol_mask] = mr_signals.loc[high_vol_mask]

    # 5. Construct portfolio
    portfolio = _construct_portfolio(combined_signals, config.max_position_pct)

    return RAMResult(
        signals=combined_signals,
        regime=regime,
        regime_score=regime_score,
        portfolio=portfolio,
        config=config,
    )


# ---------------------------------------------------------------------------
# Backtest metrics
# ---------------------------------------------------------------------------


def compute_ram_metrics(
    portfolio: pd.DataFrame,
    returns: pd.DataFrame,
    config: RAMConfig,
) -> dict:
    """Compute backtest metrics for the regime-adaptive portfolio.

    Args:
        portfolio: Portfolio weights from compute_ram_signals
        returns: Daily returns for all assets
        config: RAMConfig

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

    # Trade count
    trade_count = (portfolio.diff().abs().sum(axis=1) > 0).sum()

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_vol": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "trade_count": trade_count,
        "n_observations": len(portfolio_returns),
    }


__all__ = [
    "RAMConfig",
    "RAMResult",
    "compute_ram_signals",
    "compute_ram_metrics",
]
