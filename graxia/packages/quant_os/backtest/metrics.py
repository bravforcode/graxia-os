"""
Backtest Performance Metrics

Calculates all standard trading performance metrics:
- Win rate, profit factor, expectancy
- Sharpe ratio, Sortino ratio, Calmar ratio
- Max drawdown, max drawdown duration
- Average win/loss, average R:R
- CAGR, total return
"""

from dataclasses import dataclass
from typing import List, Optional
from decimal import Decimal
import math

from ..core.enums import PositionType


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


def calculate_metrics(
    trades: list,
    initial_capital: float,
    equity_curve: list,
    risk_free_rate: float = 0.0,
    annual_trading_days: int = 252,
) -> BacktestMetrics:
    """
    Calculate comprehensive backtest metrics.
    
    Args:
        trades: List of BacktestTrade objects
        initial_capital: Starting capital
        equity_curve: List of EquityPoint objects
        risk_free_rate: Annual risk-free rate for Sharpe calculation
        annual_trading_days: Trading days per year
    
    Returns:
        BacktestMetrics with all calculated metrics
    """
    metrics = BacktestMetrics()
    
    if not trades:
        return metrics
    
    # Basic counts
    metrics.total_trades = len(trades)
    metrics.winning_trades = sum(1 for t in trades if t.pnl > 0)
    metrics.losing_trades = sum(1 for t in trades if t.pnl < 0)
    metrics.win_rate = metrics.winning_trades / metrics.total_trades if metrics.total_trades > 0 else 0
    
    # P&L
    metrics.total_pnl = sum(float(t.pnl) for t in trades)
    metrics.total_return_pct = (metrics.total_pnl / initial_capital * 100) if initial_capital > 0 else 0
    
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
    metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    
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
        metrics.max_drawdown, metrics.max_drawdown_pct, metrics.max_drawdown_duration_bars = \
            _calculate_drawdown(equity_curve, initial_capital)
    
    # Risk-adjusted ratios
    if equity_curve and len(equity_curve) > 1:
        returns = _extract_returns(equity_curve)
        metrics.sharpe_ratio = _sharpe_ratio(returns, risk_free_rate, annual_trading_days)
        metrics.sortino_ratio = _sortino_ratio(returns, risk_free_rate, annual_trading_days)
        
        if metrics.max_drawdown_pct > 0:
            # CAGR
            total_days = len(equity_curve)
            years = total_days / annual_trading_days
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
    peak = initial_capital
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


def _extract_returns(equity_curve: list) -> List[float]:
    """Extract period returns from equity curve"""
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i-1].equity
        curr = equity_curve[i].equity
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _sharpe_ratio(returns: List[float], risk_free_rate: float, annual_trading_days: int) -> float:
    """Calculate annualized Sharpe ratio"""
    if not returns or len(returns) < 2:
        return 0.0
    
    avg_return = sum(returns) / len(returns)
    std_return = _std_dev(returns)
    
    if std_return == 0:
        return 0.0
    
    # Annualize
    daily_rf = risk_free_rate / annual_trading_days
    excess_returns = [r - daily_rf for r in returns]
    avg_excess = sum(excess_returns) / len(excess_returns)
    
    return (avg_excess / std_return) * math.sqrt(annual_trading_days)


def _sortino_ratio(returns: List[float], risk_free_rate: float, annual_trading_days: int) -> float:
    """Calculate annualized Sortino ratio (downside deviation only)"""
    if not returns or len(returns) < 2:
        return 0.0
    
    daily_rf = risk_free_rate / annual_trading_days
    excess_returns = [r - daily_rf for r in returns]
    avg_excess = sum(excess_returns) / len(excess_returns)
    
    # Downside deviation
    downside = [r for r in excess_returns if r < 0]
    if not downside:
        return float('inf') if avg_excess > 0 else 0.0
    
    downside_std = math.sqrt(sum(r**2 for r in downside) / len(downside))
    
    if downside_std == 0:
        return 0.0
    
    return (avg_excess / downside_std) * math.sqrt(annual_trading_days)


def _std_dev(values: List[float]) -> float:
    """Calculate standard deviation"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)
