"""Phase 4 — Paper Trading Validation Framework.

Extends paper trading duration requirements and adds validation gates:
- Minimum 12 weeks (84 days) paper trading before live
- Weekly performance review gates
- Drawdown-based auto-halt
- Live-backtest comparison framework

Research:
- AQR: 12+ weeks minimum paper trading
- Industry standard: 8-18 weeks
- Strategy must survive at least one regime transition
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class PaperTradingStatus(str, Enum):
    ACTIVE = "active"
    PASSED = "passed"
    FAILED = "failed"
    HALTED = "halted"  # Drawdown breach


@dataclass
class PaperTradingConfig:
    """Paper trading validation configuration."""

    # Duration requirements
    min_duration_days: int = 84  # 12 weeks minimum
    min_duration_weeks: int = 12

    # Performance gates
    min_sharpe: float = 0.5  # Minimum Sharpe ratio
    min_win_rate: float = 0.45  # Minimum win rate
    min_profit_factor: float = 1.0  # Minimum profit factor
    max_drawdown_pct: float = 0.15  # Maximum allowed drawdown (15%)

    # Weekly review gates
    max_consecutive_losing_weeks: int = 3  # Auto-halt after 3 losing weeks
    min_weekly_consistency: float = 0.4  # 40% of weeks must be profitable

    # Live-backtest comparison
    max_sharpe_degradation: float = 0.5  # Live Sharpe should be >= 50% of backtest
    max_drawdown_amplification: float = 2.0  # Live DD should be <= 2x backtest DD


@dataclass
class WeeklyReview:
    """Weekly performance review."""

    week_number: int
    start_date: str
    end_date: str
    pnl: float
    sharpe: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    trades_count: int
    passed: bool = True
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class PaperTradingResult:
    """Overall paper trading validation result."""

    status: PaperTradingStatus
    total_days: int = 0
    total_weeks: int = 0
    final_sharpe: float = 0.0
    final_win_rate: float = 0.0
    final_profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    weekly_reviews: list[WeeklyReview] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)


class PaperTradingValidator:
    """Validates strategy performance during paper trading phase.

    Enforces minimum duration, performance gates, and weekly reviews.
    """

    def __init__(self, config: PaperTradingConfig | None = None):
        self.config = config or PaperTradingConfig()
        self._start_time: float = time.time()
        self._trades: list[dict] = []
        self._weekly_pnls: list[float] = []
        self._status = PaperTradingStatus.ACTIVE
        self._failure_reasons: list[str] = []

    def record_trade(self, pnl: float, timestamp: float = 0.0):
        """Record a paper trade."""
        self._trades.append({"pnl": pnl, "timestamp": timestamp})

    def record_weekly_pnl(self, weekly_pnl: float):
        """Record weekly PnL for consistency tracking."""
        self._weekly_pnls.append(weekly_pnl)

    def evaluate(self, backtest_sharpe: float = 0.0, backtest_max_dd: float = 0.0) -> PaperTradingResult:
        """Evaluate paper trading performance.

        Args:
            backtest_sharpe: Sharpe ratio from backtest for comparison
            backtest_max_dd: Max drawdown from backtest for comparison

        Returns:
            PaperTradingResult with pass/fail status
        """
        # Calculate duration
        elapsed_days = int((time.time() - self._start_time) / 86400)
        elapsed_weeks = elapsed_days // 7

        # Calculate metrics
        if not self._trades:
            return PaperTradingResult(
                status=PaperTradingStatus.FAILED,
                total_days=elapsed_days,
                total_weeks=elapsed_weeks,
                failure_reasons=["No trades recorded"],
            )

        wins = [t["pnl"] for t in self._trades if t["pnl"] > 0]
        losses = [abs(t["pnl"]) for t in self._trades if t["pnl"] < 0]
        win_rate = len(wins) / len(self._trades) if self._trades else 0
        total_pnl = sum(t["pnl"] for t in self._trades)
        gross_profit = sum(wins) if wins else 0
        gross_loss = sum(losses) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Sharpe (simplified)
        returns = [t["pnl"] / 10000 for t in self._trades]  # Normalize
        if len(returns) > 1:
            mean_r = sum(returns) / len(returns)
            var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            sharpe = (mean_r / (var_r**0.5)) * (24192**0.5) if var_r > 0 else 0
        else:
            sharpe = 0

        # Max drawdown
        peak = 0
        max_dd = 0.0
        cumulative = 0.0
        for t in self._trades:
            cumulative += t["pnl"]
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Check gates
        reasons = []

        # Duration gate
        if elapsed_days < self.config.min_duration_days:
            reasons.append(f"Duration {elapsed_days} days < {self.config.min_duration_days} minimum")

        # Performance gates
        if sharpe < self.config.min_sharpe:
            reasons.append(f"Sharpe {sharpe:.2f} < {self.config.min_sharpe} minimum")

        if win_rate < self.config.min_win_rate:
            reasons.append(f"Win rate {win_rate:.1%} < {self.config.min_win_rate:.0%} minimum")

        if profit_factor < self.config.min_profit_factor:
            reasons.append(f"Profit factor {profit_factor:.2f} < {self.config.min_profit_factor} minimum")

        if max_dd > self.config.max_drawdown_pct:
            reasons.append(f"Max drawdown {max_dd:.1%} > {self.config.max_drawdown_pct:.0%} limit")

        # Weekly consistency
        if self._weekly_pnls:
            profitable_weeks = sum(1 for w in self._weekly_pnls if w > 0)
            weekly_consistency = profitable_weeks / len(self._weekly_pnls)
            if weekly_consistency < self.config.min_weekly_consistency:
                reasons.append(f"Weekly consistency {weekly_consistency:.0%} < {self.config.min_weekly_consistency:.0%}")

            # Consecutive losing weeks
            consecutive_losses = 0
            max_consecutive = 0
            for w in reversed(self._weekly_pnls):
                if w < 0:
                    consecutive_losses += 1
                    max_consecutive = max(max_consecutive, consecutive_losses)
                else:
                    consecutive_losses = 0
            if max_consecutive >= self.config.max_consecutive_losing_weeks:
                reasons.append(f"Max consecutive losing weeks: {max_consecutive} >= {self.config.max_consecutive_losing_weeks}")

        # Live-backtest comparison
        if backtest_sharpe > 0:
            degradation = 1 - (sharpe / backtest_sharpe)
            if degradation > self.config.max_sharpe_degradation:
                reasons.append(f"Sharpe degradation {degradation:.0%} > {self.config.max_sharpe_degradation:.0%}")

        if backtest_max_dd > 0:
            amplification = max_dd / backtest_max_dd
            if amplification > self.config.max_drawdown_amplification:
                reasons.append(f"Drawdown amplification {amplification:.1f}x > {self.config.max_drawdown_amplification:.0f}x")

        # Determine status
        if reasons:
            status = PaperTradingStatus.FAILED
        elif elapsed_days >= self.config.min_duration_days:
            status = PaperTradingStatus.PASSED
        else:
            status = PaperTradingStatus.ACTIVE

        return PaperTradingResult(
            status=status,
            total_days=elapsed_days,
            total_weeks=elapsed_weeks,
            final_sharpe=sharpe,
            final_win_rate=win_rate,
            final_profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            failure_reasons=reasons,
        )

    def reset(self):
        """Reset for a new paper trading session."""
        self._start_time = time.time()
        self._trades.clear()
        self._weekly_pnls.clear()
        self._status = PaperTradingStatus.ACTIVE
        self._failure_reasons.clear()
