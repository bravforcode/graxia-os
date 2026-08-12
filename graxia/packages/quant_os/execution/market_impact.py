"""Phase 3 — Square-Root Market Impact Model.

Based on Almgren-Chriss (2001) and empirical consensus across asset classes.
The square-root impact law: impact ∝ η × σ × √(Q/ADV)

This replaces the linear ORDER_SIZE_MULTIPLIER which overestimates small orders
and underestimates large ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class MarketImpactParams:
    """Parameters for the square-root impact model."""

    eta: float = 0.1  # Impact coefficient (empirically ~0.1-0.3 for equities, ~0.05-0.15 for FX)
    gamma: float = 0.314  # Temporary impact coefficient (Almgren default)
    adv: float = 1_000_000  # Average daily volume in lots (default for XAUUSD)


def estimate_market_impact_bps(
    order_lots: float,
    daily_vol_pct: float,
    adv_lots: float = 1_000_000,
    eta: float = 0.1,
) -> float:
    """Estimate market impact in basis points using square-root law.

    Formula: impact_bps = eta * daily_vol_pct * 100 * sqrt(order_lots / adv_lots)

    Args:
        order_lots: Order size in lots
        daily_vol_pct: Daily volatility as percentage (e.g., 1.0 = 1%)
        adv_lots: Average daily volume in lots
        eta: Impact coefficient (empirically calibrated)

    Returns:
        Estimated market impact in basis points

    Example:
        >>> estimate_market_impact_bps(5.0, 1.0, 1_000_000)
        0.005  # ~0.005 bps for 5 lots in 1M ADV market
    """
    if adv_lots <= 0 or order_lots <= 0:
        return 0.0

    participation = order_lots / adv_lots
    impact_bps = eta * daily_vol_pct * 100 * math.sqrt(participation)
    return impact_bps


def estimate_market_impact_usd(
    order_lots: float,
    contract_size: float,
    price: float,
    daily_vol_pct: float,
    adv_lots: float = 1_000_000,
    eta: float = 0.1,
) -> float:
    """Estimate market impact in USD.

    Args:
        order_lots: Order size in lots
        contract_size: Units per lot (e.g., 100 for XAUUSD)
        price: Current price
        daily_vol_pct: Daily volatility as percentage
        adv_lots: Average daily volume in lots
        eta: Impact coefficient

    Returns:
        Estimated market impact in USD
    """
    impact_bps = estimate_market_impact_bps(order_lots, daily_vol_pct, adv_lots, eta)
    notional = order_lots * contract_size * price
    return notional * impact_bps / 10000


def linear_to_sqrt_multiplier(
    linear_mult: float,
    base_lots: float = 1.0,
) -> float:
    """Convert linear size multiplier to equivalent square-root multiplier.

    The old linear model used:
        ORDER_SIZE_MULTIPLIER = {"micro": 0.5, "small": 1.0, "medium": 1.5, "large": 2.5}

    The square-root model gives: sqrt(lots/base) where base=1.0 lot.

    This function maps linear to sqrt for backward compatibility.

    Args:
        linear_mult: Old linear multiplier
        base_lots: Reference lot size (default 1.0)

    Returns:
        Equivalent square-root multiplier
    """
    # Linear: mult = base * lots (normalized to 1.0 at base_lots)
    # Sqrt: mult = sqrt(lots/base_lots)
    # Solve: sqrt(lots/base_lots) = linear_mult
    lots = (linear_mult ** 2) * base_lots
    return math.sqrt(lots / base_lots)
