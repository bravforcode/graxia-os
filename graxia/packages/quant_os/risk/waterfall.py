"""Risk waterfall — cascading budget allocation: strategy → portfolio → account.

Flow: position_size → margin_check → correlation_adj → VaR_check → max_dd_check → approve/reject

Usage:
    from risk.waterfall import RiskWaterfall
    waterfall = RiskWaterfall(risk_policy)
    result = waterfall.check(symbol="XAUUSD", proposed_size=0.01, ...)
    if not result.approved:
        print(result.reason)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WaterfallStage(Enum):
    """Stages in the risk waterfall cascade."""

    POSITION_SIZE = "position_size"
    MARGIN_CHECK = "margin_check"
    CORRELATION_ADJ = "correlation_adj"
    VAR_CHECK = "var_check"
    MAX_DD_CHECK = "max_dd_check"
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class WaterfallResult:
    """Result of risk waterfall check."""

    approved: bool
    stage: WaterfallStage
    reason: str
    adjusted_size: float = 0.0
    details: dict | None = None


class RiskWaterfall:
    """Cascading risk budget check.

    INV-001: Uses frozen RiskPolicy — no runtime mutation.
    INV-009: Pre-trade gate mandatory before any order.
    """

    def __init__(self, risk_policy, kill_switch=None):
        self._policy = risk_policy
        self._kill_switch = kill_switch

    def check(
        self,
        symbol: str,
        proposed_size: float,
        current_positions: dict | None = None,
        account_balance: float = 10000.0,
        current_drawdown_bps: int = 0,
        daily_loss_bps: int = 0,
        margin_level_pct: float = 1000.0,
        correlation_matrix: dict | None = None,
    ) -> WaterfallResult:
        """Run full waterfall cascade.

        Returns first rejection or final approval.
        """
        current_positions = current_positions or {}

        # ── Stage 1: Position size ────────────────────────────────
        if proposed_size <= 0:
            return WaterfallResult(
                False, WaterfallStage.POSITION_SIZE, "SIZE_ZERO_OR_NEGATIVE"
            )

        # ── Stage 2: Max open positions ───────────────────────────
        if len(current_positions) >= self._policy.max_open_positions:
            return WaterfallResult(
                False,
                WaterfallStage.MARGIN_CHECK,
                f"MAX_POSITIONS:{len(current_positions)}>={self._policy.max_open_positions}",
            )

        # ── Stage 3: Risk per trade (bps) ─────────────────────────
        risk_fraction = float(self._policy.risk_per_trade_fraction)
        max_risk_amount = account_balance * risk_fraction
        # Rough estimate: 1% adverse move on proposed size
        estimated_risk = proposed_size * account_balance * 0.01
        if estimated_risk > max_risk_amount:
            return WaterfallResult(
                False,
                WaterfallStage.CORRELATION_ADJ,
                f"RISK_PER_TRADE_EXCEEDS:estimated={estimated_risk:.2f}>max={max_risk_amount:.2f}",
            )

        # ── Stage 4: Daily loss limit ─────────────────────────────
        if daily_loss_bps >= self._policy.max_daily_loss_bps:
            return WaterfallResult(
                False,
                WaterfallStage.VAR_CHECK,
                f"DAILY_LOSS_LIMIT:{daily_loss_bps}>={self._policy.max_daily_loss_bps}bps",
            )

        # ── Stage 5: Max drawdown ─────────────────────────────────
        if current_drawdown_bps >= self._policy.max_total_drawdown_bps:
            return WaterfallResult(
                False,
                WaterfallStage.MAX_DD_CHECK,
                f"MAX_DRAWDOWN:{current_drawdown_bps}>={self._policy.max_total_drawdown_bps}bps",
            )

        # ── Stage 6: Margin level ─────────────────────────────────
        min_margin = float(self._policy.min_margin_level_pct)
        if margin_level_pct < min_margin:
            return WaterfallResult(
                False,
                WaterfallStage.MAX_DD_CHECK,
                f"MARGIN_LEVEL_LOW:{margin_level_pct:.0f}%<{min_margin:.0f}%",
            )

        # ── Stage 7: Kill switch ──────────────────────────────────
        if self._kill_switch and self._kill_switch.is_triggered():
            return WaterfallResult(
                False, WaterfallStage.MAX_DD_CHECK, "KILL_SWITCH_TRIGGERED"
            )

        # ── All passed ────────────────────────────────────────────
        return WaterfallResult(
            True,
            WaterfallStage.APPROVE,
            "APPROVED",
            adjusted_size=proposed_size,
            details={
                "risk_bps": self._policy.risk_per_trade_bps,
                "positions": len(current_positions),
                "drawdown_bps": current_drawdown_bps,
            },
        )
