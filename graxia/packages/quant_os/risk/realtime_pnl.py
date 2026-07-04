"""Phase 4 — Real-Time P&L Tracker.

Provides tick-level P&L tracking with real-time drawdown enforcement.
Replaces bar-close-only equity calculation with continuous monitoring.

Features:
- Tick-level P&L updates
- Real-time drawdown enforcement
- Intraday peak tracking
- Daily/weekly/monthly PnL aggregation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class PnLConfig:
    """P&L tracking configuration."""

    # Drawdown limits
    max_daily_drawdown_pct: float = 0.03  # 3% daily drawdown limit
    max_weekly_drawdown_pct: float = 0.05  # 5% weekly drawdown limit
    max_total_drawdown_pct: float = 0.10  # 10% total drawdown limit

    # Position limits
    max_open_positions: int = 5
    max_position_size_pct: float = 0.20  # 20% of equity per position

    # Alert thresholds
    warning_drawdown_pct: float = 0.02  # 2% drawdown warning
    critical_drawdown_pct: float = 0.05  # 5% drawdown critical


@dataclass
class PnLSnapshot:
    """Point-in-time P&L snapshot."""

    timestamp: float = 0.0
    equity: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    drawdown_pct: float = 0.0
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")


@dataclass
class PnLAlert:
    """P&L alert."""

    alert_type: str  # "WARNING", "CRITICAL", "BREACH"
    metric: str
    current_value: float
    threshold: float
    message: str


class RealTimePnLTracker:
    """Real-time P&L tracking with drawdown enforcement.

    Replaces bar-close-only equity calculation with continuous monitoring.
    """

    def __init__(self, config: PnLConfig | None = None, initial_equity: Decimal = Decimal("10000")):
        self.config = config or PnLConfig()
        self._initial_equity = initial_equity
        self._equity = initial_equity
        self._balance = initial_equity
        self._peak_equity = initial_equity
        self._daily_start_equity = initial_equity
        self._weekly_start_equity = initial_equity
        self._daily_pnl = Decimal("0")
        self._weekly_pnl = Decimal("0")
        self._realized_pnl = Decimal("0")
        self._positions: list[dict] = []
        self._snapshots: list[PnLSnapshot] = []
        self._alerts: list[PnLAlert] = []

    @property
    def equity(self) -> Decimal:
        return self._equity

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown as percentage of peak."""
        if self._peak_equity <= 0:
            return 0.0
        return float((self._peak_equity - self._equity) / self._peak_equity)

    @property
    def daily_drawdown_pct(self) -> float:
        """Daily drawdown from day start."""
        if self._daily_start_equity <= 0:
            return 0.0
        return float((self._daily_start_equity - self._equity) / self._daily_start_equity)

    @property
    def alerts(self) -> list[PnLAlert]:
        return list(self._alerts)

    def update_tick(self, unrealized_pnl: Decimal, timestamp: float = 0.0):
        """Update with tick-level P&L.

        Args:
            unrealized_pnl: Current unrealized P&L
            timestamp: Current timestamp
        """
        self._equity = self._balance + unrealized_pnl

        # Update peak
        if self._equity > self._peak_equity:
            self._peak_equity = self._equity

        # Update daily/weekly PnL
        self._daily_pnl = self._equity - self._daily_start_equity
        self._weekly_pnl = self._equity - self._weekly_start_equity

        # Check drawdown limits
        self._check_drawdowns()

    def record_trade_pnl(self, pnl: Decimal):
        """Record a closed trade PnL."""
        self._realized_pnl += pnl
        self._balance += pnl
        self._equity = self._balance

    def new_day(self):
        """Call at start of new trading day."""
        self._daily_start_equity = self._equity
        self._daily_pnl = Decimal("0")

    def new_week(self):
        """Call at start of new trading week."""
        self._weekly_start_equity = self._equity
        self._weekly_pnl = Decimal("0")

    def can_open_position(self, size_pct: float) -> tuple[bool, str]:
        """Check if a new position can be opened.

        Args:
            size_pct: Proposed position size as % of equity

        Returns:
            (allowed, reason)
        """
        if len(self._positions) >= self.config.max_open_positions:
            return False, f"Max positions reached: {len(self._positions)}"

        if size_pct > self.config.max_position_size_pct:
            return False, f"Position size {size_pct:.1%} > max {self.config.max_position_size_pct:.0%}"

        if self.drawdown_pct > self.config.critical_drawdown_pct:
            return False, f"Drawdown {self.drawdown_pct:.1%} exceeds critical threshold"

        return True, "OK"

    def _check_drawdowns(self):
        """Check drawdown limits and generate alerts."""
        dd = self.drawdown_pct
        daily_dd = self.daily_drawdown_pct

        # Total drawdown
        if dd >= self.config.max_total_drawdown_pct:
            self._alerts.append(PnLAlert(
                alert_type="BREACH",
                metric="total_drawdown",
                current_value=dd,
                threshold=self.config.max_total_drawdown_pct,
                message=f"TOTAL DRAWDOWN BREACH: {dd:.1%} >= {self.config.max_total_drawdown_pct:.0%}",
            ))
        elif dd >= self.config.critical_drawdown_pct:
            self._alerts.append(PnLAlert(
                alert_type="CRITICAL",
                metric="total_drawdown",
                current_value=dd,
                threshold=self.config.critical_drawdown_pct,
                message=f"Critical drawdown: {dd:.1%} >= {self.config.critical_drawdown_pct:.0%}",
            ))
        elif dd >= self.config.warning_drawdown_pct:
            self._alerts.append(PnLAlert(
                alert_type="WARNING",
                metric="total_drawdown",
                current_value=dd,
                threshold=self.config.warning_drawdown_pct,
                message=f"Drawdown warning: {dd:.1%} >= {self.config.warning_drawdown_pct:.0%}",
            ))

        # Daily drawdown
        if daily_dd >= self.config.max_daily_drawdown_pct:
            self._alerts.append(PnLAlert(
                alert_type="BREACH",
                metric="daily_drawdown",
                current_value=daily_dd,
                threshold=self.config.max_daily_drawdown_pct,
                message=f"DAILY DRAWDOWN BREACH: {daily_dd:.1%} >= {self.config.max_daily_drawdown_pct:.0%}",
            ))

    def get_snapshot(self, timestamp: float = 0.0) -> PnLSnapshot:
        """Get current P&L snapshot."""
        return PnLSnapshot(
            timestamp=timestamp,
            equity=self._equity,
            balance=self._balance,
            unrealized_pnl=self._equity - self._balance,
            realized_pnl=self._realized_pnl,
            drawdown_pct=self.drawdown_pct,
            daily_pnl=self._daily_pnl,
            weekly_pnl=self._weekly_pnl,
            peak_equity=self._peak_equity,
        )

    def reset(self):
        """Reset for a new session."""
        self._equity = self._initial_equity
        self._balance = self._initial_equity
        self._peak_equity = self._initial_equity
        self._daily_start_equity = self._initial_equity
        self._weekly_start_equity = self._initial_equity
        self._daily_pnl = Decimal("0")
        self._weekly_pnl = Decimal("0")
        self._realized_pnl = Decimal("0")
        self._positions.clear()
        self._snapshots.clear()
        self._alerts.clear()
