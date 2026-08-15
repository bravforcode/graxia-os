"""Quality gate for collected accounts. Pure functions, fail-closed."""

from dataclasses import dataclass

from market_data.myfxbook.models import AccountSummary


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    min_tracked_months: int = 12
    max_drawdown_pct: float = 25.0
    min_profit_factor: float = 1.5
    min_total_trades: int = 300


@dataclass(frozen=True, slots=True)
class FilterVerdict:
    passed: bool
    reasons: list[str]


def evaluate_quality(summary: AccountSummary, thresholds: QualityThresholds | None = None) -> FilterVerdict:
    """Fail-closed quality check. Missing metrics are treated as failures."""
    t = thresholds or QualityThresholds()
    reasons: list[str] = []

    if summary.verified is False:
        reasons.append("unverified")
    if summary.tracked_months is None:
        reasons.append(f"insufficient history (unknown, need >= {t.min_tracked_months} months)")
    elif summary.tracked_months < t.min_tracked_months:
        reasons.append(f"insufficient history ({summary.tracked_months} < {t.min_tracked_months} months)")
    if summary.max_drawdown_pct is None:
        reasons.append("drawdown unknown")
    elif summary.max_drawdown_pct > t.max_drawdown_pct:
        reasons.append(f"drawdown too high ({summary.max_drawdown_pct:.1f}% > {t.max_drawdown_pct:.1f}%)")
    if summary.profit_factor is None:
        reasons.append("profit factor unknown")
    elif summary.profit_factor < t.min_profit_factor:
        reasons.append(f"profit factor too low ({summary.profit_factor:.2f} < {t.min_profit_factor:.2f})")
    if summary.total_trades is None:
        reasons.append("too few trades (unknown)")
    elif summary.total_trades < t.min_total_trades:
        reasons.append(f"too few trades ({summary.total_trades} < {t.min_total_trades})")

    return FilterVerdict(passed=not reasons, reasons=reasons)
