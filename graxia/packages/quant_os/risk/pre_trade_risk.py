"""Pre-trade risk engine - final gate before order submission."""

from dataclasses import dataclass, field
from decimal import Decimal

from .circuit_breaker import CircuitBreaker
from .kill_switch import KillSwitch
from .position_sizer_v2 import SizingResult
from .risk_ledger import RiskLedger
from .risk_policy import RiskPolicy


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
    kill_switch: KillSwitch = None,
    circuit_breaker: CircuitBreaker = None,
    asset_class: str = "",
    margin_level_pct: Decimal | None = None,
) -> RiskCheckResult:
    """
    Final risk gate before order submission.
    Checks: kill switch, circuit breaker, daily/weekly/drawdown limits, position count, order rate, margin.
    """
    reasons = []
    risk_budget = account_equity * risk_policy.risk_per_trade_fraction
    daily_loss = Decimal(str(risk_ledger.daily_realized_loss))
    weekly_loss = Decimal(str(risk_ledger.weekly_realized_loss))
    total_drawdown = Decimal(str(risk_ledger.total_drawdown))

    # Kill switch check
    if kill_switch and kill_switch.is_active():
        reasons.append("Kill switch is active")

    # Circuit breaker check
    if circuit_breaker and asset_class:
        if circuit_breaker.is_open(asset_class):
            reasons.append(f"Circuit breaker open for {asset_class}: {circuit_breaker.reason}")

    # Rejected by sizer
    if sizing_result.rejected:
        reasons.extend(sizing_result.rejection_reasons)

    # Daily loss limit
    max_daily = account_equity * risk_policy.max_daily_loss_fraction
    if daily_loss >= max_daily:
        reasons.append(f"Daily loss limit reached: {daily_loss:.2f} >= {max_daily:.2f}")

    # Weekly loss limit
    max_weekly = account_equity * risk_policy.max_weekly_loss_fraction
    if weekly_loss >= max_weekly:
        reasons.append(f"Weekly loss limit reached: {weekly_loss:.2f} >= {max_weekly:.2f}")

    # Drawdown limit
    max_dd = account_equity * risk_policy.max_total_drawdown_fraction
    if total_drawdown >= max_dd:
        reasons.append(f"Drawdown limit reached: {total_drawdown:.2f} >= {max_dd:.2f}")

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
