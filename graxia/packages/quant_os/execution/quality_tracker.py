"""Execution quality tracking — slippage, fill rates, latency metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class FillOutcome(str, Enum):
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    REQUOTED = "REQUOTED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class FillRecord:
    """Single fill event for quality tracking."""

    order_id: str
    symbol: str
    side: str
    expected_price: Decimal
    actual_price: Decimal
    quantity: Decimal
    filled_quantity: Decimal
    outcome: FillOutcome
    timestamp: datetime
    latency_ms: float
    spread_at_entry: Decimal | None = None
    raw_response: dict | None = None


@dataclass(frozen=True)
class SlippageReport:
    """Slippage analysis for a single fill."""

    symbol: str
    side: str
    expected_price: Decimal
    actual_price: Decimal
    slippage_pips: Decimal
    slippage_cost: Decimal
    spread_component: Decimal
    adverse_component: Decimal
    within_spread: bool


@dataclass
class QualityMetrics:
    """Aggregated execution quality metrics."""

    symbol: str
    period_start: datetime
    period_end: datetime
    total_fills: int
    filled: int
    partial: int
    rejected: int
    requoted: int
    timeout: int
    fill_rate: Decimal
    requote_rate: Decimal
    avg_slippage_pips: Decimal
    median_slippage_pips: Decimal
    max_slippage_pips: Decimal
    p95_slippage_pips: Decimal
    avg_latency_ms: float
    median_latency_ms: float
    max_latency_ms: float
    total_slippage_cost: Decimal
    adverse_fill_pct: Decimal


class ExecutionQualityTracker:
    """Tracks execution quality across fills.

    Records fills, calculates slippage, and aggregates quality metrics
    per symbol and over rolling windows.

    Usage:
        tracker = ExecutionQualityTracker(pip_size=Decimal("0.01"))
        tracker.record_fill(fill_record)
        metrics = tracker.get_quality_metrics("XAUUSD", lookback_hours=24)
    """

    def __init__(
        self,
        pip_size: Decimal = Decimal("0.01"),
        adverse_threshold_pips: Decimal = Decimal("0.5"),
        max_history: int = 10_000,
    ) -> None:
        self._pip_size = pip_size
        self._adverse_threshold = adverse_threshold_pips
        self._max_history = max_history
        self._fills: list[FillRecord] = []
        logger.info(
            "quality_tracker.init",
            pip_size=str(pip_size),
            adverse_threshold=str(adverse_threshold_pips),
        )

    def record_fill(self, fill: FillRecord) -> SlippageReport:
        """Record a fill event and return slippage analysis."""
        report = self.calculate_slippage(fill)
        self._fills.append(fill)
        if len(self._fills) > self._max_history:
            self._fills = self._fills[-self._max_history :]
        logger.info(
            "fill.recorded",
            order_id=fill.order_id,
            symbol=fill.symbol,
            outcome=fill.outcome.value,
            slippage_pips=str(report.slippage_pips),
            latency_ms=fill.latency_ms,
        )
        return report

    def calculate_slippage(self, fill: FillRecord) -> SlippageReport:
        """Calculate slippage breakdown for a fill."""
        price_diff = fill.actual_price - fill.expected_price
        if fill.side == "SELL":
            price_diff = -price_diff
        slippage_pips = (price_diff / self._pip_size).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        slippage_cost = (price_diff * fill.filled_quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        spread_component = Decimal("0")
        if fill.spread_at_entry is not None:
            spread_component = (fill.spread_at_entry / self._pip_size / 2).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
        adverse_component = max(slippage_pips - spread_component, Decimal("0"))
        within_spread = adverse_component <= 0
        return SlippageReport(
            symbol=fill.symbol,
            side=fill.side,
            expected_price=fill.expected_price,
            actual_price=fill.actual_price,
            slippage_pips=slippage_pips,
            slippage_cost=slippage_cost,
            spread_component=spread_component,
            adverse_component=adverse_component,
            within_spread=within_spread,
        )

    def get_quality_metrics(
        self,
        symbol: str,
        lookback_hours: int | None = None,
    ) -> QualityMetrics:
        """Aggregate quality metrics for a symbol over a time window."""
        now = datetime.now(UTC)
        if lookback_hours is not None:
            cutoff = now - timedelta(hours=lookback_hours)
            fills = [f for f in self._fills if f.symbol == symbol and f.timestamp >= cutoff]
        else:
            fills = [f for f in self._fills if f.symbol == symbol]

        if not fills:
            return QualityMetrics(
                symbol=symbol,
                period_start=now,
                period_end=now,
                total_fills=0,
                filled=0,
                partial=0,
                rejected=0,
                requoted=0,
                timeout=0,
                fill_rate=Decimal("0"),
                requote_rate=Decimal("0"),
                avg_slippage_pips=Decimal("0"),
                median_slippage_pips=Decimal("0"),
                max_slippage_pips=Decimal("0"),
                p95_slippage_pips=Decimal("0"),
                avg_latency_ms=0.0,
                median_latency_ms=0.0,
                max_latency_ms=0.0,
                total_slippage_cost=Decimal("0"),
                adverse_fill_pct=Decimal("0"),
            )

        total = len(fills)
        filled = sum(1 for f in fills if f.outcome == FillOutcome.FILLED)
        partial = sum(1 for f in fills if f.outcome == FillOutcome.PARTIAL)
        rejected = sum(1 for f in fills if f.outcome == FillOutcome.REJECTED)
        requoted = sum(1 for f in fills if f.outcome == FillOutcome.REQUOTED)
        timeout = sum(1 for f in fills if f.outcome == FillOutcome.TIMEOUT)

        fill_rate = (Decimal(filled) / Decimal(total)).quantize(Decimal("0.0001"))
        requote_rate = (Decimal(requoted) / Decimal(total)).quantize(Decimal("0.0001"))

        slips = [self.calculate_slippage(f).slippage_pips for f in fills]
        slips_sorted = sorted(slips)
        avg_slip = (sum(slips) / len(slips)).quantize(Decimal("0.001"))
        med_slip = slips_sorted[len(slips_sorted) // 2]
        max_slip = max(slips)
        p95_idx = int(len(slips_sorted) * 0.95)
        p95_slip = slips_sorted[min(p95_idx, len(slips_sorted) - 1)]

        latencies = [f.latency_ms for f in fills]
        avg_lat = sum(latencies) / len(latencies)
        med_lat = sorted(latencies)[len(latencies) // 2]
        max_lat = max(latencies)

        total_cost = sum(self.calculate_slippage(f).slippage_cost for f in fills)

        adverse_count = sum(1 for f in fills if self.calculate_slippage(f).adverse_component > 0)
        adverse_pct = (Decimal(adverse_count) / Decimal(total)).quantize(Decimal("0.0001"))

        period_start = min(f.timestamp for f in fills)
        period_end = max(f.timestamp for f in fills)

        metrics = QualityMetrics(
            symbol=symbol,
            period_start=period_start,
            period_end=period_end,
            total_fills=total,
            filled=filled,
            partial=partial,
            rejected=rejected,
            requoted=requoted,
            timeout=timeout,
            fill_rate=fill_rate,
            requote_rate=requote_rate,
            avg_slippage_pips=avg_slip,
            median_slippage_pips=med_slip,
            max_slippage_pips=max_slip,
            p95_slippage_pips=p95_slip,
            avg_latency_ms=round(avg_lat, 2),
            median_latency_ms=round(med_lat, 2),
            max_latency_ms=round(max_lat, 2),
            total_slippage_cost=total_cost,
            adverse_fill_pct=adverse_pct,
        )
        logger.info(
            "quality.metrics.computed",
            symbol=symbol,
            total_fills=total,
            fill_rate=str(fill_rate),
            avg_slippage=str(avg_slip),
        )
        return metrics

    def get_slippage_history(self, symbol: str, lookback_hours: int | None = None) -> list[SlippageReport]:
        """Return slippage reports for a symbol."""
        now = datetime.now(UTC)
        fills = [f for f in self._fills if f.symbol == symbol]
        if lookback_hours is not None:
            cutoff = now - timedelta(hours=lookback_hours)
            fills = [f for f in fills if f.timestamp >= cutoff]
        return [self.calculate_slippage(f) for f in fills]

    def detect_adverse_fills(self, symbol: str, lookback_hours: int | None = None) -> list[FillRecord]:
        """Return fills with adverse slippage beyond threshold."""
        reports = self.get_slippage_history(symbol, lookback_hours)
        adverse_fills = []
        for report in reports:
            if report.adverse_component > self._adverse_threshold:
                fill = next(
                    f
                    for f in self._fills
                    if f.symbol == symbol
                    and f.expected_price == report.expected_price
                    and f.actual_price == report.actual_price
                )
                adverse_fills.append(fill)
        if adverse_fills:
            logger.warning(
                "adverse.fills.detected",
                symbol=symbol,
                count=len(adverse_fills),
            )
        return adverse_fills

    def compare_expected_vs_actual(
        self,
        order_id: str,
        expected_price: Decimal,
        actual_price: Decimal,
        side: str,
    ) -> dict:
        """Quick comparison of expected vs actual execution."""
        price_diff = actual_price - expected_price
        if side == "SELL":
            price_diff = -price_diff
        slippage_pips = (price_diff / self._pip_size).quantize(Decimal("0.001"))
        is_favorable = price_diff < 0
        return {
            "order_id": order_id,
            "expected": str(expected_price),
            "actual": str(actual_price),
            "difference": str(price_diff),
            "slippage_pips": str(slippage_pips),
            "is_favorable": is_favorable,
            "verdict": "FAVORABLE" if is_favorable else "ADVERSE",
        }

    @property
    def total_fills_tracked(self) -> int:
        return len(self._fills)
