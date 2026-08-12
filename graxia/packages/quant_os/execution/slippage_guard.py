"""Slippage Guard — rejects orders when current price deviates too far from expected.

Fills during flash crashes or stale quotes can be devastating.  This guard
compares the expected price (signal price) against the live bid/ask spread
and rejects the order if the deviation exceeds a configurable threshold.

Usage::

    from execution.slippage_guard import SlippageGuard

    guard = SlippageGuard()
    result = guard.check(
        symbol="EURUSD",
        side="BUY",
        expected_price=1.0850,
        current_bid=1.0848,
        current_ask=1.0852,
    )
    if not result.allowed:
        print(f"Rejected: {result.reason} (deviation={result.deviation_bps:.1f} bps)")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..core.symbol_registry import symbol_to_asset_class as _symbol_to_asset_class

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default slippage thresholds (basis points)
# ---------------------------------------------------------------------------

# Asset class → max allowed deviation in bps
# Crypto: wider due to volatility; FX: tight
_DEFAULT_MAX_BPS: dict[str, float] = {
    "crypto": 50.0,
    "forex": 10.0,
    "metals": 20.0,
    "indices": 30.0,
}

# Symbol overrides (symbol → max_bps)
_SYMBOL_OVERRIDES: dict[str, float] = {
    "BTCUSD": 100.0,  # BTC can gap widely
    "ETHUSD": 80.0,
    "XAUUSD": 25.0,  # Gold: moderate
    "EURUSD": 8.0,  # Majors: tight
    "GBPUSD": 10.0,
    "USDJPY": 10.0,
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlippageCheckResult:
    """Outcome of a slippage check."""

    allowed: bool
    reason: str = ""
    expected_price: float = 0.0
    current_price: float = 0.0
    deviation_bps: float = 0.0
    max_bps: float = 0.0


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class SlippageGuard:
    """Reject orders when price deviation exceeds a basis-point threshold.

    Parameters:
        max_bps: Global default max deviation in basis points.
        symbol_overrides: Per-symbol max bps overrides.
        asset_class_defaults: Per-asset-class default max bps.
    """

    def __init__(
        self,
        max_bps: float | None = None,
        symbol_overrides: dict[str, float] | None = None,
        asset_class_defaults: dict[str, float] | None = None,
    ) -> None:
        self._global_default = max_bps
        self._symbol_overrides = symbol_overrides if symbol_overrides is not None else dict(_SYMBOL_OVERRIDES)
        self._asset_class_defaults = (
            asset_class_defaults if asset_class_defaults is not None else dict(_DEFAULT_MAX_BPS)
        )

    def _resolve_max_bps(self, symbol: str) -> float:
        """Determine the max allowed slippage in bps for a symbol."""
        sym = symbol.upper()
        if sym in self._symbol_overrides:
            return self._symbol_overrides[sym]
        if self._global_default is not None:
            return self._global_default
        asset_class = _symbol_to_asset_class(sym)
        return self._asset_class_defaults.get(asset_class, 10.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        symbol: str,
        side: str,
        expected_price: float,
        current_bid: float,
        current_ask: float,
    ) -> SlippageCheckResult:
        """Compare expected price against live bid/ask and reject if too far.

        For BUY orders, we compare against the ask (what we'd pay).
        For SELL orders, we compare against the bid (what we'd receive).

        Args:
            symbol: MT5 symbol (e.g. "EURUSD").
            side: "BUY" or "SELL".
            expected_price: The price at which the signal was generated.
            current_bid: Current bid price.
            current_ask: Current ask price.

        Returns:
            ``SlippageCheckResult(allowed=True)`` if within threshold,
            or ``SlippageCheckResult(allowed=False, reason=...)`` if rejected.
        """
        max_bps = self._resolve_max_bps(symbol)
        side_upper = side.upper()

        # Determine execution price (what we'd actually pay/receive)
        if side_upper == "BUY":
            exec_price = current_ask
        elif side_upper == "SELL":
            exec_price = current_bid
        else:
            return SlippageCheckResult(
                allowed=False,
                reason=f"Unknown side: {side}",
                max_bps=max_bps,
            )

        # Guard against zero/missing prices
        if expected_price <= 0 or exec_price <= 0:
            return SlippageCheckResult(
                allowed=False,
                reason=f"Invalid price: expected={expected_price}, exec={exec_price}",
                expected_price=expected_price,
                current_price=exec_price,
                max_bps=max_bps,
            )

        # Compute deviation in basis points
        deviation = abs(exec_price - expected_price)
        deviation_bps = (deviation / expected_price) * 10_000

        if deviation_bps > max_bps:
            return SlippageCheckResult(
                allowed=False,
                reason=(
                    f"Slippage {deviation_bps:.1f} bps exceeds max {max_bps:.1f} bps "
                    f"({symbol} {side_upper} expected={expected_price:.5f} "
                    f"exec={exec_price:.5f} diff={deviation:.5f})"
                ),
                expected_price=expected_price,
                current_price=exec_price,
                deviation_bps=round(deviation_bps, 2),
                max_bps=max_bps,
            )

        return SlippageCheckResult(
            allowed=True,
            expected_price=expected_price,
            current_price=exec_price,
            deviation_bps=round(deviation_bps, 2),
            max_bps=max_bps,
        )

    def should_reject(
        self,
        symbol: str,
        side: str,
        expected_price: float,
        current_bid: float,
        current_ask: float,
    ) -> tuple[bool, str]:
        """Convenience: returns ``(should_reject, reason)`` for logging."""
        result = self.check(symbol, side, expected_price, current_bid, current_ask)
        return (not result.allowed, result.reason)
