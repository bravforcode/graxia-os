"""Pre-trade risk engine - final gate before order submission."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .circuit_breaker import CircuitBreaker
from .kill_switch import KillSwitch
from .position_sizer_v2 import SizingResult
from .risk_ledger import RiskLedger
from .risk_policy import RiskPolicy

_UNSET_STOP_LOSS = object()


@dataclass
class RiskCheckResult:
    approved: bool
    reasons: list[str] = field(default_factory=list)  # Empty if approved
    risk_budget: Decimal = Decimal("0")
    daily_loss: Decimal = Decimal("0")
    weekly_loss: Decimal = Decimal("0")
    total_drawdown: Decimal = Decimal("0")
    orders_today: int = 0
    open_positions: int = 0


def pre_trade_check(
    sizing_result: SizingResult,
    risk_policy: RiskPolicy,
    risk_ledger: RiskLedger,
    account_equity: Decimal,
    kill_switch: KillSwitch,
    circuit_breaker: CircuitBreaker = None,
    asset_class: str = "",
    margin_level_pct: Decimal | None = None,
    signal_stop_loss: Any = _UNSET_STOP_LOSS,
) -> RiskCheckResult:
    """
    Final risk gate before order submission.
    Checks: kill switch, circuit breaker, daily/weekly/drawdown limits, position count, order rate, margin, stop-loss.

    Fail-closed: kill_switch is required. If None, all orders are rejected.
    """
    reasons = []

    # Fail-closed: kill_switch is required
    if kill_switch is None:
        return RiskCheckResult(
            approved=False,
            reasons=["kill_switch is required but not provided (fail-closed)"],
            risk_budget=Decimal("0"),
            daily_loss=Decimal("0"),
            weekly_loss=Decimal("0"),
            total_drawdown=Decimal("0"),
            orders_today=0,
            open_positions=0,
        )

    risk_budget = account_equity * risk_policy.risk_per_trade_fraction
    daily_loss = Decimal(str(risk_ledger.daily_realized_loss))
    weekly_loss = Decimal(str(risk_ledger.weekly_realized_loss))
    total_drawdown = Decimal(str(risk_ledger.total_drawdown))

    # Kill switch check
    if kill_switch.is_active():
        reasons.append("Kill switch is active")

    # Circuit breaker check
    if circuit_breaker and asset_class:
        if circuit_breaker.is_open(asset_class):
            reasons.append(f"Circuit breaker open for {asset_class}: {circuit_breaker.reason}")

    # Stop-loss requirement (only checked when signal stop-loss is explicitly provided)
    if (
        signal_stop_loss is not _UNSET_STOP_LOSS
        and risk_policy.require_stop_loss
        and (signal_stop_loss is None or signal_stop_loss <= 0)
    ):
        reasons.append("Stop-loss required but not provided")

    # Rejected by sizer
    if sizing_result.rejected:
        reasons.extend(sizing_result.rejection_reasons)

    # Daily loss limit — daily_loss is a dollar amount; compare as fraction of equity
    if account_equity > 0:
        daily_loss_frac = daily_loss / account_equity
        if daily_loss_frac >= risk_policy.max_daily_loss_fraction:
            reasons.append(f"Daily loss limit reached: {daily_loss_frac:.4f} >= {risk_policy.max_daily_loss_fraction}")

    # Weekly loss limit — weekly_loss is a dollar amount; compare as fraction of equity
    if account_equity > 0:
        weekly_loss_frac = weekly_loss / account_equity
        if weekly_loss_frac >= risk_policy.max_weekly_loss_fraction:
            reasons.append(
                f"Weekly loss limit reached: {weekly_loss_frac:.4f} >= {risk_policy.max_weekly_loss_fraction}"
            )

    # Drawdown limit — total_drawdown is already a fraction (peak-equity)/peak
    if total_drawdown >= risk_policy.max_total_drawdown_fraction:
        reasons.append(f"Drawdown limit reached: {total_drawdown:.4f} >= {risk_policy.max_total_drawdown_fraction}")

    # Position count
    if risk_ledger.open_positions >= risk_policy.max_positions:
        reasons.append(f"Max positions reached: {risk_ledger.open_positions} >= {risk_policy.max_positions}")

    # Order rate
    if risk_ledger.orders_today >= risk_policy.max_orders_per_day:
        reasons.append(f"Max orders/day reached: {risk_ledger.orders_today} >= {risk_policy.max_orders_per_day}")

    # Margin level check
    if margin_level_pct is not None and margin_level_pct > 0:
        if margin_level_pct < risk_policy.min_margin_level_pct:
            reasons.append(f"Margin level too low: {margin_level_pct:.0f}% < {risk_policy.min_margin_level_pct:.0f}%")

    return RiskCheckResult(
        approved=len(reasons) == 0,
        reasons=reasons,
        risk_budget=risk_budget,
        daily_loss=daily_loss,
        weekly_loss=weekly_loss,
        total_drawdown=total_drawdown,
        orders_today=risk_ledger.orders_today,
        open_positions=risk_ledger.open_positions,
    )
