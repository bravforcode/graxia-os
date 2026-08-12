"""
Backtest Performance Metrics

Calculates all standard trading performance metrics:
- Win rate, profit factor, expectancy
- Sharpe ratio, Sortino ratio, Calmar ratio
- Max drawdown, max drawdown duration
- Average win/loss, average R:R
- CAGR, total return

Phase 3: Added bootstrap confidence intervals (stationary bootstrap).
"""

import math
import random
from dataclasses import dataclass, field

from ..core.enums import PositionType

# ── Bars-per-year lookup for correct Sharpe annualization ───────────────
# Key: (asset_class, timeframe) → bars per calendar year
# Metals/crypto trade 24/7; forex/indices follow ~252 trading-day calendar.
BARS_PER_YEAR: dict[tuple[str, str], int] = {
    ("metals", "M15"): 24_192,  # 24h × 4 bars/h × 365d × ~6.9 for metals session
    ("crypto", "M15"): 35_040,  # 24/7/365 × 4 bars/h
    ("forex", "M15"): 24_192,  # 24h × 4 × ~252 (incl. sessions overlap)
    ("indices", "M15"): 16_128,  # ~6.5h × 4 × 252
    # Fallback for daily or unknown
    ("_default", "D1"): 252,
}
_DEFAULT_BARS_PER_YEAR = 24_192  # conservative metals/forex M15 default


@dataclass
class BacktestMetrics:
    """Performance metrics from a backtest run"""

    # Basic
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # P&L
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    expectancy: float = 0.0

    # Risk
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0

    # Risk-adjusted
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Time
    cagr: float = 0.0
    total_bars: int = 0

    # Costs
    total_fees: float = 0.0
    total_slippage: float = 0.0

    # By side
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0

    # By exit reason
    stop_loss_exits: int = 0
    take_profit_exits: int = 0
    manual_exits: int = 0

    # Consecutive
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


@dataclass
class BootstrapCI:
    """Phase 3: Bootstrap confidence interval for a metric."""

    metric_name: str
    point_estimate: float
    ci_lower: float  # 2.5th percentile
    ci_upper: float  # 97.5th percentile
    ci_level: float = 0.95
    n_resamples: int = 1000
    includes_zero: bool = True  # True if CI includes zero (no edge detected)


def stationary_bootstrap(
    returns: list[float],
    mean_block_length: int = 10,
    n_resamples: int = 1000,
    seed: int | None = None,
) -> list[list[float]]:
    """Phase 3: Stationary bootstrap (Politis & Romano 1994).

    Preserves autocorrelation and volatility clustering in financial time series.

    Args:
        returns: Per-bar return series
        mean_block_length: Average block length (10-20 for daily FX)
        n_resamples: Number of bootstrap samples
        seed: Random seed for reproducibility

    Returns:
        List of n_resamples bootstrap return series
    """
    if len(returns) < 2:
        return [returns] * n_resamples

    rng = random.Random(seed)
    n = len(returns)
    p = 1.0 / mean_block_length  # Probability of starting a new block

    resamples = []
    for _ in range(n_resamples):
        sample = []
        idx = rng.randint(0, n - 1)
        while len(sample) < n:
            sample.append(returns[idx])
            if rng.random() < p:
                idx = rng.randint(0, n - 1)
            else:
                idx = (idx + 1) % n
        resamples.append(sample)

    return resamples


def bootstrap_metric_ci(
    returns: list[float],
    metric_func,
    n_resamples: int = 1000,
    mean_block_length: int = 10,
    ci_level: float = 0.95,
    seed: int | None = None,
) -> BootstrapCI:
    """Phase 3: Compute bootstrap confidence interval for any metric.

    Args:
        returns: Per-bar return series
        metric_func: Function that takes a return series and returns a scalar metric
        n_resamples: Number of bootstrap resamples
        mean_block_length: Average block length for stationary bootstrap
        ci_level: Confidence level (default 0.95 = 95% CI)
        seed: Random seed

    Returns:
        BootstrapCI with point estimate, CI bounds, and zero-inclusion check
    """
    if not returns or len(returns) < 10:
        point = metric_func(returns) if returns else 0.0
        return BootstrapCI(
            metric_name=metric_func.__name__,
            point_estimate=point,
            ci_lower=point,
            ci_upper=point,
            ci_level=ci_level,
            n_resamples=0,
            includes_zero=True,
        )

    point = metric_func(returns)
    resamples = stationary_bootstrap(returns, mean_block_length, n_resamples, seed)

    bootstrap_values = []
    for sample in resamples:
        try:
            val = metric_func(sample)
            if math.isfinite(val):
                bootstrap_values.append(val)
        except Exception:
            continue

    if not bootstrap_values:
        return BootstrapCI(
            metric_name=metric_func.__name__,
            point_estimate=point,
            ci_lower=point,
            ci_upper=point,
            ci_level=ci_level,
            n_resamples=0,
            includes_zero=True,
        )

    bootstrap_values.sort()
    alpha = (1 - ci_level) / 2
    lower_idx = int(alpha * len(bootstrap_values))
    upper_idx = int((1 - alpha) * len(bootstrap_values)) - 1
    lower_idx = max(0, min(lower_idx, len(bootstrap_values) - 1))
    upper_idx = max(0, min(upper_idx, len(bootstrap_values) - 1))

    ci_lower = bootstrap_values[lower_idx]
    ci_upper = bootstrap_values[upper_idx]
    includes_zero = ci_lower <= 0 <= ci_upper

    return BootstrapCI(
        metric_name=metric_func.__name__,
        point_estimate=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        n_resamples=len(bootstrap_values),
        includes_zero=includes_zero,
    )


