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
KELLY_HALF = 0.5  # Use half-Kelly for safety


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


from dataclasses import dataclass

# Regime multipliers ordered by how much of base_kelly to deploy —
# trending markets get full sizing, crisis regimes get near-zero.
_REGIME_MULT = {
    "trending": 1.00,
    "normal": 0.75,
    "ranging": 0.55,
    "volatile": 0.35,
    "crisis": 0.10,
}


@dataclass
class KellyResult:
    fraction: float
    raw_fraction: float
    regime: str
    regime_mult: float
    vol_mult: float
    dd_mult: float


class DynamicKellySizer:
    """
    Position sizer combining Kelly Criterion with regime, volatility-target,
    and drawdown scaling. Stateless per call — safe to share across threads.
    """

    def __init__(
        self,
        base_kelly: float = 0.25,
        vol_target: float = 0.15,
        min_kelly: float = MIN_FRACTION,
        max_kelly: float | None = None,
    ) -> None:
        self.base_kelly = base_kelly
        self.vol_target = vol_target
        self.min_kelly = min_kelly
        self.max_kelly = max_kelly if max_kelly is not None else base_kelly

    def compute_kelly(
        self,
        win_rate: float,
        win_loss_ratio: float,
        avg_loss: float,
        current_vol: float,
        regime: str = "normal",
        drawdown: float = 0.0,
    ) -> KellyResult:
        if win_rate <= 0.0 or win_rate >= 1.0 or avg_loss <= 0.0 or win_loss_ratio <= 0.0:
            return KellyResult(self.min_kelly, 0.0, regime, 0.0, 0.0, 0.0)

        p = win_rate
        q = 1.0 - p
        b = win_loss_ratio
        f_star = (b * p - q) / b

        if f_star <= 0:
            return KellyResult(self.min_kelly, f_star, regime, 0.0, 0.0, 0.0)

        raw = f_star * self.base_kelly

        regime_mult = _REGIME_MULT.get(regime, _REGIME_MULT["normal"])
        vol_mult = min(1.5, self.vol_target / current_vol) if current_vol > 0 else 1.0
        dd_mult = max(0.1, 1.0 - min(drawdown, 1.0) * 2.0)

        fraction = raw * regime_mult * vol_mult * dd_mult
        fraction = max(self.min_kelly, min(self.max_kelly, fraction))

        return KellyResult(round(fraction, 6), raw, regime, regime_mult, vol_mult, dd_mult)
