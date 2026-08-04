"""Heuristic martingale / blow-up detection from equity curves and trade lots.

Deliberately simple: tail crash, full-quadratic parabolic fit, lot doubling.
This is a research screen, not a risk-policy gate — live risk never consults it.
"""

from dataclasses import dataclass

from market_data.myfxbook.models import EquityPoint, TradeRecord

TAIL_WINDOW_RATIO = 0.2
TAIL_DRAWDOWN_THRESHOLD = 30.0
PARABOLIC_R2_THRESHOLD = 0.95
LOT_DOUBLING_RATIO = 1.8
MIN_POINTS_FOR_PARABOLA = 12


@dataclass(frozen=True, slots=True)
class MartingaleVerdict:
    risky: bool
    signals: list[str]


def tail_drawdown_risk(equity_points: list[EquityPoint]) -> list[str]:
    if not equity_points:
        return []
    values = [p.equity for p in equity_points]
    n_tail = max(1, int(len(values) * TAIL_WINDOW_RATIO))
    tail = values[-n_tail:]
    peak = max(values[:-n_tail]) if len(values) > n_tail else max(values)
    if peak <= 0:
        return []
    drop_pct = (peak - min(tail)) / peak * 100.0
    if drop_pct >= TAIL_DRAWDOWN_THRESHOLD:
        return [f"tail drawdown {drop_pct:.1f}% >= {TAIL_DRAWDOWN_THRESHOLD:.0f}%"]
    return []


def _quadratic_fit(values: list[float]) -> tuple[float, float, float, float] | None:
    """OLS fit y = a*z^2 + b*z + c with z = x - mean(x). Returns (a, b, c, r2) or None.

    The linear term b*z is REQUIRED: fitting z^2 alone to an x^2-shaped blow-up
    curve yields R2 ~ 0.07 (the linear component dominates the variance), so the
    detector would miss real martingale curves. For equally spaced indices
    sum(z) = 0 and sum(z^3) = 0, so b decouples: b = sum(z*y) / sum(z^2).
    """
    if len(values) < MIN_POINTS_FOR_PARABOLA or any(v <= 0 for v in values):
        return None
    n = len(values)
    xs = [float(i) for i in range(n)]
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    zs = [x - x_mean for x in xs]
    z2 = [z * z for z in zs]
    sum_z2 = sum(z2)
    sum_z4 = sum(z * z * z * z for z in zs)
    b = sum(z * y for z, y in zip(zs, values, strict=False)) / sum_z2 if sum_z2 > 0 else 0.0
    y_prime = [y - b * z for y, z in zip(values, zs, strict=False)]
    sum_yp = sum(y_prime)
    sum_z2yp = sum(z_sq * yp for z_sq, yp in zip(z2, y_prime, strict=False))
    denom = n * sum_z4 - sum_z2 * sum_z2
    if abs(denom) < 1e-12:
        return None
    a = (n * sum_z2yp - sum_z2 * sum_yp) / denom
    c = (sum_yp - a * sum_z2) / n
    fitted = [a * z_sq + b * z + c for z_sq, z in zip(z2, zs, strict=False)]
    ss_res = sum((y - fy) ** 2 for y, fy in zip(values, fitted, strict=False))
    ss_tot = sum((y - y_mean) ** 2 for y in values)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return a, b, c, r2


def parabolic_growth_risk(equity_points: list[EquityPoint]) -> list[str]:
    values = [p.equity for p in equity_points]
    # Fit on the PRE-TAIL portion only: the crash itself would drag R2 down
    # even for a perfect parabola (the crashed tail is not parabolic).
    n_tail = max(1, int(len(values) * TAIL_WINDOW_RATIO)) if values else 0
    head = values[:-n_tail] if len(values) > n_tail else values
    fit = _quadratic_fit(head)
    if fit is None or fit[0] <= 0:  # a <= 0 = no upward curvature
        return []
    a, _b, _c, r2 = fit
    if r2 > PARABOLIC_R2_THRESHOLD and tail_drawdown_risk(equity_points):
        return [f"parabolic equity growth (R2={r2:.2f})"]
    return []


def lot_doubling_signals(trades: list[TradeRecord]) -> list[str]:
    signals: list[str] = []
    for i in range(len(trades) - 1):
        prev, curr = trades[i], trades[i + 1]
        if prev.symbol != curr.symbol or prev.lots <= 0:
            continue
        ratio = curr.lots / prev.lots
        if ratio >= LOT_DOUBLING_RATIO:
            signals.append(f"lot doubling {curr.symbol} {prev.lots:.2f} -> {curr.lots:.2f}")
    return signals


def detect_martingale(equity_points: list[EquityPoint], trades: list[TradeRecord] | None = None) -> MartingaleVerdict:
    if not equity_points:
        return MartingaleVerdict(risky=False, signals=["insufficient equity data"])
    signals: list[str] = []
    signals.extend(tail_drawdown_risk(equity_points))
    signals.extend(parabolic_growth_risk(equity_points))
    if trades:
        signals.extend(lot_doubling_signals(trades))
    return MartingaleVerdict(risky=bool(signals), signals=signals)
