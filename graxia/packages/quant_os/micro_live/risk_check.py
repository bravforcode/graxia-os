"""Phase BE-P12 — Micro-live risk check."""
from dataclasses import dataclass


@dataclass
class RiskBudget:
    daily_pnl_bps: float = 0.0
    weekly_pnl_bps: float = 0.0
    total_drawdown_bps: float = 0.0
    orders_today: int = 0


class MicroLiveRiskCheck:
    """Enforce micro-live risk limits."""

    def __init__(self, max_daily_bps: int = 50, max_weekly_bps: int = 150,
                 max_drawdown_bps: int = 300, max_orders_per_day: int = 3):
        self._max_daily = max_daily_bps
        self._max_weekly = max_weekly_bps
        self._max_drawdown = max_drawdown_bps
        self._max_orders = max_orders_per_day

    def check(self, budget: RiskBudget) -> tuple[bool, list[str]]:
        issues = []
        if abs(budget.daily_pnl_bps) >= self._max_daily:
            issues.append(f"daily_loss: {budget.daily_pnl_bps:.1f} >= {self._max_daily}")
        if abs(budget.weekly_pnl_bps) >= self._max_weekly:
            issues.append(f"weekly_loss: {budget.weekly_pnl_bps:.1f} >= {self._max_weekly}")
        if abs(budget.total_drawdown_bps) >= self._max_drawdown:
            issues.append(f"drawdown: {budget.total_drawdown_bps:.1f} >= {self._max_drawdown}")
        if budget.orders_today >= self._max_orders:
            issues.append(f"orders: {budget.orders_today} >= {self._max_orders}")
        return len(issues) == 0, issues
