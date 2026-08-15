"""
Grid Trading Strategy — Self-Contained Implementation

Mechanism:
  - A grid of equidistant price levels is placed between high and low bounds.
  - Buy limit orders are placed at levels below the current price.
  - Sell limit orders are placed at levels above the current price.
  - When a buy fills, a counter sell is placed one grid_step above the fill price.
  - When a sell fills, a counter buy is placed one grid_step below the fill price.
  - Profit per round-trip cycle = grid_step × volume (before fees).
  - Grid deactivates if price breaks out of range by 2× grid_step.

Conservative fill rule:
  - BUY fills  if bar_low  <= order_price  (price traded at or below our bid)
  - SELL fills if bar_high >= order_price (price traded at or above our ask)

This module is completely standalone — no dependency on strategies/base.py,
backtest/engine.py, or any internal quant_os framework.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4

import numpy as np


# =============================================================================
# Enums
# =============================================================================

class OrderSide(str, Enum):
    """Grid order side. Counter variants distinguish orders spawned after a fill."""
    BUY = "BUY"
    SELL = "SELL"
    COUNTER_BUY = "COUNTER_BUY"
    COUNTER_SELL = "COUNTER_SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    COUNTER_PLACED = "COUNTER_PLACED"
    CANCELLED = "CANCELLED"


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class GridConfig:
    """Immutable configuration for a grid trading strategy instance."""

    symbol: str = ""
    grid_step: float = 0.0           # price distance between levels (auto from bounds if 0)
    grid_count: int = 20              # total grid levels (produces grid_count + 1 price points)
    order_volume: float = 0.01        # volume per level / per order
    high_price: float = 0.0           # upper bound (auto via range detection if 0)
    low_price: float = 0.0            # lower bound (auto via range detection if 0)
    range_method: str = "atr"         # "atr" | "fixed"
    atr_period: int = 20
    atr_multiplier: float = 2.0
    max_open_orders_per_side: int = 10
    max_grid_exposure: float = 0.5    # max fraction of capital allocated to the grid


@dataclass
class GridOrder:
    """A single order within the grid — can be initial or counter."""

    id: str = field(default_factory=lambda: str(uuid4()))
    price: float = 0.0
    side: OrderSide = OrderSide.BUY
    volume: float = 0.01
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float = 0.0
    fill_bar: int = -1
    counter_order_id: str = ""
    is_counter: bool = False


@dataclass
class GridState:
    """Persistent state for a running grid instance."""

    grid_id: str = field(default_factory=lambda: str(uuid4()))
    levels: list[float] = field(default_factory=list)
    active_orders: list[GridOrder] = field(default_factory=list)
    filled_orders: list[GridOrder] = field(default_factory=list)
    total_pnl: float = 0.0
    total_fills: int = 0
    is_active: bool = False
    high_price: float = 0.0
    low_price: float = 0.0
    current_bar: int = 0


# =============================================================================
# RangeDetector
# =============================================================================

class RangeDetector:
    """Detects price range bounds for grid deployment.

    Two modes:
      - **fixed**:  use config.high_price / config.low_price directly.
      - **atr**:    compute ATR from OHLCV data and set bounds as
                    current_price ± (ATR × atr_multiplier).
    """

    @staticmethod
    def detect_range(
        current_price: float,
        ohlcv_data: dict[str, list[float]],
        config: GridConfig,
    ) -> tuple[float, float]:
        """Return (high, low) grid bounds."""
        if config.range_method == "fixed" or (
            config.high_price > 0 and config.low_price > 0
        ):
            if config.high_price > 0 and config.low_price > 0:
                return (config.high_price, config.low_price)
        return RangeDetector._atr_range(current_price, ohlcv_data, config)

    @staticmethod
    def _atr_range(
        current_price: float,
        ohlcv_data: dict[str, list[float]],
        config: GridConfig,
    ) -> tuple[float, float]:
        high = np.asarray(ohlcv_data.get("high", []), dtype=np.float64)
        low = np.asarray(ohlcv_data.get("low", []), dtype=np.float64)
        close = np.asarray(ohlcv_data.get("close", []), dtype=np.float64)

        if len(close) < max(config.atr_period, 2):
            fallback = current_price * 0.02 * config.atr_multiplier
            return (current_price + fallback, current_price - fallback)

        atr_val = RangeDetector._compute_atr(high, low, close, config.atr_period)
        spread = atr_val * config.atr_multiplier
        return (current_price + spread, current_price - spread)

    @staticmethod
    def _compute_atr(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int,
    ) -> float:
        """Wilder's smoothed Average True Range."""
        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]

        tr1 = high - low
        tr2 = np.abs(high - prev_close)
        tr3 = np.abs(low - prev_close)
        true_range = np.maximum.reduce([tr1, tr2, tr3])

        atr = np.empty_like(true_range)
        atr[period - 1] = float(np.mean(true_range[:period]))
        for i in range(period, len(true_range)):
            atr[i] = (atr[i - 1] * (period - 1) + true_range[i]) / period

        return float(atr[-1])


