"""Real-time risk calculation engine.

Calculates VaR, drawdown, P&L, and exposure metrics live. Fires alerts
when configurable risk thresholds are approached or breached.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass
class PositionSnapshot:
    """Snapshot of a single position for risk calculation."""

    symbol: str
    direction: str  # "LONG" | "SHORT"
    quantity: float
    entry_price: float
    current_price: float
    stop_loss: Optional[float] = None

    @property
    def market_value(self) -> float:
        return abs(self.quantity) * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        if self.direction == "LONG":
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * abs(self.quantity)

    @property
    def risk_to_stop(self) -> float:
        """Dollar risk if stop is hit (always positive)."""
        if self.stop_loss is None or self.stop_loss <= 0:
            return 0.0
        return abs(self.entry_price - self.stop_loss) * abs(self.quantity)


@dataclass
class RealTimeMetrics:
    """Aggregated real-time risk metrics."""

    timestamp: float
    total_exposure: float = 0.0
    net_exposure: float = 0.0
    gross_exposure: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    current_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    max_risk_to_stop: float = 0.0
    alerts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RiskLimits:
    """Configurable risk thresholds."""

    max_total_exposure_pct: float = 0.80
    max_single_position_pct: float = 0.30
    max_drawdown_pct: float = 0.15
    var_limit_95_pct: float = 0.02
    max_risk_to_stop_pct: float = 0.05
    alert_buffer_pct: float = 0.10  # fire alert at 90% of limit


# ── Alert callback type ─────────────────────────────────────────────────────

AlertCallback = Callable[[str, str], None]


# ── Core engine ──────────────────────────────────────────────────────────────


class RealTimeRisk:
    """Calculates real-time risk metrics against a live portfolio snapshot.

    Usage::

        risk = RealTimeRisk(equity=100_000.0, limits=RiskLimits())
        risk.update_positions([...])
        risk.record_equity(100_000.0)
        metrics = risk.get_risk_metrics()
    """

    def __init__(
        self,
        equity: float = 100_000.0,
        limits: RiskLimits | None = None,
        lookback_window: int = 252,
        on_alert: AlertCallback | None = None,
    ):
        self._equity = equity
        self._limits = limits or RiskLimits()
        self._lookback = lookback_window
        self._on_alert = on_alert

        self._positions: dict[str, PositionSnapshot] = {}
        self._equity_history: list[float] = [equity]
        self._pnl_history: list[float] = [0.0]
        self._peak_equity: float = equity
        self._realized_pnl: float = 0.0

        logger.info(
            "realtime_risk.init",
            equity=equity,
            lookback=lookback_window,
        )

    # ── State mutation ───────────────────────────────────────────────────

    def update_positions(self, positions: list[PositionSnapshot]) -> None:
        """Replace the current position set with a fresh snapshot."""
        self._positions = {p.symbol: p for p in positions}
        logger.debug("realtime_risk.positions_updated", count=len(positions))

    def update_position(self, position: PositionSnapshot) -> None:
        """Update a single position."""
        self._positions[position.symbol] = position

    def remove_position(self, symbol: str) -> None:
        self._positions.pop(symbol, None)

    def record_equity(self, equity: float) -> None:
        """Record current account equity for drawdown tracking."""
        self._equity = equity
        self._equity_history.append(equity)
        if equity > self._peak_equity:
            self._peak_equity = equity
        if len(self._equity_history) > self._lookback + 1:
            self._equity_history = self._equity_history[-(self._lookback + 1) :]
        self._pnl_history.append(equity - self._equity_history[-2] if len(self._equity_history) > 1 else 0.0)
        if len(self._pnl_history) > self._lookback + 1:
            self._pnl_history = self._pnl_history[-(self._lookback + 1) :]

    def record_realized_pnl(self, pnl: float) -> None:
        """Add a realized P&L event."""
        self._realized_pnl += pnl

    # ── VaR calculations ────────────────────────────────────────────────

    def calculate_portfolio_var(
        self, confidence: float = 0.95, method: str = "historical"
    ) -> float:
        """Calculate portfolio Value at Risk.

        Args:
            confidence: VaR confidence level (e.g. 0.95 for 95%).
            method: ``"historical"`` uses empirical return distribution.

        Returns:
            VaR as a positive fraction of equity (e.g. 0.02 = 2%).
        """
        returns = self._portfolio_returns()
        if len(returns) < 10:
            logger.warning("realtime_risk.var_insufficient_data", n=len(returns))
            return 0.0

        arr = np.asarray(returns, dtype=np.float64)
        alpha = 1.0 - confidence
        var = float(-np.percentile(arr, alpha * 100))
        logger.debug("realtime_risk.var", confidence=confidence, var=var)
        return max(var, 0.0)

    def calculate_cvar(self, confidence: float = 0.95) -> float:
        """Conditional VaR (Expected Shortfall) — average loss beyond VaR."""
        returns = self._portfolio_returns()
        if len(returns) < 10:
            return 0.0
        arr = np.asarray(returns, dtype=np.float64)
        alpha = 1.0 - confidence
        threshold = np.percentile(arr, alpha * 100)
        tail = arr[arr <= threshold]
        if tail.size == 0:
            return 0.0
        return max(float(-tail.mean()), 0.0)

    # ── Position risk ───────────────────────────────────────────────────

    def calculate_position_risk(self, symbol: str) -> dict[str, float]:
        """Calculate risk metrics for a single position.

        Returns dict with ``market_value``, ``pnl``, ``pnl_pct``,
        ``risk_to_stop``, ``contribution_to_var``.
        """
        pos = self._positions.get(symbol)
        if pos is None:
            return {}

        pnl_pct = pos.unrealized_pnl / self._equity if self._equity else 0.0
        return {
            "market_value": pos.market_value,
            "pnl": pos.unrealized_pnl,
            "pnl_pct": pnl_pct,
            "risk_to_stop": pos.risk_to_stop,
            "contribution_to_var": 0.0,  # filled by get_risk_metrics
        }

    # ── Aggregate metrics ───────────────────────────────────────────────

    def get_risk_metrics(self) -> RealTimeMetrics:
        """Build the full real-time metrics snapshot and fire alerts."""
        positions = list(self._positions.values())
        total_exposure = sum(p.market_value for p in positions)
        long_exposure = sum(p.market_value for p in positions if p.direction == "LONG")
        short_exposure = sum(p.market_value for p in positions if p.direction == "SHORT")
        gross_exposure = long_exposure + short_exposure
        net_exposure = long_exposure - short_exposure

        unrealized = sum(p.unrealized_pnl for p in positions)
        max_risk_to_stop = sum(p.risk_to_stop for p in positions)

        drawdown = self._current_drawdown()
        var_95 = self.calculate_portfolio_var(0.95)
        var_99 = self.calculate_portfolio_var(0.99)
        cvar_95 = self.calculate_cvar(0.95)

        alerts = self._check_alerts(
            total_exposure=total_exposure,
            gross_exposure=gross_exposure,
            drawdown=drawdown,
            var_95=var_95,
            max_risk_to_stop=max_risk_to_stop,
            positions=positions,
        )

        metrics = RealTimeMetrics(
            timestamp=time.time(),
            total_exposure=total_exposure,
            net_exposure=net_exposure,
            gross_exposure=gross_exposure,
            unrealized_pnl=unrealized,
            realized_pnl=self._realized_pnl,
            current_drawdown_pct=drawdown,
            peak_equity=self._peak_equity,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            max_risk_to_stop=max_risk_to_stop,
            alerts=alerts,
        )

        logger.info(
            "realtime_risk.metrics",
            exposure=f"{total_exposure:.0f}",
            pnl=f"{unrealized:.2f}",
            drawdown=f"{drawdown:.4f}",
            var95=f"{var_95:.4f}",
            alerts=len(alerts),
        )
        return metrics

    # ── Internal helpers ────────────────────────────────────────────────

    def _current_drawdown(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return max((self._peak_equity - self._equity) / self._peak_equity, 0.0)

    def _portfolio_returns(self) -> list[float]:
        """Weighted portfolio returns from equity history."""
        if len(self._equity_history) < 2:
            return []
        returns: list[float] = []
        for i in range(1, len(self._equity_history)):
            prev = self._equity_history[i - 1]
            if prev != 0:
                returns.append((self._equity_history[i] - prev) / prev)
        return returns

    def _check_alerts(
        self,
        total_exposure: float,
        gross_exposure: float,
        drawdown: float,
        var_95: float,
        max_risk_to_stop: float,
        positions: list[PositionSnapshot],
    ) -> list[str]:
        """Evaluate thresholds and return alert messages."""
        L = self._limits
        buf = 1.0 - L.alert_buffer_pct
        alerts: list[str] = []

        def _check(label: str, value: float, limit: float) -> None:
            if limit <= 0:
                return
            if value >= limit:
                msg = f"BREACH: {label} = {value:.4f} >= limit {limit:.4f}"
                alerts.append(msg)
                self._fire_alert("BREACH", msg)
            elif value >= limit * buf:
                msg = f"WARNING: {label} = {value:.4f} approaching limit {limit:.4f}"
                alerts.append(msg)
                self._fire_alert("WARNING", msg)

        # Exposure checks
        if self._equity > 0:
            _check("total_exposure_pct", total_exposure / self._equity, L.max_total_exposure_pct)
            _check("var_95_pct", var_95, L.var_limit_95_pct)
            _check("drawdown_pct", drawdown, L.max_drawdown_pct)
            _check("risk_to_stop_pct", max_risk_to_stop / self._equity, L.max_risk_to_stop_pct)

        # Per-position concentration
        for pos in positions:
            if self._equity > 0:
                pct = pos.market_value / self._equity
                if pct > L.max_single_position_pct:
                    msg = f"BREACH: position {pos.symbol} concentration {pct:.4f} > {L.max_single_position_pct}"
                    alerts.append(msg)
                    self._fire_alert("BREACH", msg)

        return alerts

    def _fire_alert(self, level: str, message: str) -> None:
        """Dispatch alert to callback and log."""
        logger.warning("realtime_risk.alert", level=level, message=message)
        if self._on_alert is not None:
            try:
                self._on_alert(level, message)
            except Exception:
                logger.exception("realtime_risk.alert_callback_failed")