def calculate_metrics(
    trades: list,
    initial_capital: float,
    equity_curve: list,
    risk_free_rate: float = 0.0,
    annual_trading_days: int = 252,
    asset_class: str = "_default",
    timeframe: str = "M15",
) -> BacktestMetrics:
    """
    Calculate comprehensive backtest metrics.

    Args:
        trades: List of BacktestTrade objects
        initial_capital: Starting capital
        equity_curve: List of EquityPoint objects
        risk_free_rate: Annual risk-free rate for Sharpe calculation
        annual_trading_days: Trading days per year (legacy; overridden by BARS_PER_YEAR when available)
        asset_class: Asset class for correct bar-frequency lookup ("metals","crypto","forex","indices")
        timeframe: Bar timeframe for lookup ("M15","D1", etc.)

    Returns:
        BacktestMetrics with all calculated metrics
    """
    # Resolve bars-per-year from asset/timeframe, fall back to legacy param
    bars_per_year = BARS_PER_YEAR.get(
        (asset_class, timeframe),
        BARS_PER_YEAR.get(("_default", timeframe), annual_trading_days),
    )
    metrics = BacktestMetrics()
    initial_capital = float(initial_capital)  # ponytail: accept Decimal from engine

    if not trades:
        return metrics

    # Basic counts
    metrics.total_trades = len(trades)
    metrics.winning_trades = sum(1 for t in trades if t.pnl > 0)
    metrics.losing_trades = sum(1 for t in trades if t.pnl < 0)
    metrics.win_rate = metrics.winning_trades / metrics.total_trades if metrics.total_trades > 0 else 0

    # P&L
    metrics.total_pnl = sum(float(t.pnl) for t in trades)
    metrics.total_return_pct = (metrics.total_pnl / float(initial_capital) * 100) if float(initial_capital) > 0 else 0

    wins = [float(t.pnl) for t in trades if t.pnl > 0]
    losses = [float(t.pnl) for t in trades if t.pnl < 0]

    metrics.avg_win = sum(wins) / len(wins) if wins else 0
    metrics.avg_loss = sum(losses) / len(losses) if losses else 0

    # Expectancy: (win_rate * avg_win) - (loss_rate * avg_loss)
    win_rate = metrics.win_rate
    loss_rate = 1 - win_rate
    metrics.expectancy = (win_rate * metrics.avg_win) + (loss_rate * metrics.avg_loss)

    # Average R:R
    if metrics.avg_loss != 0:
        metrics.avg_rr = abs(metrics.avg_win / metrics.avg_loss)

    # Profit factor
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

    # Fees
    metrics.total_fees = sum(float(t.fees) for t in trades)

    # By side
    long_trades = [t for t in trades if t.side == PositionType.LONG]
    short_trades = [t for t in trades if t.side == PositionType.SHORT]
    metrics.long_trades = len(long_trades)
    metrics.short_trades = len(short_trades)
    metrics.long_win_rate = sum(1 for t in long_trades if t.pnl > 0) / len(long_trades) if long_trades else 0
    metrics.short_win_rate = sum(1 for t in short_trades if t.pnl > 0) / len(short_trades) if short_trades else 0

    # By exit reason
    from ..core.enums import CloseReason

    metrics.stop_loss_exits = sum(1 for t in trades if t.close_reason == CloseReason.STOP_LOSS)
    metrics.take_profit_exits = sum(1 for t in trades if t.close_reason == CloseReason.TAKE_PROFIT)
    metrics.manual_exits = sum(1 for t in trades if t.close_reason == CloseReason.MANUAL)

    # Consecutive wins/losses
    metrics.max_consecutive_wins, metrics.max_consecutive_losses = _consecutive_streaks(trades)

    # Max drawdown from equity curve
    if equity_curve:
        metrics.max_drawdown, metrics.max_drawdown_pct, metrics.max_drawdown_duration_bars = _calculate_drawdown(
            equity_curve, initial_capital
        )

    # Risk-adjusted ratios
    if equity_curve and len(equity_curve) > 1:
        returns = _extract_returns(equity_curve)
        metrics.sharpe_ratio = _sharpe_ratio(returns, risk_free_rate, bars_per_year)
        metrics.sortino_ratio = _sortino_ratio(returns, risk_free_rate, bars_per_year)

        if metrics.max_drawdown_pct > 0:
            # CAGR
            total_bars = len(equity_curve)
            years = total_bars / bars_per_year
            if years > 0:
                final_equity = equity_curve[-1].equity
                metrics.cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100

            metrics.calmar_ratio = (metrics.cagr / metrics.max_drawdown_pct) if metrics.max_drawdown_pct > 0 else 0

    metrics.total_bars = len(equity_curve)

    return metrics


