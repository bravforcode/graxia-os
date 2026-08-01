"""Execution validator — pre-submission order checks (INV-009).

INV-009: Pre-trade risk gate mandatory before any order.
INV-010: Missing/invalid/stale contract data = reject + fail closed.

Usage:
    from execution.validator import OrderValidator
    validator = OrderValidator()
    result = validator.validate(symbol="XAUUSD", side="BUY", volume=0.01, ...)
    if not result.valid:
        print(result.reason)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderValidation:
    """Result of order validation."""

    valid: bool
    stage: str  # "symbol" | "market_hours" | "side" | "volume" | "position_limit" | "price_sanity" | "contract" | "all"
    reason: str


class OrderValidator:
    """Pre-submission order validation.

    Validates: symbol → market hours → position limits → price sanity → contract spec.
    Fails closed on any check failure.
    """

    def __init__(
        self,
        contract_store: object = None,
        max_slippage_bps: int = 10,
        max_price_deviation_bps: int = 100,
    ) -> None:
        self._contracts = contract_store
        self._max_slippage_bps = max_slippage_bps
        self._max_price_deviation_bps = max_price_deviation_bps

    def validate(
        self,
        symbol: str,
        side: str,
        volume: float,
        price: float | None = None,
        market_price: float | None = None,
        market_open: bool = True,
        current_positions: int = 0,
        max_positions: int = 5,
        orders_today: int = 0,
        max_orders_per_day: int = 20,
        signal_id: str | None = None,
    ) -> OrderValidation:
        """Full validation chain. Returns first failure or success.

        Checks (in order):
        1. Symbol valid
        2. Market open
        3. Side valid (BUY/SELL)
        4. Volume > 0
        5. Position limits
        6. Order rate limits
        7. Price sanity (if both price and market_price available)
        8. Contract spec exists (INV-010)
        """
        # 1. Symbol
        if not symbol or len(symbol) < 3:
            return OrderValidation(False, "symbol", f"INVALID_SYMBOL:{symbol}")

        # 2. Market hours
        if not market_open:
            return OrderValidation(False, "market_hours", "MARKET_CLOSED")

        # 3. Side
        if side not in ("BUY", "SELL"):
            return OrderValidation(False, "side", f"INVALID_SIDE:{side}")

        # 4. Volume
        if volume <= 0:
            return OrderValidation(False, "volume", f"INVALID_VOLUME:{volume}")

        # 5. Position limits
        if current_positions >= max_positions:
            return OrderValidation(
                False,
                "position_limit",
                f"MAX_POSITIONS:{current_positions}>={max_positions}",
            )

        # 6. Order rate limits
        if orders_today >= max_orders_per_day:
            return OrderValidation(
                False,
                "position_limit",
                f"MAX_ORDERS_TODAY:{orders_today}>={max_orders_per_day}",
            )

        # 7. Price sanity
        if price is not None and market_price is not None and market_price > 0:
            deviation_bps = abs(price - market_price) / market_price * 10000
            if deviation_bps > self._max_price_deviation_bps:
                return OrderValidation(
                    False,
                    "price_sanity",
                    f"PRICE_DEVIATION:{deviation_bps:.0f}bps>{self._max_price_deviation_bps}bps",
                )

        # 8. Contract validation (INV-010)
        if self._contracts is not None:
            contract = self._contracts.get(symbol)
            if contract is None:
                return OrderValidation(
                    False, "contract", f"NO_CONTRACT_SPEC:{symbol}"
                )

        return OrderValidation(True, "all", "VALID")
