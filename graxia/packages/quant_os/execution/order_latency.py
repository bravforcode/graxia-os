"""Phase 4 — Order Latency Measurement.

Tracks end-to-end order execution latency for calibration:
- Signal generation → order submission
- Order submission → broker acknowledgment
- Broker acknowledgment → fill confirmation
- Fill confirmation → position update

Research:
- IB TWS: typical round-trip 50-200ms
- Pepperstone Razor: 50-300ms latency
- Backtest vs live gap: ~0.3-0.5 Sharpe attributable to execution errors
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from statistics import mean, median, stdev


@dataclass
class LatencyRecord:
    """Single order latency measurement."""

    order_id: str
    signal_time: float  # Time signal was generated
    submit_time: float  # Time order was submitted
    ack_time: float = 0.0  # Time broker acknowledged
    fill_time: float = 0.0  # Time fill was confirmed
    update_time: float = 0.0  # Time position was updated

    @property
    def signal_to_submit_ms(self) -> float:
        """Latency from signal to order submission."""
        return (self.submit_time - self.signal_time) * 1000

    @property
    def submit_to_ack_ms(self) -> float:
        """Latency from submission to broker acknowledgment."""
        if self.ack_time <= 0:
            return 0.0
        return (self.ack_time - self.submit_time) * 1000

    @property
    def ack_to_fill_ms(self) -> float:
        """Latency from acknowledgment to fill."""
        if self.fill_time <= 0 or self.ack_time <= 0:
            return 0.0
        return (self.fill_time - self.ack_time) * 1000

    @property
    def total_latency_ms(self) -> float:
        """Total end-to-end latency."""
        if self.fill_time <= 0:
            return 0.0
        return (self.fill_time - self.signal_time) * 1000


class OrderLatencyTracker:
    """Tracks and aggregates order execution latency.

    Used to calibrate backtest slippage assumptions against live execution.
    """

    def __init__(self):
        self._records: list[LatencyRecord] = []

    def record_order(
        self,
        order_id: str,
        signal_time: float,
        submit_time: float,
        ack_time: float = 0.0,
        fill_time: float = 0.0,
        update_time: float = 0.0,
    ):
        """Record an order's latency measurements.

        Args:
            order_id: Unique order identifier
            signal_time: Time signal was generated (epoch seconds)
            submit_time: Time order was submitted
            ack_time: Time broker acknowledged
            fill_time: Time fill was confirmed
            update_time: Time position was updated
        """
        self._records.append(LatencyRecord(
            order_id=order_id,
            signal_time=signal_time,
            submit_time=submit_time,
            ack_time=ack_time,
            fill_time=fill_time,
            update_time=update_time,
        ))

    def get_statistics(self) -> dict:
        """Get aggregate latency statistics.

        Returns:
            Dict with mean, median, std, p95, p99 for each latency component
        """
        if not self._records:
            return {"total_orders": 0}

        signal_to_submit = [r.signal_to_submit_ms for r in self._records]
        submit_to_ack = [r.submit_to_ack_ms for r in self._records if r.ack_time > 0]
        ack_to_fill = [r.ack_to_fill_ms for r in self._records if r.fill_time > 0 and r.ack_time > 0]
        total = [r.total_latency_ms for r in self._records if r.fill_time > 0]

        def _stats(values: list[float]) -> dict:
            if not values:
                return {"mean": 0, "median": 0, "std": 0, "p95": 0, "p99": 0}
            sorted_v = sorted(values)
            p95_idx = int(0.95 * len(sorted_v))
            p99_idx = int(0.99 * len(sorted_v))
            return {
                "mean": round(mean(values), 2),
                "median": round(median(values), 2),
                "std": round(stdev(values), 2) if len(values) > 1 else 0.0,
                "p95": round(sorted_v[min(p95_idx, len(sorted_v) - 1)], 2),
                "p99": round(sorted_v[min(p99_idx, len(sorted_v) - 1)], 2),
            }

        return {
            "total_orders": len(self._records),
            "signal_to_submit_ms": _stats(signal_to_submit),
            "submit_to_ack_ms": _stats(submit_to_ack),
            "ack_to_fill_ms": _stats(ack_to_fill),
            "total_latency_ms": _stats(total),
        }

    def calibrate_backtest_slippage(self) -> float:
        """Calculate recommended backtest slippage from live latency data.

        Uses total latency to estimate additional slippage beyond spread.

        Returns:
            Recommended slippage in pips for backtest
        """
        stats = self.get_statistics()
        total = stats.get("total_latency_ms", {})
        if not total or total.get("mean", 0) == 0:
            return 0.0

        # Rough estimate: 1ms latency ≈ 0.001 pips slippage for XAUUSD
        # This is very approximate; real calibration requires tick data
        mean_latency_ms = total.get("mean", 0)
        p95_latency_ms = total.get("p95", 0)

        # Use P95 for conservative calibration
        recommended_slippage = p95_latency_ms * 0.001
        return round(recommended_slippage, 4)

    def reset(self):
        """Reset for a new session."""
        self._records.clear()
