"""Pre-trade risk gate adapter for OMS integration.

Provides a ``check_order_sync(order)`` interface compatible with the OMS
risk engine contract.  Wraps the existing KillSwitch, CircuitBreaker, and
RiskPolicy infrastructure into a single callable gate.

Checks:
  1. Kill switch — blocks all orders if active or paused
  2. Circuit breaker — blocks orders for the asset class
  3. Price sanity — rejects trades when current price is >3σ from 20-period SMA

Usage::

    from risk.pre_trade_gate import PreTradeRiskGate
    from risk.kill_switch import KillSwitch

    gate = PreTradeRiskGate(
        kill_switch=KillSwitch("data/kill_switch_state.json"),
    )
    result = gate.check_order_sync(order)
    if not result.passed:
        print(f"Rejected: {result.reason}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from ..core.symbol_registry import symbol_to_asset_class  # noqa: F401 — re-exported for backward compat

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type expected by OMS
# ---------------------------------------------------------------------------


@dataclass
class RiskCheckResult:
    """Result of a pre-trade risk check.  Compatible with OMS contract."""

    passed: bool
    reason: str = ""


# ---------------------------------------------------------------------------
# Protocols (duck-typed dependencies)
# ---------------------------------------------------------------------------


class KillSwitchLike(Protocol):
    def is_active(self) -> bool: ...
    def is_paused(self) -> bool: ...


class CircuitBreakerLike(Protocol):
    def is_open(self, asset_class: str) -> bool: ...


# symbol_to_asset_class is imported from core.symbol_registry and re-exported above.


# ---------------------------------------------------------------------------
# Price sanity check
# ---------------------------------------------------------------------------


def price_sanity_check(
    current_price: float,
    recent_prices: list[float],
    max_std_deviations: float = 3.0,
    sma_period: int = 20,
) -> tuple[bool, str]:
    """Validate that current price is within N standard deviations of the SMA.

    This rejects garbage data: if the current price is anomalously far from
    the recent moving average, the trade is likely based on bad data.

    Args:
        current_price: The price to validate.
        recent_prices: Recent price history (at least ``sma_period`` values).
                       If fewer values are available, all are used.
        max_std_deviations: Maximum allowed deviations from SMA (default 3.0).
        sma_period: Lookback period for SMA calculation (default 20).

    Returns:
        ``(passed, reason)`` tuple. ``passed=True`` means price is sane.
    """
    if current_price <= 0:
        return False, f"Invalid current price: {current_price}"

    if not recent_prices or len(recent_prices) < 2:
        # Not enough data — cannot validate, allow trade
        logger.debug("price_sanity_check: insufficient data (%d prices), allowing", len(recent_prices))
        return True, ""

    # Use the last N prices for SMA calculation
    window = recent_prices[-sma_period:]

    sma = sum(window) / len(window)

    # Calculate standard deviation
    variance = sum((p - sma) ** 2 for p in window) / len(window)
    std_dev = variance**0.5

    if std_dev == 0:
        # All prices are identical — allow (no volatility)
        return True, ""

    z_score = (current_price - sma) / std_dev

    if abs(z_score) > max_std_deviations:
        reason = (
            f"Price anomaly: current={current_price:.5f} is "
            f"{abs(z_score):.2f}σ from SMA({sma_period})={sma:.5f} "
            f"(threshold={max_std_deviations}σ, std={std_dev:.5f})"
        )
        logger.warning("price_sanity_check REJECTED: %s", reason)
        return False, reason

    return True, ""


# ---------------------------------------------------------------------------
# Price data provider protocol
# ---------------------------------------------------------------------------


class PriceDataProvider(Protocol):
    """Protocol for providing recent price data to the risk gate."""

    def get_recent_prices(self, symbol: str, count: int) -> list[float]:
        """Return the last ``count`` prices for ``symbol``.

        The most recent price should be the last element.
        Returns an empty list if data is unavailable.
        """
        ...


# ---------------------------------------------------------------------------
# Pre-trade risk gate
# ---------------------------------------------------------------------------


class PreTradeRiskGate:
    """Lightweight risk gate for script-level OMS integration.

    Checks (in order):
    1. Kill switch — blocks all orders if active or paused
    2. Circuit breaker — blocks orders for the asset class
    3. Price sanity — rejects trades when price is >3σ from 20-period SMA

    This is intentionally minimal.  Full 4-layer risk evaluation belongs
    in ``RiskEngine.evaluate()`` for production live trading.
    """

    def __init__(
        self,
        kill_switch: KillSwitchLike | None = None,
        circuit_breaker: CircuitBreakerLike | None = None,
        price_provider: PriceDataProvider | None = None,
        price_sma_period: int = 20,
        price_max_std_dev: float = 3.0,
    ) -> None:
        self._kill_switch = kill_switch
        self._circuit_breaker = circuit_breaker
        self._price_provider = price_provider
        self._price_sma_period = price_sma_period
        self._price_max_std_dev = price_max_std_dev

    def check_order_sync(self, order: Any) -> RiskCheckResult:
        """Check an order against kill switch, circuit breaker, and price sanity.

        Args:
            order: An ``Order`` object (or any object with ``symbol`` and
                   ``asset_class`` attributes).

        Returns:
            ``RiskCheckResult(passed=True)`` if all checks pass,
            ``RiskCheckResult(passed=False, reason=...)`` if rejected.
        """
        # 1. Kill switch
        if self._kill_switch is not None:
            try:
                if self._kill_switch.is_active():
                    return RiskCheckResult(passed=False, reason="Kill switch is active")
                if self._kill_switch.is_paused():
                    return RiskCheckResult(passed=False, reason="Kill switch is paused — no new entries")
            except Exception as exc:
                logger.warning("Kill switch check failed: %s — rejecting as precaution", exc)
                return RiskCheckResult(passed=False, reason=f"Kill switch error: {exc}")

        # 2. Circuit breaker
        if self._circuit_breaker is not None:
            try:
                asset_class = getattr(order, "asset_class", "")
                if asset_class and self._circuit_breaker.is_open(asset_class):
                    return RiskCheckResult(
                        passed=False,
                        reason=f"Circuit breaker open for {asset_class}",
                    )
            except Exception as exc:
                logger.warning("Circuit breaker check failed: %s", exc)

        # 3. Price sanity check
        if self._price_provider is not None:
            try:
                symbol = getattr(order, "symbol", "")
                if symbol:
                    # Get current price (most recent)
                    prices = self._price_provider.get_recent_prices(symbol, self._price_sma_period + 1)
                    if prices and len(prices) >= 2:
                        current_price = prices[-1]
                        passed, reason = price_sanity_check(
                            current_price=current_price,
                            recent_prices=prices[:-1],  # Exclude current from SMA
                            max_std_deviations=self._price_max_std_dev,
                            sma_period=self._price_sma_period,
                        )
                        if not passed:
                            return RiskCheckResult(passed=False, reason=reason)
            except Exception as exc:
                logger.warning("Price sanity check failed: %s — rejecting as precaution", exc)
                return RiskCheckResult(passed=False, reason=f"Price check error: {exc}")

        return RiskCheckResult(passed=True)
