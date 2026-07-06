"""Risk Overlay — independent risk policy layer.

Enforces position sizing, daily/weekly loss limits, consecutive loss cooldown,
and kill switch. Must approve every trade before execution.

State persists to disk via JSON so kill switch and loss tracking survive restarts.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class KillSwitchReason(Enum):
    NONE = ""
    MANUAL = "MANUAL"
    DAILY_LOSS = "DAILY_LOSS_BREACH"
    WEEKLY_LOSS = "WEEKLY_LOSS_BREACH"
    DRAWDOWN = "DRAWDOWN_BREACH"
    CONSECUTIVE_LOSS = "CONSECUTIVE_LOSS_STREAK"
    SPREAD_SPIKE = "SPREAD_SPIKE"
    DATA_FEED_FAIL = "DATA_FEED_FAIL"
    FILL_REJECT = "FILL_REJECTION_SPIKE"


@dataclass
class RiskResult:
    """Result of risk approval check."""

    approved: bool
    risk_usd: float = 0.0
    risk_pct: float = 0.0
    position_size: float = 0.0
    daily_loss_used: float = 0.0
    weekly_loss_used: float = 0.0
    cooldown_active: bool = False
    kill_switch_active: bool = False
    cooldown_remaining_sec: int = 0
    reason_code: str = ""


@dataclass
class RiskState:
    """Persistent risk tracking state."""

    daily_start: datetime = field(default_factory=datetime.now)
    weekly_start: datetime = field(default_factory=datetime.now)
    daily_realized_pnl: float = 0.0
    weekly_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    trade_count_today: int = 0
    kill_switch_reason: str = ""
    kill_switch_triggered: bool = False
    last_trade_time: datetime | None = None
    cooldown_until: datetime | None = None


class RiskOverlay:
    """Risk policy layer. Must be consulted before every trade.

    Args:
        initial_balance: Starting account balance
        max_risk_pct: Max risk per trade (decimal, default 0.005 = 0.5%)
        max_daily_loss_pct: Max daily loss before halt (default 0.02 = 2%)
        max_weekly_loss_pct: Max weekly loss before halt (default 0.05 = 5%)
        max_consecutive_losses: Losses before cooldown (default 2)
        cooldown_minutes: Cooldown duration (default 30)
        max_daily_trades: Max trades per day (default 10)
    """

    def __init__(
        self,
        initial_balance: float = 50000.0,
        max_risk_pct: float = 0.005,
        max_daily_loss_pct: float = 0.02,
        max_weekly_loss_pct: float = 0.05,
        max_consecutive_losses: int = 2,
        cooldown_minutes: int = 30,
        max_daily_trades: int = 10,
        state_file: str = "data/risk_overlay_state.json",
        coordinator: Any | None = None,
    ):
        self.initial_balance = initial_balance
        self.max_risk_pct = max_risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_minutes = cooldown_minutes
        self.max_daily_trades = max_daily_trades
        self._state_file = Path(state_file)
        self._coordinator = coordinator

        self.state = self._load_state()
        self._reset_if_new_period()

    def approve(self, risk_amount: float, stop_distance: float, current_balance: float) -> RiskResult:
        """Check if a trade is allowed under current risk policy.

        Args:
            risk_amount: USD risk for this trade (from Entry Executor)
            stop_distance: Stop loss distance in price units
            current_balance: Current account balance

        Returns:
            RiskResult with approval decision
        """
        self._reset_if_new_period()
        now = datetime.now()

        # --- Gate 1: Kill switch ---
        if self.state.kill_switch_triggered:
            return RiskResult(
                approved=False,
                kill_switch_active=True,
                reason_code=f"KILL_SWITCH_{self.state.kill_switch_reason}",
            )

        # --- Gate 2: Daily loss ---
        daily_loss_pct = abs(self.state.daily_realized_pnl) / self.initial_balance
        if daily_loss_pct >= self.max_daily_loss_pct:
            self.trigger_kill_switch("DAILY_LOSS_BREACH")
            return RiskResult(approved=False, reason_code="DAILY_LOSS_LIMIT")

        # --- Gate 3: Weekly loss ---
        weekly_loss_pct = abs(self.state.weekly_realized_pnl) / self.initial_balance
        if weekly_loss_pct >= self.max_weekly_loss_pct:
            self.trigger_kill_switch("WEEKLY_LOSS_BREACH")
            return RiskResult(approved=False, reason_code="WEEKLY_LOSS_LIMIT")

        # --- Gate 4: Consecutive loss cooldown ---
        if self.state.cooldown_until and now < self.state.cooldown_until:
            remaining = int((self.state.cooldown_until - now).total_seconds())
            return RiskResult(
                approved=False,
                cooldown_active=True,
                cooldown_remaining_sec=remaining,
                reason_code="CONSECUTIVE_LOSS_COOLDOWN",
            )

        # --- Gate 5: Max daily trades ---
        if self.state.trade_count_today >= self.max_daily_trades:
            return RiskResult(approved=False, reason_code="MAX_DAILY_TRADES")

        # --- Gate 6: Per-trade risk cap ---
        risk_pct = risk_amount / current_balance if current_balance > 0 else 0
        if risk_pct > self.max_risk_pct * 1.1:  # 10% tolerance
            return RiskResult(approved=False, reason_code=f"RISK_CAP_EXCEEDED:{risk_pct:.4f}")

        # --- Position sizing ---
        if stop_distance > 0:
            size = risk_amount / stop_distance
        else:
            return RiskResult(approved=False, reason_code="ZERO_STOP_DISTANCE")

        # --- All gates passed ---
        return RiskResult(
            approved=True,
            risk_usd=round(risk_amount, 2),
            risk_pct=round(risk_pct * 100, 3),
            position_size=round(size, 4),
            daily_loss_used=round(daily_loss_pct * 100, 2),
            weekly_loss_used=round(weekly_loss_pct * 100, 2),
            reason_code="APPROVED",
        )

    def report_trade_result(self, pnl: float):
        """Report P&L after trade closes. Updates risk tracking."""
        self._reset_if_new_period()
        self.state.daily_realized_pnl += pnl
        self.state.weekly_realized_pnl += pnl
        self.state.trade_count_today += 1
        self.state.last_trade_time = datetime.now()

        if pnl < 0:
            self.state.consecutive_losses += 1
            if self.state.consecutive_losses >= self.max_consecutive_losses:
                self.state.cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
        else:
            self.state.consecutive_losses = 0  # reset on win

        # Auto-trigger kill switch on extreme loss
        daily_pct = abs(self.state.daily_realized_pnl) / self.initial_balance
        if daily_pct >= self.max_daily_loss_pct:
            self.trigger_kill_switch("DAILY_LOSS_BREACH")
        weekly_pct = abs(self.state.weekly_realized_pnl) / self.initial_balance
        if weekly_pct >= self.max_weekly_loss_pct:
            self.trigger_kill_switch("WEEKLY_LOSS_BREACH")
        self._save_state()

    def set_coordinator(self, coordinator: Any) -> None:
        """Wire in the StateCoordinator for cross-store sync."""
        self._coordinator = coordinator

    def trigger_kill_switch(self, reason: str = "MANUAL"):
        """Activate kill switch. Blocks all further trading."""
        self.state.kill_switch_triggered = True
        self.state.kill_switch_reason = reason
        self._save_state()
        if self._coordinator is not None:
            self._coordinator.sync_kill_switch(True, reason, source="risk_overlay", triggering_store="risk_overlay")

    def release_kill_switch(self):
        """Deactivate kill switch."""
        self.state.kill_switch_triggered = False
        self.state.kill_switch_reason = ""
        self._save_state()
        if self._coordinator is not None:
            self._coordinator.sync_kill_switch(False, "manual", source="risk_overlay", triggering_store="risk_overlay")

    def get_status(self) -> dict:
        """Return current risk status summary."""
        self._reset_if_new_period()
        daily_pct = abs(self.state.daily_realized_pnl) / self.initial_balance * 100
        weekly_pct = abs(self.state.weekly_realized_pnl) / self.initial_balance * 100
        return {
            "kill_switch": self.state.kill_switch_triggered,
            "kill_switch_reason": self.state.kill_switch_reason,
            "daily_pnl": round(self.state.daily_realized_pnl, 2),
            "daily_used_pct": round(daily_pct, 2),
            "weekly_pnl": round(self.state.weekly_realized_pnl, 2),
            "weekly_used_pct": round(weekly_pct, 2),
            "consecutive_losses": self.state.consecutive_losses,
            "cooldown_until": str(self.state.cooldown_until) if self.state.cooldown_until else "",
            "trades_today": self.state.trade_count_today,
        }

    def _reset_if_new_period(self):
        """Reset daily/weekly counters at period boundaries."""
        now = datetime.now()

        # Daily reset
        if now.date() > self.state.daily_start.date():
            self.state.daily_start = now
            self.state.daily_realized_pnl = 0.0
            self.state.trade_count_today = 0

        # Weekly reset (Monday)
        if now.weekday() == 0 and self.state.weekly_start.date() < now.date():
            self.state.weekly_start = now
            self.state.weekly_realized_pnl = 0.0

    def _save_state(self):
        """Persist state to disk atomically so kill switch survives restart."""
        import tempfile

        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "daily_start": self.state.daily_start.isoformat(),
            "weekly_start": self.state.weekly_start.isoformat(),
            "daily_realized_pnl": self.state.daily_realized_pnl,
            "weekly_realized_pnl": self.state.weekly_realized_pnl,
            "consecutive_losses": self.state.consecutive_losses,
            "trade_count_today": self.state.trade_count_today,
            "kill_switch_reason": self.state.kill_switch_reason,
            "kill_switch_triggered": self.state.kill_switch_triggered,
            "last_trade_time": self.state.last_trade_time.isoformat() if self.state.last_trade_time else None,
            "cooldown_until": self.state.cooldown_until.isoformat() if self.state.cooldown_until else None,
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_file.parent),
            prefix=".risk_overlay_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._state_file))
        except Exception:
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _load_state(self) -> RiskState:
        """Load state from disk, or return fresh state if file missing."""
        if not self._state_file.exists():
            return RiskState()
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return RiskState(
                daily_start=datetime.fromisoformat(data["daily_start"]),
                weekly_start=datetime.fromisoformat(data["weekly_start"]),
                daily_realized_pnl=data.get("daily_realized_pnl", 0.0),
                weekly_realized_pnl=data.get("weekly_realized_pnl", 0.0),
                consecutive_losses=data.get("consecutive_losses", 0),
                trade_count_today=data.get("trade_count_today", 0),
                kill_switch_reason=data.get("kill_switch_reason", ""),
                kill_switch_triggered=data.get("kill_switch_triggered", False),
                last_trade_time=datetime.fromisoformat(data["last_trade_time"])
                if data.get("last_trade_time")
                else None,
                cooldown_until=datetime.fromisoformat(data["cooldown_until"]) if data.get("cooldown_until") else None,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            state = RiskState()
            state.kill_switch_triggered = True
            state.kill_switch_reason = "STATE_FILE_CORRUPTED"
            return state