# =============================================================================
# GridOrderManager
# =============================================================================

class GridOrderManager:
    """Handles the full lifecycle of grid orders."""

    def __init__(self, config: GridConfig):
        self.config = config

    # ------------------------------------------------------------------
    # Level construction
    # ------------------------------------------------------------------

    def build_grid_levels(
        self,
        high: float,
        low: float,
        grid_count: int,
        grid_step: float = 0.0,
    ) -> list[float]:
        """Generate equidistant price levels from low to high (inclusive)."""
        step = grid_step if grid_step > 0 else (high - low) / grid_count
        return [low + i * step for i in range(grid_count + 1)]

    # ------------------------------------------------------------------
    # Initial placement
    # ------------------------------------------------------------------

    def place_initial_orders(
        self,
        state: GridState,
        current_price: float,
    ) -> list[GridOrder]:
        """Place buy orders below current_price, sell orders above.

        Caps each side at max_open_orders_per_side.  Stores orders on state.
        """
        new_orders: list[GridOrder] = []
        buy_count = 0
        sell_count = 0
        limit = self.config.max_open_orders_per_side

        for level in state.levels:
            if buy_count >= limit and sell_count >= limit:
                break

            if level < current_price and buy_count < limit:
                new_orders.append(
                    GridOrder(price=level, side=OrderSide.BUY, volume=self.config.order_volume)
                )
                buy_count += 1
            elif level > current_price and sell_count < limit:
                new_orders.append(
                    GridOrder(price=level, side=OrderSide.SELL, volume=self.config.order_volume)
                )
                sell_count += 1

        state.active_orders = new_orders
        return new_orders

    # ------------------------------------------------------------------
    # Bar-based fill evaluation
    # ------------------------------------------------------------------

    def evaluate_bar(
        self,
        state: GridState,
        bar_high: float,
        bar_low: float,
        bar_index: int,
    ) -> list[GridOrder]:
        """Return all pending orders that filled within this bar's range.

        Conservative rule:
          - BUY  fills when bar_low  <= order_price
          - SELL fills when bar_high >= order_price
        """
        filled: list[GridOrder] = []

        for order in state.active_orders:
            if order.status != OrderStatus.PENDING:
                continue

            if order.side in (OrderSide.BUY, OrderSide.COUNTER_BUY):
                if bar_low <= order.price:
                    self._mark_filled(order, order.price, bar_index)
                    filled.append(order)

            elif order.side in (OrderSide.SELL, OrderSide.COUNTER_SELL):
                if bar_high >= order.price:
                    self._mark_filled(order, order.price, bar_index)
                    filled.append(order)

        return filled

    # ------------------------------------------------------------------
    # Counter-order placement
    # ------------------------------------------------------------------

    def place_counter_order(
        self,
        state: GridState,
        filled_order: GridOrder,
    ) -> Optional[GridOrder]:
        """After a fill, place the opposite order one grid_step away.

        BUY  filled → place COUNTER_SELL at fill_price + grid_step.
        SELL filled → place COUNTER_BUY  at fill_price - grid_step.

        Returns None if the counter price falls outside the grid bounds.
        """
        step = self._grid_step(state)
        if step <= 0:
            return None

        is_buy = filled_order.side in (OrderSide.BUY, OrderSide.COUNTER_BUY)

        if is_buy:
            counter_price = filled_order.fill_price + step
            counter_side = OrderSide.COUNTER_SELL
        else:
            counter_price = filled_order.fill_price - step
            counter_side = OrderSide.COUNTER_BUY

        if counter_price > state.high_price or counter_price < state.low_price:
            return None

        counter = GridOrder(
            price=counter_price,
            side=counter_side,
            volume=self.config.order_volume,
            is_counter=True,
        )
        filled_order.counter_order_id = counter.id
        filled_order.status = OrderStatus.COUNTER_PLACED

        state.total_pnl += step * self.config.order_volume
        state.total_fills += 1
        state.active_orders.append(counter)

        return counter

    # ------------------------------------------------------------------
    # Breakout detection
    # ------------------------------------------------------------------

    def is_breakout(self, state: GridState, current_price: float) -> bool:
        """True when price has breached the grid range by 2× grid_step."""
        step = self._grid_step(state)
        if step <= 0:
            return False
        return (
            current_price > state.high_price + 2 * step
            or current_price < state.low_price - 2 * step
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _grid_step(self, state: GridState) -> float:
        if self.config.grid_step > 0:
            return self.config.grid_step
        if len(state.levels) >= 2:
            return state.levels[1] - state.levels[0]
        return 0.0

    @staticmethod
    def _mark_filled(order: GridOrder, fill_price: float, bar_index: int) -> None:
        order.status = OrderStatus.FILLED
        order.fill_price = fill_price
        order.fill_bar = bar_index


# =============================================================================
# GridStrategy — top-level entry point
# =============================================================================

class GridStrategy:
    """Minimal, self-contained grid trading strategy.

    Usage::

        config = GridConfig(symbol="EURUSD", grid_count=20, order_volume=0.01)
        strategy = GridStrategy(config)
        state = strategy.initialize_grid(bar_index=0, current_price=1.0850, ohlcv_data=...)

        for i, bar in enumerate(bars):
            fills, counters = strategy.on_bar(i, bar["high"], bar["low"], bar["close"])
            # fills:    list[GridOrder] that were matched this bar
            # counters: list[GridOrder] newly placed after fills
    """

    def __init__(self, config: GridConfig) -> None:
        self.config = config
        self.detector = RangeDetector()
        self.manager = GridOrderManager(config)
        self._state: Optional[GridState] = None

    @property
    def state(self) -> Optional[GridState]:
        """Current grid state (None before initialize_grid is called)."""
        return self._state

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize_grid(
        self,
        bar_index: int,
        current_price: float,
        ohlcv_data: dict[str, list[float]],
    ) -> GridState:
        """Detect range, build levels, place initial orders.  Returns state."""
        high, low = self.detector.detect_range(current_price, ohlcv_data, self.config)

        levels = self.manager.build_grid_levels(
            high=high,
            low=low,
            grid_count=self.config.grid_count,
            grid_step=self.config.grid_step,
        )

        state = GridState(
            high_price=high,
            low_price=low,
            levels=levels,
            current_bar=bar_index,
            is_active=True,
        )

        self.manager.place_initial_orders(state, current_price)
        self._state = state
        return state

    # ------------------------------------------------------------------
    # Per-bar processing
    # ------------------------------------------------------------------

    def on_bar(
        self,
        bar_index: int,
        bar_high: float,
        bar_low: float,
        bar_close: float,
    ) -> tuple[list[GridOrder], list[GridOrder]]:
        """Process one bar: evaluate fills → place counters → check breakout.

        Returns ``(filled_orders, new_counter_orders)``.
        """
        if self._state is None or not self._state.is_active:
            return ([], [])

        state = self._state
        state.current_bar = bar_index

        fills = self.manager.evaluate_bar(state, bar_high, bar_low, bar_index)

        counters: list[GridOrder] = []
        for filled in fills:
            counter = self.manager.place_counter_order(state, filled)
            if counter is not None:
                counters.append(counter)
            state.filled_orders.append(filled)

        if self.manager.is_breakout(state, bar_close):
            state.is_active = False

        return (fills, counters)

    # ------------------------------------------------------------------
    # Range recalculation
    # ------------------------------------------------------------------

    def recalc_range(
        self,
        bar_index: int,
        current_price: float,
        ohlcv_data: dict[str, list[float]],
    ) -> GridState:
        """Re-detect range and fully reinitialize (e.g. after breakout)."""
        return self.initialize_grid(bar_index, current_price, ohlcv_data)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return a summary dictionary of the current grid state."""
        if self._state is None:
            return {"active": False, "total_pnl": 0.0, "total_fills": 0}
        s = self._state
        return {
            "grid_id": s.grid_id,
            "active": s.is_active,
            "total_pnl": s.total_pnl,
            "total_fills": s.total_fills,
            "pending_orders": sum(
                1 for o in s.active_orders if o.status == OrderStatus.PENDING
            ),
            "high_price": s.high_price,
            "low_price": s.low_price,
            "current_bar": s.current_bar,
        }
