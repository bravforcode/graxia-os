"""
Metrics collection for Quant OS
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class TradeMetrics:
    """Metrics for a single trade"""
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    duration_seconds: int
    regime: Optional[str] = None


class MetricsCollector:
    """
    Collect and aggregate trading metrics
    """

    def __init__(self):
        self.daily_trades: list = []
        self.daily_pnl: float = 0.0
        self.win_count: int = 0
        self.loss_count: int = 0

    def record_trade(self, metrics: TradeMetrics) -> None:
        """Record a completed trade"""
        self.daily_trades.append(metrics)
        self.daily_pnl += metrics.pnl

        if metrics.pnl > 0:
            self.win_count += 1
        elif metrics.pnl < 0:
            self.loss_count += 1

    def get_win_rate(self) -> float:
        """Calculate win rate"""
        total = self.win_count + self.loss_count
        if total == 0:
            return 0.0
        return self.win_count / total * 100

    def get_expectancy(self) -> float:
        """Calculate expectancy ($ per trade)"""
        if not self.daily_trades:
            return 0.0
        return self.daily_pnl / len(self.daily_trades)

    def reset_daily(self) -> None:
        """Reset daily metrics"""
        self.daily_trades = []
        self.daily_pnl = 0.0
        self.win_count = 0
        self.loss_count = 0

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary"""
        return {
            "total_trades": len(self.daily_trades),
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate_pct": self.get_win_rate(),
            "daily_pnl": self.daily_pnl,
            "expectancy": self.get_expectancy(),
        }
