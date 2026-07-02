"""
Spread Monitor for Quant OS

Tracks bid-ask spread per symbol:
- Rolling baseline (mean + std) over last N samples
- Real-time wide-spread detection via multiplier threshold
- Decimal precision throughout
"""

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class SpreadState:
    """Immutable snapshot of spread monitoring state."""

    symbol: str
    current_spread_points: Decimal
    baseline_mean: Decimal
    baseline_std: Decimal
    spread_multiplier: float  # current / baseline_mean (0 if baseline is 0)
    is_wide: bool
    sample_count: int
    last_update_utc: datetime


class SpreadMonitor:
    """
    Per-symbol spread monitor.

    Maintains a rolling window of spread samples and computes
    mean / std to detect abnormally wide spreads.  A spread is
    flagged as wide when it exceeds baseline_mean + reject_multiplier * baseline_std.
    """

    def __init__(
        self,
        symbol: str,
        baseline_window: int = 500,
        reject_multiplier: float = 2.0,
    ):
        self._symbol = symbol
        self._baseline_window = baseline_window
        self._reject_multiplier = reject_multiplier

        self._spreads: list[Decimal] = []
        self._baseline_mean: Decimal = Decimal("0")
        self._baseline_std: Decimal = Decimal("0")
        self._last_spread: Decimal = Decimal("0")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_tick(self, bid: Decimal, ask: Decimal, timestamp: datetime) -> SpreadState:
        """
        Process a new tick and update spread tracking.

        Args:
            bid: Best bid price.
            ask: Best ask price.
            timestamp: Tick timestamp (exchange or local).

        Returns:
            Updated SpreadState.
        """
        if bid <= 0 or ask <= 0 or ask < bid:
            # Invalid quotes — return current state unchanged
            return self.get_state()

        spread = ask - bid
        self._last_spread = spread
        self._spreads.append(spread)

        # Trim to rolling window
        if len(self._spreads) > self._baseline_window:
            self._spreads = self._spreads[-self._baseline_window :]

        # Recompute baseline
        self._recalculate_baseline()

        return self.get_state()

    def is_wide_spread(self, current_spread: Decimal) -> bool:
        """Check if a given spread exceeds the acceptable band."""
        if self._baseline_mean == 0 or self._baseline_std == 0:
            # Insufficient baseline — only reject extreme outliers (> 10x mean)
            return self._baseline_mean > 0 and current_spread > self._baseline_mean * 10

        threshold = self._baseline_mean + Decimal(str(self._reject_multiplier)) * self._baseline_std
        return current_spread > threshold

    def get_baseline(self) -> tuple[Decimal, Decimal]:
        """Return (mean, std) of the current rolling baseline."""
        return self._baseline_mean, self._baseline_std

    def get_state(self) -> SpreadState:
        """Return a snapshot of the current spread monitoring state."""
        multiplier = 0.0
        if self._baseline_mean > 0:
            multiplier = float(self._last_spread / self._baseline_mean)

        return SpreadState(
            symbol=self._symbol,
            current_spread_points=self._last_spread,
            baseline_mean=self._baseline_mean,
            baseline_std=self._baseline_std,
            spread_multiplier=multiplier,
            is_wide=self.is_wide_spread(self._last_spread),
            sample_count=len(self._spreads),
            last_update_utc=datetime.now(UTC),
        )

    def reset(self) -> None:
        """Clear all samples and reset baseline to zero."""
        self._spreads.clear()
        self._baseline_mean = Decimal("0")
        self._baseline_std = Decimal("0")
        self._last_spread = Decimal("0")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalculate_baseline(self) -> None:
        """Recompute mean and std from the rolling window."""
        if not self._spreads:
            self._baseline_mean = Decimal("0")
            self._baseline_std = Decimal("0")
            return

        # Convert to float for statistics, then back to Decimal
        float_spreads = [float(s) for s in self._spreads]
        mean = statistics.mean(float_spreads)
        self._baseline_mean = Decimal(str(round(mean, 10)))

        if len(float_spreads) >= 2:
            std = statistics.stdev(float_spreads)
            self._baseline_std = Decimal(str(round(std, 10)))
        else:
            self._baseline_std = Decimal("0")
