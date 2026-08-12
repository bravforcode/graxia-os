# WARNING: This engine executes trades autonomously.
# DO NOT ENABLE without explicit user approval.
# Requires: --enable-autonomous flag or manual activation.

"""Autonomous Trading Engine — full auto with safety guards.

SAFETY GUARDS (hardcoded, not configurable):
1. Kill switch: emergency stop all trading
2. Max daily loss: 2% of account — stops trading
3. Max weekly loss: 5% of account — stops trading
4. Max position size: 1% risk per trade
5. Max open positions: 3
6. News blackout: blocks trades during HIGH/CRISIS news
7. Session filter: blocks trades outside trading hours
8. Regime gate: CRISIS = no new positions
9. Correlation gate: high correlation = reduced sizing
10. Cooldown: 5 min between trades (prevents overtrading)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class EngineState(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    TRADING = "trading"
    PAUSED = "paused"
    KILLED = "killed"
    RISK_LOCKED = "risk_locked"


@dataclass
class TradeDecision:
    symbol: str
    action: str
    confidence: float
    position_size_pct: float
    reason: str
    guards_checked: list[str] = field(default_factory=list)
    guards_passed: list[str] = field(default_factory=list)


class AutonomousEngine:
    """Full autonomous trading engine with safety guards."""

    MAX_DAILY_LOSS_PCT = 2.0
    MAX_WEEKLY_LOSS_PCT = 5.0
    MAX_POSITION_PCT = 1.0
    MAX_OPEN_POSITIONS = 3
    COOLDOWN_SECONDS = 300

    def __init__(self) -> None:
        self._state = EngineState.IDLE
        self._kill_switch = False
        self._daily_pnl = 0.0
        self._weekly_pnl = 0.0
        self._open_positions = 0
        self._last_trade_time = 0.0
        self._trade_log: list[dict] = []

    def emergency_stop(self) -> None:
        """Kill switch — stops all trading immediately."""
        self._kill_switch = True
        self._state = EngineState.KILLED
        logger.warning("engine.kill_switch_activated")

    def resume(self) -> None:
        """Resume trading (requires manual confirmation)."""
        self._kill_switch = False
        self._state = EngineState.IDLE
        logger.info("engine.resumed")

    def evaluate(
        self,
        symbol: str,
        signal: str,
        confidence: float,
        regime_label: str,
        is_news_blocked: bool,
        session_active: bool,
        correlation_adj: float = 1.0,
    ) -> TradeDecision:
        """Evaluate whether to trade. Returns decision with guard results."""
        guards_checked: list[str] = []
        guards_passed: list[str] = []

        # Guard 1: Kill switch
        guards_checked.append("kill_switch")
        if self._kill_switch:
            self._state = EngineState.KILLED
            return self._reject(symbol, "Kill switch active", guards_checked, guards_passed)
        guards_passed.append("kill_switch")

        # Guard 2: Daily loss limit
        guards_checked.append("daily_loss")
        if self._daily_pnl <= -self.MAX_DAILY_LOSS_PCT:
            self._state = EngineState.RISK_LOCKED
            return self._reject(
                symbol,
                f"Daily loss limit: {self._daily_pnl:.2f}%",
                guards_checked,
                guards_passed,
            )
        guards_passed.append("daily_loss")

        # Guard 3: Weekly loss limit
        guards_checked.append("weekly_loss")
        if self._weekly_pnl <= -self.MAX_WEEKLY_LOSS_PCT:
            self._state = EngineState.RISK_LOCKED
            return self._reject(
                symbol,
                f"Weekly loss limit: {self._weekly_pnl:.2f}%",
                guards_checked,
                guards_passed,
            )
        guards_passed.append("weekly_loss")

        # Guard 4: Max positions
        guards_checked.append("max_positions")
        if self._open_positions >= self.MAX_OPEN_POSITIONS:
            return self._reject(
                symbol,
                f"Max positions: {self._open_positions}",
                guards_checked,
                guards_passed,
            )
        guards_passed.append("max_positions")

        # Guard 5: News blackout
        guards_checked.append("news_blackout")
        if is_news_blocked:
            self._state = EngineState.PAUSED
            return self._reject(symbol, "News blackout active", guards_checked, guards_passed)
        guards_passed.append("news_blackout")

        # Guard 6: Session filter
        guards_checked.append("session_filter")
        if not session_active:
            self._state = EngineState.PAUSED
            return self._reject(symbol, "Outside trading session", guards_checked, guards_passed)
        guards_passed.append("session_filter")

        # Guard 7: Regime gate
        guards_checked.append("regime_gate")
        if regime_label == "CRISIS":
            return self._reject(
                symbol,
                "CRISIS regime — no new positions",
                guards_checked,
                guards_passed,
            )
        guards_passed.append("regime_gate")

        # Guard 8: Cooldown
        guards_checked.append("cooldown")
        if (time.time() - self._last_trade_time) < self.COOLDOWN_SECONDS:
            return self._reject(symbol, "Cooldown active", guards_checked, guards_passed)
        guards_passed.append("cooldown")

        # Guard 9: Confidence threshold
        guards_checked.append("confidence")
        if confidence < 0.6:
            return self._reject(
                symbol,
                f"Low confidence: {confidence:.2f}",
                guards_checked,
                guards_passed,
            )
        guards_passed.append("confidence")

        # All guards passed — calculate position size
        pos_mult = 1.0
        if regime_label == "HIGH_UNCERTAINTY":
            pos_mult = 0.5
        pos_pct = self.MAX_POSITION_PCT * pos_mult * correlation_adj
        pos_pct = min(pos_pct, self.MAX_POSITION_PCT)

        self._state = EngineState.TRADING
        self._last_trade_time = time.time()

        decision = TradeDecision(
            symbol=symbol,
            action=signal,
            confidence=confidence,
            position_size_pct=round(pos_pct, 4),
            reason=f"Approved: {signal} {symbol} @ {confidence:.2f}",
            guards_checked=guards_checked,
            guards_passed=guards_passed,
        )

        self._trade_log.append(
            {
                "time": datetime.now(UTC).isoformat(),
                "symbol": symbol,
                "action": signal,
                "confidence": confidence,
                "position_pct": pos_pct,
                "regime": regime_label,
            }
        )

        logger.info(
            "engine.trade_approved",
            symbol=symbol,
            action=signal,
            pos_pct=pos_pct,
            regime=regime_label,
        )
        return decision

    def _reject(
        self,
        symbol: str,
        reason: str,
        checked: list[str],
        passed: list[str],
    ) -> TradeDecision:
        logger.info("engine.trade_rejected", symbol=symbol, reason=reason)
        return TradeDecision(
            symbol=symbol,
            action="HOLD",
            confidence=0.0,
            position_size_pct=0.0,
            reason=reason,
            guards_checked=checked,
            guards_passed=passed,
        )

    def record_pnl(self, pnl_pct: float) -> None:
        self._daily_pnl += pnl_pct
        self._weekly_pnl += pnl_pct

    def record_position_open(self) -> None:
        self._open_positions += 1

    def record_position_close(self) -> None:
        self._open_positions = max(0, self._open_positions - 1)

    def get_state(self) -> dict:
        return {
            "state": self._state.value,
            "kill_switch": self._kill_switch,
            "daily_pnl": self._daily_pnl,
            "weekly_pnl": self._weekly_pnl,
            "open_positions": self._open_positions,
            "trade_count": len(self._trade_log),
        }
