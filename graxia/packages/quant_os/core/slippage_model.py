"""
Slippage Model — Realistic slippage estimation based on market conditions.

Factors:
  - Session liquidity (London/NY = low slippage, Asian = high)
  - Volatility (high vol = more slippage)
  - Order size (large orders = more market impact)
  - Time of day (opening/closing = more slippage)

Phase 3: Added Laplace distribution and square-root market impact.

Usage:
  from core.slippage_model import SlippageModel
  sm = SlippageModel()
  slippage = sm.estimate(
      symbol="XAUUSD",
      order_size_lots=0.1,
      volatility=0.15,
      session="london",
  )
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class OrderSize(str, Enum):
    MICRO = "micro"  # < 0.1 lots
    SMALL = "small"  # 0.1 - 0.5 lots
    MEDIUM = "medium"  # 0.5 - 2.0 lots
    LARGE = "large"  # 2.0 - 5.0 lots
    INSTITUTIONAL = "inst"  # > 5.0 lots


# Base slippage in pips per symbol
BASE_SLIPPAGE = {
    "XAUUSD": 0.3,  # Gold: 0.3 pips base
    "EURUSD": 0.1,  # EUR/USD: 0.1 pips base
    "GBPUSD": 0.15,  # GBP/USD: 0.15 pips base
    "USDJPY": 0.15,  # USD/JPY: 0.15 pips base
    "BTCUSD": 5.0,  # Bitcoin: 5.0 pips base
    "US30": 1.0,  # Dow: 1.0 pip base
}

# Session multipliers (how much worse than baseline)
SESSION_MULTIPLIER = {
    "asian": 1.5,  # Low liquidity = more slippage
    "london": 0.8,  # High liquidity = less slippage
    "new_york": 0.9,  # Good liquidity
    "overlap": 0.7,  # Best liquidity = least slippage
    "closed": 3.0,  # No liquidity = max slippage
}

# Phase 3: Square-root order size multipliers (replacing linear)
# Based on Almgren-Chriss empirical law: impact ∝ sqrt(participation)
ORDER_SIZE_MULTIPLIER = {
    OrderSize.MICRO: 0.32,  # sqrt(0.05) ≈ 0.22, adjusted for micro
    OrderSize.SMALL: 0.71,  # sqrt(0.5) ≈ 0.71
    OrderSize.MEDIUM: 1.0,  # sqrt(1.0) = 1.0 (reference)
    OrderSize.LARGE: 1.41,  # sqrt(2.0) ≈ 1.41
    OrderSize.INSTITUTIONAL: 2.24,  # sqrt(5.0) ≈ 2.24
}

# Volatility multiplier (exponential scaling)
VOLATILITY_BASE = 0.15  # Normal volatility


@dataclass(frozen=True)
class SlippageEstimate:
    symbol: str
    base_slippage_pips: float
    session_multiplier: float
    size_multiplier: float
    volatility_multiplier: float
    estimated_slippage_pips: float
    estimated_slippage_price: float  # in price terms
    session: str
    order_size: str
    # Phase 3: Distribution parameters
    laplace_location: float = 0.0  # Location parameter (mu)
    laplace_scale: float = 0.0  # Scale parameter (b)


class SlippageModel:
    """
    Estimate slippage based on market conditions.

    Phase 3: Uses Laplace distribution for fat-tailed slippage modeling.
    Formula:
        slippage = base * session_mult * size_mult * vol_mult
    Distribution: Laplace(mu, b) where b = scale parameter
    """

    def __init__(self, pip_values: dict[str, float] | None = None, seed: int | None = None):
        # Default pip values (price per pip per lot)
        self._pip_values = pip_values or {
            "XAUUSD": 0.01,
            "EURUSD": 0.0001,
            "GBPUSD": 0.0001,
            "USDJPY": 0.01,
            "BTCUSD": 0.01,
            "US30": 0.01,
        }
        self._rng = random.Random(seed)

    def _classify_size(self, lots: float) -> OrderSize:
        if lots < 0.1:
            return OrderSize.MICRO
        elif lots < 0.5:
            return OrderSize.SMALL
        elif lots < 2.0:
            return OrderSize.MEDIUM
        elif lots < 5.0:
            return OrderSize.LARGE
        else:
            return OrderSize.INSTITUTIONAL

    def _volatility_multiplier(self, volatility: float) -> float:
        """Exponential scaling: higher vol = disproportionately more slippage."""
        if volatility <= 0:
            return 1.0
        ratio = volatility / VOLATILITY_BASE
        return 1.0 + (ratio - 1.0) ** 1.5

    def _laplace_sample(self, mu: float, b: float) -> float:
        """Sample from Laplace distribution.

        Laplace(mu, b) has sharper peak and fatter tails than Normal.
        Better captures empirical slippage distribution (Gurovich 2026).
        """
        u = self._rng.random() - 0.5
        # Laplace inverse CDF
        return mu - b * (1 if u < 0 else -1) * math.log(1 - 2 * abs(u))

    def estimate(
        self,
        symbol: str,
        order_size_lots: float,
        volatility: float = 0.15,
        session: str = "london",
        use_distribution: bool = False,
    ) -> SlippageEstimate:
        """Estimate slippage for a given trade.

        Args:
            symbol: Trading symbol
            order_size_lots: Order size in lots
            volatility: Current volatility (0-1)
            session: Trading session
            use_distribution: If True, sample from Laplace distribution
        """
        base = BASE_SLIPPAGE.get(symbol, 0.2)
        session_mult = SESSION_MULTIPLIER.get(session, 1.0)
        size_class = self._classify_size(order_size_lots)
        size_mult = ORDER_SIZE_MULTIPLIER[size_class]
        vol_mult = self._volatility_multiplier(volatility)

        # Point estimate
        estimated = base * session_mult * size_mult * vol_mult
        pip_value = self._pip_values.get(symbol, 0.01)
        estimated_price = estimated * pip_value

        # Phase 3: Laplace distribution parameters
        laplace_location = estimated
        laplace_scale = estimated * 0.3  # Scale ~30% of location (empirical)

        # Sample from distribution if requested
        if use_distribution:
            estimated = self._laplace_sample(laplace_location, laplace_scale)
            estimated = max(0, estimated)  # Slippage can't be negative
            estimated_price = estimated * pip_value

        return SlippageEstimate(
            symbol=symbol,
            base_slippage_pips=base,
            session_multiplier=session_mult,
            size_multiplier=size_mult,
            volatility_multiplier=vol_mult,
            estimated_slippage_pips=round(estimated, 4),
            estimated_slippage_price=round(estimated_price, 6),
            session=session,
            order_size=size_class.value,
            laplace_location=laplace_location,
            laplace_scale=laplace_scale,
        )

    def adjust_sl_tp(
        self,
        entry_price: float,
        sl_pips: float,
        tp_pips: float,
        direction: str,
        symbol: str,
        order_size_lots: float,
        volatility: float = 0.15,
        session: str = "london",
    ) -> dict:
        """Adjust SL/TP to account for estimated slippage."""
        est = self.estimate(symbol, order_size_lots, volatility, session)
        slip = est.estimated_slippage_pips

        if direction == "BUY":
            adjusted_sl = sl_pips + slip  # SL moves against us
            adjusted_tp = tp_pips - slip  # TP reduces
        else:
            adjusted_sl = sl_pips + slip
            adjusted_tp = tp_pips - slip

        return {
            "original_sl_pips": sl_pips,
            "original_tp_pips": tp_pips,
            "slippage_pips": slip,
            "adjusted_sl_pips": round(adjusted_sl, 4),
            "adjusted_tp_pips": round(adjusted_tp, 4),
            "slippage_cost_usd": round(est.estimated_slippage_price * order_size_lots * 100000, 2),
        }
