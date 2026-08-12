"""Execution Monitor — tracks slippage, fill quality, latency, and divergence.

Independent observability layer that detects execution degradation
before it impacts P&L. Must be consulted before and after every order.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
import statistics


class HealthStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class AlertLevel(Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


@dataclass
class OrderReport:
    """Record of an order sent to broker."""
    symbol: str
    side: str  # BUY/SELL
    signal_type: str  # REVERSAL/CONTINUATION
    session: str  # ASIAN/LONDON/NY
    expected_price: float
    stop_loss: float
    take_profit: float
    risk_usd: float
    timestamp_signal: datetime = field(default_factory=datetime.now)


@dataclass
class FillReport:
    """Record of a fill received from broker."""
    symbol: str
    side: str
    fill_price: float
    fill_quantity: float
    fill_pnl: float = 0.0
    rejected: bool = False
    rejection_reason: str = ""
    latency_ms: float = 0.0
    spread_at_fill: float = 0.0
    timestamp_fill: datetime = field(default_factory=datetime.now)

    # Optional divergence tracking
    expected_pnl: float = 0.0
    expected_slippage_bps: float = 0.0


@dataclass
class Alert:
    level: AlertLevel
    metric: str
    message: str
    symbol: str = ""
    value: float = 0.0
    threshold: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MetricStats:
    mean: float = 0.0
    median: float = 0.0
    max: float = 0.0
    min: float = 0.0
    count: int = 0
    std: float = 0.0


@dataclass
class SlippageStats:
    total_bps: MetricStats = field(default_factory=MetricStats)
    by_symbol: Dict[str, MetricStats] = field(default_factory=dict)
    # Spread anomaly: slippage beyond expected half-spread (reflects execution quality)
    total_anomaly_bps: MetricStats = field(default_factory=MetricStats)
    anomaly_by_symbol: Dict[str, MetricStats] = field(default_factory=dict)


@dataclass
class FillStats:
    total_attempts: int = 0
    total_fills: int = 0
    total_rejections: int = 0
    fill_rate: float = 1.0
    by_symbol: Dict[str, dict] = field(default_factory=dict)


@dataclass
class LatencyStats:
    ms: MetricStats = field(default_factory=MetricStats)
    by_symbol: Dict[str, MetricStats] = field(default_factory=dict)


@dataclass
class DivergenceStats:
    """Difference between backtest expectations and live paper execution."""
    total_trades: int = 0
    avg_pnl_diff_pct: float = 0.0
    slippage_impact_bps: float = 0.0
    fill_rate_impact_pct: float = 0.0
    score: float = 0.0  # 0 = exact match, higher = more divergence


@dataclass
class MonitorResult:
    health_status: HealthStatus = HealthStatus.HEALTHY
    alerts: List[Alert] = field(default_factory=list)
    slippage_stats: SlippageStats = field(default_factory=SlippageStats)
    fill_stats: FillStats = field(default_factory=FillStats)
    latency_stats: LatencyStats = field(default_factory=LatencyStats)
    divergence: DivergenceStats = field(default_factory=DivergenceStats)
    drawdown_pct: float = 0.0
    total_trades: int = 0
    reason_code: str = ""


# Default per-symbol slippage thresholds (bps).
# Symbols not listed use "_default".
# Values: warning = causes DEGRADED, critical = causes CRITICAL health.
SYMBOL_SLIPPAGE_LIMITS: Dict[str, dict] = {
    "EURUSD": {"warning": 5.0,  "critical": 10.0},
    "GBPUSD": {"warning": 6.0,  "critical": 12.0},
    "USDJPY": {"warning": 3.0,  "critical": 6.0},
    "AUDUSD": {"warning": 6.0,  "critical": 12.0},
    "USDCAD": {"warning": 6.0,  "critical": 12.0},
    "USDCHF": {"warning": 6.0,  "critical": 12.0},
    "NZDUSD": {"warning": 7.0,  "critical": 14.0},
    "XAUUSD": {"warning": 25.0, "critical": 50.0},
    "_default": {"warning": 10.0, "critical": 20.0},
}


class Monitor:
    """Execution quality monitor. Report orders and fills, then query status.

    Thresholds:
        symbol_slippage_limits: per-symbol {sym: {warning, critical}} bps.
            Any symbol not listed falls back to "_default".
        Other global thresholds listed below.
    """

    def __init__(
        self,
        initial_balance: float = 50000.0,
        symbol_slippage_limits: Optional[Dict[str, dict]] = None,
        slippage_critical_bps: Optional[float] = None,
        slippage_warning_bps: Optional[float] = None,
        min_fill_rate: float = 0.80,
        fill_rate_warning: float = 0.90,
        latency_critical_ms: float = 5000.0,
        latency_warning_ms: float = 2000.0,
        rejection_rate_critical: float = 0.20,
        divergence_critical: float = 20.0,
    ):
        self.initial_balance = initial_balance

        # Build per-symbol thresholds
        limits = dict(SYMBOL_SLIPPAGE_LIMITS)
        # Legacy global params: override warning/critical on all symbols
        warn_override = slippage_warning_bps
        crit_override = slippage_critical_bps
        if warn_override is not None or crit_override is not None:
            for k, v in limits.items():
                limits[k] = dict(v)
                if warn_override is not None:
                    limits[k]["warning"] = warn_override
                if crit_override is not None:
                    limits[k]["critical"] = crit_override
        if symbol_slippage_limits:
            limits.update(symbol_slippage_limits)
        self.symbol_slippage_limits = limits

        self.thresholds = {
            "min_fill_rate": min_fill_rate,
            "fill_rate_warning": fill_rate_warning,
            "latency_critical_ms": latency_critical_ms,
            "latency_warning_ms": latency_warning_ms,
            "rejection_rate_critical": rejection_rate_critical,
            "divergence_critical": divergence_critical,
        }

        # Accumulators
        self._slippages: List[float] = []
        self._slippages_by_symbol: Dict[str, List[float]] = {}
        self._anomalies: List[float] = []  # slippage anomaly (beyond normal spread)
        self._anomalies_by_symbol: Dict[str, List[float]] = {}
        self._latencies: List[float] = []
        self._latencies_by_symbol: Dict[str, List[float]] = {}
        self._orders: List[OrderReport] = []
        self._fills: List[FillReport] = []
        self._alerts: List[Alert] = []
        self._peak_balance: float = initial_balance
        self._current_balance: float = initial_balance

    def report_order(self, order: OrderReport):
        """Record an order being sent."""
        self._orders.append(order)

    def report_fill(self, fill: FillReport):
        """Record a fill. Computes slippage, anomaly, and latency."""
        self._fills.append(fill)

        if fill.rejected:
            return

        # Slippage in bps: diff between expected (bar close) and fill price
        expected_price = getattr(
            self._find_order(fill.symbol, fill.side), "expected_price", fill.fill_price
        )
        slippage_bps = abs(fill.fill_price - expected_price)
        slippage_bps = (slippage_bps / fill.fill_price) * 10000 if fill.fill_price > 0 else 0
        self._slippages.append(slippage_bps)
        self._slippages_by_symbol.setdefault(fill.symbol, []).append(slippage_bps)

        # Spread anomaly: slippage beyond expected half-spread
        # Normal half-spread (mid→bid/ask) is the execution cost.
        # Anomaly = what's left after subtracting that cost.
        spread_bps = (fill.spread_at_fill / fill.fill_price) * 10000 if fill.fill_price > 0 else 0
        half_spread_bps = spread_bps / 2.0
        anomaly_bps = max(0.0, slippage_bps - half_spread_bps)
        self._anomalies.append(anomaly_bps)
        self._anomalies_by_symbol.setdefault(fill.symbol, []).append(anomaly_bps)

        # Latency
        self._latencies.append(fill.latency_ms)
        self._latencies_by_symbol.setdefault(fill.symbol, []).append(fill.latency_ms)

        # Track balance drift
        self._current_balance += fill.fill_pnl
        self._peak_balance = max(self._peak_balance, self._current_balance)

    def _find_order(self, symbol: str, side: str) -> Optional[OrderReport]:
        """Find matching order for a fill (last match, FIFO)."""
        for o in reversed(self._orders):
            if o.symbol == symbol and o.side == side:
                return o
        return None

    def get_status(self) -> MonitorResult:
        """Compute current health status and return full result."""
        self._check_alerts()
        return MonitorResult(
            health_status=self._compute_health(),
            alerts=list(self._alerts),
            slippage_stats=self._compute_slippage_stats(),
            fill_stats=self._compute_fill_stats(),
            latency_stats=self._compute_latency_stats(),
            divergence=self._compute_divergence(),
            drawdown_pct=self._compute_drawdown(),
            total_trades=len(self._fills),
            reason_code=self._reason_code(),
        )

    def get_alerts(self, clear: bool = True) -> List[Alert]:
        """Return pending alerts and optionally clear them."""
        alerts = list(self._alerts)
        if clear:
            self._alerts.clear()
        return alerts

    def reset(self):
        """Clear all accumulated data."""
        self._slippages.clear()
        self._slippages_by_symbol.clear()
        self._anomalies.clear()
        self._anomalies_by_symbol.clear()
        self._latencies.clear()
        self._latencies_by_symbol.clear()
        self._orders.clear()
        self._fills.clear()
        self._alerts.clear()
        self._peak_balance = self._current_balance

    def _compute_health(self) -> HealthStatus:
        has_critical = any(a.level == AlertLevel.CRITICAL for a in self._alerts)
        has_warning = any(a.level == AlertLevel.WARNING for a in self._alerts)
        if has_critical:
            return HealthStatus.CRITICAL
        if has_warning:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def _compute_slippage_stats(self) -> SlippageStats:
        total = self._stats_from_list(self._slippages)
        by_symbol = {
            sym: self._stats_from_list(vals)
            for sym, vals in self._slippages_by_symbol.items()
        }
        total_anomaly = self._stats_from_list(self._anomalies)
        anomaly_by_symbol = {
            sym: self._stats_from_list(vals)
            for sym, vals in self._anomalies_by_symbol.items()
        }
        return SlippageStats(
            total_bps=total, by_symbol=by_symbol,
            total_anomaly_bps=total_anomaly, anomaly_by_symbol=anomaly_by_symbol,
        )

    def _compute_fill_stats(self) -> FillStats:
        total_attempts = len(self._orders)
        total_fills = sum(1 for f in self._fills if not f.rejected)
        total_rejections = sum(1 for f in self._fills if f.rejected)
        fill_rate = total_fills / total_attempts if total_attempts > 0 else 1.0

        by_symbol = {}
        for f in self._fills:
            by_symbol.setdefault(f.symbol, {"attempts": 0, "fills": 0, "rejections": 0})
            by_symbol[f.symbol]["attempts"] += 1
            if f.rejected:
                by_symbol[f.symbol]["rejections"] += 1
            else:
                by_symbol[f.symbol]["fills"] += 1

        return FillStats(
            total_attempts=total_attempts,
            total_fills=total_fills,
            total_rejections=total_rejections,
            fill_rate=round(fill_rate, 4),
            by_symbol=by_symbol,
        )

    def _compute_latency_stats(self) -> LatencyStats:
        total = self._stats_from_list(self._latencies)
        by_symbol = {
            sym: self._stats_from_list(vals)
            for sym, vals in self._latencies_by_symbol.items()
        }
        return LatencyStats(ms=total, by_symbol=by_symbol)

    def _compute_divergence(self) -> DivergenceStats:
        """Compare fill P&L vs expected P&L to measure execution drift."""
        trades_with_both = [f for f in self._fills if f.expected_pnl != 0]
        if not trades_with_both:
            return DivergenceStats()

        diffs = []
        total_slippage = 0.0
        for f in trades_with_both:
            diff_pct = abs(f.fill_pnl - f.expected_pnl) / abs(f.expected_pnl) if f.expected_pnl != 0 else 0
            diffs.append(diff_pct)
            total_slippage += f.expected_slippage_bps

        fill_stats = self._compute_fill_stats()
        fill_rate_impact = (1 - fill_stats.fill_rate) * 100

        score = (statistics.mean(diffs) * 50 +  # 50% weight on P&L diff
                 total_slippage / len(trades_with_both) * 10 +  # 10% weight on slippage
                 fill_rate_impact * 0.5)  # 0.5% per fill rate % drop

        return DivergenceStats(
            total_trades=len(trades_with_both),
            avg_pnl_diff_pct=round(statistics.mean(diffs) * 100, 2),
            slippage_impact_bps=round(total_slippage / len(trades_with_both), 2),
            fill_rate_impact_pct=round(fill_rate_impact, 2),
            score=round(score, 2),
        )

    def _compute_drawdown(self) -> float:
        if self._peak_balance <= 0:
            return 0.0
        dd = (self._peak_balance - self._current_balance) / self._peak_balance * 100
        return round(max(0, dd), 2)

    def _check_alerts(self):
        """Generate alerts based on current metrics."""
        self._check_slippage_alerts()
        self._check_fill_rate_alerts()
        self._check_latency_alerts()
        self._check_rejection_alerts()
        self._check_divergence_alerts()

    def _check_slippage_alerts(self):
        if not self._slippages:
            return
        sym_stats = self._compute_slippage_stats()

        # Per-symbol anomaly alerts (slippage beyond normal spread)
        for sym in sym_stats.anomaly_by_symbol:
            anomaly_mean = sym_stats.anomaly_by_symbol[sym].mean
            limits = self.symbol_slippage_limits.get(
                sym, self.symbol_slippage_limits["_default"]
            )
            if anomaly_mean > limits["critical"]:
                self._alerts.append(Alert(
                    AlertLevel.CRITICAL, "slippage_anomaly",
                    f"Slippage anomaly on {sym}: {anomaly_mean:.1f} bps"
                    f" (exceeds {limits['critical']:.0f} bps crit threshold)",
                    symbol=sym, value=anomaly_mean,
                    threshold=limits["critical"]))
            elif anomaly_mean > limits["warning"]:
                self._alerts.append(Alert(
                    AlertLevel.WARNING, "slippage_anomaly",
                    f"Slippage anomaly on {sym}: {anomaly_mean:.1f} bps",
                    symbol=sym, value=anomaly_mean,
                    threshold=limits["warning"]))

        # Overall anomaly alert (warning at 5 bps)
        if sym_stats.total_anomaly_bps.count > 0:
            overall_anomaly = sym_stats.total_anomaly_bps.mean
            if overall_anomaly > 5.0:
                self._alerts.append(Alert(
                    AlertLevel.WARNING, "slippage_anomaly",
                    f"Overall anomaly {overall_anomaly:.1f} bps — check execution quality",
                    value=overall_anomaly, threshold=5.0))

    def _check_fill_rate_alerts(self):
        fs = self._compute_fill_stats()
        if fs.total_attempts < 5:
            return
        if fs.fill_rate < self.thresholds["min_fill_rate"]:
            self._alerts.append(Alert(
                AlertLevel.CRITICAL, "fill_rate",
                f"Fill rate {fs.fill_rate:.1%} below {self.thresholds['min_fill_rate']:.0%}",
                value=fs.fill_rate, threshold=self.thresholds["min_fill_rate"]))
        elif fs.fill_rate < self.thresholds["fill_rate_warning"]:
            self._alerts.append(Alert(
                AlertLevel.WARNING, "fill_rate",
                f"Fill rate dropping: {fs.fill_rate:.1%}",
                value=fs.fill_rate, threshold=self.thresholds["fill_rate_warning"]))

    def _check_latency_alerts(self):
        if not self._latencies:
            return
        avg = statistics.mean(self._latencies)
        if avg > self.thresholds["latency_critical_ms"]:
            self._alerts.append(Alert(
                AlertLevel.CRITICAL, "latency",
                f"Avg latency {avg:.0f}ms exceeds critical {self.thresholds['latency_critical_ms']:.0f}ms",
                value=avg, threshold=self.thresholds["latency_critical_ms"]))
        elif avg > self.thresholds["latency_warning_ms"]:
            self._alerts.append(Alert(
                AlertLevel.WARNING, "latency",
                f"Latency rising: {avg:.0f}ms",
                value=avg, threshold=self.thresholds["latency_warning_ms"]))

    def _check_rejection_alerts(self):
        fs = self._compute_fill_stats()
        if fs.total_attempts < 5:
            return
        rejection_rate = fs.total_rejections / fs.total_attempts if fs.total_attempts > 0 else 0
        if rejection_rate > self.thresholds["rejection_rate_critical"]:
            self._alerts.append(Alert(
                AlertLevel.CRITICAL, "rejection",
                f"Rejection rate {rejection_rate:.1%} exceeds {self.thresholds['rejection_rate_critical']:.0%}",
                value=rejection_rate, threshold=self.thresholds["rejection_rate_critical"]))

    def _check_divergence_alerts(self):
        d = self._compute_divergence()
        if d.total_trades < 5:
            return
        if d.score > self.thresholds["divergence_critical"]:
            self._alerts.append(Alert(
                AlertLevel.CRITICAL, "divergence",
                f"Execution divergence score {d.score:.1f} above {self.thresholds['divergence_critical']}",
                value=d.score, threshold=self.thresholds["divergence_critical"]))

    def _reason_code(self) -> str:
        if not self._alerts:
            return "HEALTHY"
        critical = [a for a in self._alerts if a.level == AlertLevel.CRITICAL]
        if critical:
            return f"CRITICAL:{','.join(a.metric.upper() for a in critical)}"
        return f"DEGRADED:{','.join(a.metric.upper() for a in self._alerts)}"

    @staticmethod
    def _stats_from_list(vals: List[float]) -> MetricStats:
        if not vals:
            return MetricStats()
        return MetricStats(
            mean=round(statistics.mean(vals), 4),
            median=round(statistics.median(vals), 4),
            max=round(max(vals), 4),
            min=round(min(vals), 4),
            count=len(vals),
            std=round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
        )
