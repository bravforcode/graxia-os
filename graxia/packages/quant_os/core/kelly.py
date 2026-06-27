"""
Kelly Criterion — Dynamic position sizing based on historical win rate.

Formula: f* = (bp - q) / b
  f* = optimal fraction of capital to risk
  b  = reward/risk ratio (TP/SL)
  p  = win probability
  q  = 1 - p (loss probability)

Clamped to [0.01, 0.05] for safety (never risk more than 5% per trade).

Usage:
  from core.kelly import kelly_fraction, kelly_size
  frac = kelly_fraction(win_rate=0.59, avg_rr=1.88)
  size = kelly_size(capital=10000, win_rate=0.59, avg_rr=1.88, sl_pips=100)
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Hard limits (never exceed these regardless of Kelly output)
MAX_FRACTION = 0.05  # 5% max risk per trade
MIN_FRACTION = 0.01  # 1% min risk per trade
KELLY_HALF = 0.5     # Use half-Kelly for safety


def kelly_fraction(
    win_rate: float,
    avg_rr: float,
    use_half: bool = True,
) -> float:
    """
    Calculate optimal risk fraction using Kelly Criterion.

    Args:
        win_rate: Historical win probability (0.0 - 1.0)
        avg_rr: Average reward/risk ratio (e.g., 1.88 means $1.88 reward per $1 risk)
        use_half: Use half-Kelly (recommended for safety)

    Returns:
        Fraction of capital to risk (clamped to [MIN_FRACTION, MAX_FRACTION])
    """
    if win_rate <= 0 or win_rate >= 1:
        logger.warning("kelly.invalid_win_rate", win_rate=win_rate)
        return MIN_FRACTION

    if avg_rr <= 0:
        logger.warning("kelly.invalid_rr", avg_rr=avg_rr)
        return MIN_FRACTION

    p = win_rate
    q = 1.0 - p
    b = avg_rr

    # Kelly formula: f* = (bp - q) / b
    f_star = (b * p - q) / b

    if f_star <= 0:
        # Negative Kelly = edge is against us
        logger.info("kelly.negative_edge", f_star=f_star, win_rate=win_rate, avg_rr=avg_rr)
        return MIN_FRACTION

    if use_half:
        f_star *= KELLY_HALF

    # Clamp
    f_star = max(MIN_FRACTION, min(MAX_FRACTION, f_star))

    return round(f_star, 4)


def kelly_size(
    capital: float,
    win_rate: float,
    avg_rr: float,
    sl_pips: float,
    pip_value: float = 0.01,
    use_half: bool = True,
) -> dict:
    """
    Calculate position size using Kelly Criterion.

    Args:
        capital: Current account capital
        win_rate: Historical win rate
        avg_rr: Average reward/risk ratio
        sl_pips: Stop loss in pips
        pip_value: Dollar value per pip per standard lot (default $0.01 for micro)
        use_half: Use half-Kelly

    Returns:
        Dict with kelly_fraction, risk_dollars, lots, confidence
    """
    frac = kelly_fraction(win_rate, avg_rr, use_half)
    risk_dollars = capital * frac

    # Convert to lots
    risk_per_pip = risk_dollars / sl_pips if sl_pips > 0 else 0
    lots = risk_per_pip / pip_value if pip_value > 0 else 0

    return {
        "kelly_fraction": frac,
        "risk_dollars": round(risk_dollars, 2),
        "lots": round(lots, 2),
        "capital": capital,
        "win_rate": win_rate,
        "avg_rr": avg_rr,
        "sl_pips": sl_pips,
    }


def kelly_adjust_for_regime(
    base_fraction: float,
    regime_label: str,
) -> float:
    """Adjust Kelly fraction based on macro regime."""
    regime_mult = {
        "NORMAL": 1.0,
        "HIGH_UNCERTAINTY": 0.5,
        "CRISIS": 0.0,
    }
    mult = regime_mult.get(regime_label, 0.5)
    adjusted = base_fraction * mult
    return max(MIN_FRACTION, min(MAX_FRACTION, adjusted))