def _consecutive_streaks(trades: list) -> tuple:
    """Calculate max consecutive wins and losses"""
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0

    for trade in trades:
        if trade.pnl > 0:
            current_wins += 1
            current_losses = 0
            max_wins = max(max_wins, current_wins)
        elif trade.pnl < 0:
            current_losses += 1
            current_wins = 0
            max_losses = max(max_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0

    return max_wins, max_losses


def _calculate_drawdown(equity_curve: list, initial_capital: float) -> tuple:
    """Calculate max drawdown from equity curve"""
    peak = float(initial_capital)
    max_dd = 0.0
    max_dd_pct = 0.0
    current_dd_start = 0
    max_dd_duration = 0
    in_drawdown = False
    dd_start_idx = 0

    for i, point in enumerate(equity_curve):
        if point.equity > peak:
            peak = point.equity
            if in_drawdown:
                duration = i - dd_start_idx
                max_dd_duration = max(max_dd_duration, duration)
                in_drawdown = False

        dd = peak - point.equity
        dd_pct = (dd / peak * 100) if peak > 0 else 0

        if dd > max_dd:
            max_dd = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

        if dd > 0 and not in_drawdown:
            in_drawdown = True
            dd_start_idx = i

    # If still in drawdown at end
    if in_drawdown:
        max_dd_duration = max(max_dd_duration, len(equity_curve) - dd_start_idx)

    return max_dd, max_dd_pct, max_dd_duration


def _extract_returns(equity_curve: list) -> list[float]:
    """Extract period returns from equity curve"""
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        curr = equity_curve[i].equity
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _sharpe_ratio(returns: list[float], risk_free_rate: float, bars_per_year: int) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        returns: Period returns (one per bar).
        risk_free_rate: Annual risk-free rate.
        bars_per_year: Number of bars in one calendar year for the given
            asset class / timeframe.  Drives the sqrt(T) annualization factor.
    """
    if not returns or len(returns) < 2:
        return 0.0

    avg_return = sum(returns) / len(returns)
    std_return = _std_dev(returns)

    if std_return == 0:
        return 0.0

    # Annualize
    bar_rf = risk_free_rate / bars_per_year
    excess_returns = [r - bar_rf for r in returns]
    avg_excess = sum(excess_returns) / len(excess_returns)

    return (avg_excess / std_return) * math.sqrt(bars_per_year)


def _sortino_ratio(returns: list[float], risk_free_rate: float, bars_per_year: int) -> float:
    """Calculate annualized Sortino ratio (downside deviation only).

    Args:
        returns: Period returns (one per bar).
        risk_free_rate: Annual risk-free rate.
        bars_per_year: Annualization factor matching the bar frequency.
    """
    if not returns or len(returns) < 2:
        return 0.0

    bar_rf = risk_free_rate / bars_per_year
    excess_returns = [r - bar_rf for r in returns]
    avg_excess = sum(excess_returns) / len(excess_returns)

    # Downside deviation — use ALL observations (not just negative returns)
    # to avoid overstating risk-adjusted returns. Negative returns contribute 0.
    downside_sq_sum = sum(r**2 for r in excess_returns if r < 0)
    downside_std = math.sqrt(downside_sq_sum / len(excess_returns))

    if downside_std == 0:
        return float("inf") if avg_excess > 0 else 0.0

    return (avg_excess / downside_std) * math.sqrt(bars_per_year)


def _std_dev(values: list[float]) -> float:
    """Calculate standard deviation"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)
