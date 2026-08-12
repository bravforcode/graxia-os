"""Phase 3 — Continuous Spread Model.

Replaces static session-based spread costs with a continuous time-of-day
model that captures the U-shaped intraday volatility pattern.

Research-backed:
- Spreads widen 1-2 hours before 20:00 GMT (Virtu 2025)
- U-shaped intraday volatility pattern confirmed for FX (Martins & Lopes 2024)
- Opening auctions cost 2-3x midday spreads
- 1σ VIX increase widens FX spreads by 1-3 bps (IMF 2025)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SpreadRegime:
    """Current spread regime parameters."""

    base_spread_bps: float = 1.0  # Baseline spread in bps
    volatility_regime: str = "normal"  # normal, elevated, stressed
    vol_mult: float = 1.0  # Volatility regime multiplier


def continuous_spread_multiplier(hour_utc: float, is_rollover: bool = False) -> float:
    """Calculate continuous spread multiplier based on time of day.

    Models the U-shaped intraday spread pattern:
    - Tightest during London/NY overlap (12-16 UTC)
    - Widest during Asian session and rollover (21-00 UTC)

    Args:
        hour_utc: UTC hour (0-23, fractional allowed)
        is_rollover: True during 21:00-00:00 UTC rollover period

    Returns:
        Spread multiplier (1.0 = baseline, >1.0 = wider)
    """
    # U-shape: minimum at hour 14 (London/NY overlap), maximum at hour 0/24
    # Using cosine: min at 14, max at 0/24
    u_shape = 1.0 + 0.5 * math.cos(math.pi * (hour_utc - 14) / 10)

    # Rollover spike (21:00-00:00 UTC): 3-5x widening
    if is_rollover or (21 <= hour_utc or hour_utc < 1):
        rollover_mult = 3.0 + 2.0 * math.cos(math.pi * (hour_utc - 21.5) / 2.5)
        rollover_mult = max(1.0, min(5.0, rollover_mult))
        u_shape *= rollover_mult

    return max(0.5, min(5.0, u_shape))


def get_volatility_regime_multiplier(vix_level: float = 20.0) -> float:
    """Get spread multiplier based on volatility regime.

    Research (IMF 2025): 1σ VIX increase widens FX spreads by 1-3 bps.
    Nonlinear for >2σ shocks.

    Args:
        vix_level: Current VIX level (20 = normal, 30 = elevated, 40+ = stressed)

    Returns:
        Volatility regime multiplier (1.0 = normal, >1.0 = wider)
    """
    if vix_level <= 20:
        return 1.0  # Normal
    elif vix_level <= 30:
        # Linear increase: 1.0 at VIX=20, 1.5 at VIX=30
        return 1.0 + 0.05 * (vix_level - 20)
    elif vix_level <= 40:
        # Accelerating: 1.5 at VIX=30, 2.5 at VIX=40
        return 1.5 + 0.1 * (vix_level - 30)
    else:
        # Stressed: >2.5x, nonlinear
        return 2.5 + 0.2 * (vix_level - 40)


def continuous_spread_bps(
    base_spread_bps: float,
    hour_utc: float,
    vix_level: float = 20.0,
    is_rollover: bool = False,
) -> float:
    """Calculate continuous spread in bps.

    Combines time-of-day and volatility regime effects.

    Args:
        base_spread_bps: Baseline spread in bps
        hour_utc: UTC hour (0-23)
        vix_level: Current VIX level
        is_rollover: True during rollover period

    Returns:
        Spread in bps
    """
    time_mult = continuous_spread_multiplier(hour_utc, is_rollover)
    vol_mult = get_volatility_regime_multiplier(vix_level)
    return base_spread_bps * time_mult * vol_mult
