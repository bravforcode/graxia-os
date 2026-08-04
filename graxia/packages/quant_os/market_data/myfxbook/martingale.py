"""Martingale / blow-up risk detection for Myfxbook equity curves and trades.

Signals:
- Tail drawdown: recent peak-to-trough drop >= TAIL_DRAWDOWN_THRESHOLD.
- Parabolic blow-up: equity fits y = a*z^2 + b*z + c (z centered) with a > 0
  and high R^2 -- accelerating growth typical of size-doubling strategies.
- Lot doubling: consecutive trades on the same symbol doubling in lots.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .models import EquityPoint, TradeRecord

if TYPE_CHECKING:
    pass

TAIL_DRAWDOWN_THRESHOLD: float = 25.0
MIN_POINTS_FOR_TAIL: int = 6
MIN_POINTS_FOR_PARABOLA: int = 12
MIN_R2_FOR_PARABOLA: float = 0.9
DOUBLING_TOLERANCE: float = 0.05


@dataclass(frozen=True)
class MartingaleVerdict:
    """Result of the martingale detector for one account."""

    risky: bool
    signals: tuple[str, ...]


def _tail_drawdown(values: Sequence[float]) -> str | None:
    """Return a reason string if the recent tail drops >= threshold."""
    if len(values) < MIN_POINTS_FOR_TAIL:
        return None
    tail = values[-MIN_POINTS_FOR_TAIL:]
    peak = max(tail)
    if peak <= 0:
        return None
    drop_pct = (peak - min(tail)) / peak * 100.0
    if drop_pct >= TAIL_DRAWDOWN_THRESHOLD:
        return f"tail drawdown {drop_pct:.1f}% >= " f"{TAIL_DRAWDOWN_THRESHOLD:.0f}%"
    return None


def _quadratic_fit(
    values: Sequence[float],
) -> tuple[float, float, float, float] | None:
    """OLS fit of y = a*z^2 + b*z + c with z = x - mean(x).

    Returns (a, b, c, r2) or None when the series is too short or contains
    non-positive equity. z is centered so the linear term decouples:
    b = sum(z*y) / sum(z^2); a and c follow from the 2x2 normal equations.
    """
    n = len(values)
    if n < MIN_POINTS_FOR_PARABOLA or any(v <= 0 for v in values):
        return None
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(values) / n
    z = [xi - x_mean for xi in x]
    z2 = [zi * zi for zi in z]

    s_zz = sum(z2)
    s_zy = sum(zi * yi for zi, yi in zip(z, values, strict=False))
    b = s_zy / s_zz

    w = [yi - b * zi for yi, zi in zip(values, z, strict=False)]
    s_z2z2 = sum(vi * vi for vi in z2)
    s_z2w = sum(z2i * wi for z2i, wi in zip(z2, w, strict=False))
    s_w = sum(w)
    det = s_z2z2 * n - s_zz * s_zz
    if det == 0:
        return None
    a = (n * s_z2w - s_zz * s_w) / det
    c = (s_z2z2 * s_w - s_zz * s_z2w) / det

    ss_res = sum((yi - (a * zi * zi + b * zi + c)) ** 2 for yi, zi in zip(values, z, strict=False))
    ss_tot = sum((yi - y_mean) ** 2 for yi in values)
    if ss_tot == 0:
        r2 = 1.0
    else:
        r2 = 1.0 - ss_res / ss_tot
    return a, b, c, r2


def detect_martingale(equity_points: Sequence[EquityPoint]) -> MartingaleVerdict:
    """Evaluate an account's monthly equity curve for martingale behavior."""
    values = [p.equity for p in equity_points]
    if not values:
        return MartingaleVerdict(risky=False, signals=("insufficient equity data",))

    signals: list[str] = []
    tail = _tail_drawdown(values)
    if tail is not None:
        signals.append(tail)

    fit = _quadratic_fit(values)
    if fit is not None:
        a, _b, _c, r2 = fit
        if a > 0 and r2 >= MIN_R2_FOR_PARABOLA:
            signals.append(f"parabolic equity growth (a={a:.3f}, r2={r2:.2f})")

    return MartingaleVerdict(risky=bool(signals), signals=tuple(signals))


def lot_doubling_signals(trades: Sequence[TradeRecord]) -> list[str]:
    """Flag consecutive same-symbol trades where lots approximately double."""
    signals: list[str] = []
    ordered = sorted(trades, key=lambda t: (t.open_time, t.trade_id))
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        if prev.symbol != nxt.symbol or prev.lots <= 0:
            continue
        ratio = nxt.lots / prev.lots
        if abs(ratio - 2.0) <= DOUBLING_TOLERANCE:
            signals.append(f"lot doubling {prev.symbol}: {prev.lots} -> {nxt.lots}")
    return signals
