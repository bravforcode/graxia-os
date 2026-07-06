"""
Auto-Stop Drawdown Protection — Automatic kill switch activation on drawdown breach.

Monitors portfolio equity against a high-water mark (HWM). When drawdown exceeds
the configured threshold, automatically activates the KillSwitch.

Key design decisions:
  - Threshold: 15% (conservative, well below backtest max DD of 42.11%)
  - Recovery: Manual reset ONLY (no auto-recovery — must be intentional)
  - Persistence: State survives restarts via JSON state file
  - Audit: All activations and resets logged with timestamp, drawdown, reason

Usage:
    from risk.auto_stop import AutoStop

    auto_stop = AutoStop(
        kill_switch=kill_switch,
        threshold_pct=15.0,
        state_file="data/auto_stop_state.json",
    )

    # Update equity each tick/bar
    auto_stop.update_equity(current_equity)

    # Check before trading
    if auto_stop.is_triggered:
        # Skip trading
        pass
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AutoStopConfig:
    """Configuration for auto-stop drawdown protection."""

    # Drawdown threshold as percentage (e.g., 15.0 = 15%)
    threshold_pct: float = 15.0

    # High-water mark tracking
    hwm: float = 0.0

    # Whether auto-stop is currently triggered
    triggered: bool = False

    # Current drawdown percentage (negative value)
    current_drawdown_pct: float = 0.0


class AutoStop:
    """
    Automatic drawdown protection that activates the KillSwitch when
    portfolio drawdown exceeds a configured threshold.

    State persists across restarts. Recovery requires explicit manual reset.
    """

    def __init__(
        self,
        kill_switch: Any | None = None,
        threshold_pct: float = 15.0,
        state_file: str | None = None,
    ):
        """
        Initialize auto-stop drawdown protection.

        Args:
            kill_switch: KillSwitch instance to activate on breach.
            threshold_pct: Drawdown threshold percentage (default 15%).
            state_file: Path to persist state across restarts.
        """
        self._kill_switch = kill_switch
        self._threshold_pct = threshold_pct
        self._state_file = Path(state_file) if state_file else None

        # State
        self._hwm: float = 0.0
        self._triggered: bool = False
        self._triggered_at: str | None = None
        self._trigger_drawdown_pct: float = 0.0
        self._reset_at: str | None = None
        self._reset_by: str | None = None
        self._history: list[dict[str, Any]] = []

        # Load persisted state
        if self._state_file and self._state_file.exists():
            self._load()

    @property
    def is_triggered(self) -> bool:
        """Whether auto-stop has been triggered (kill switch activated)."""
        return self._triggered

    @property
    def threshold_pct(self) -> float:
        """The drawdown threshold percentage."""
        return self._threshold_pct

    @property
    def high_water_mark(self) -> float:
        """The current high-water mark."""
        return self._hwm

    @property
    def current_drawdown_pct(self) -> float:
        """Current drawdown as a negative percentage."""
        if self._hwm <= 0:
            return 0.0
        return self._trigger_drawdown_pct if self._triggered else self._current_dd_pct

    @property
    def _current_dd_pct(self) -> float:
        """Calculate current drawdown from HWM."""
        # This is updated by update_equity()
        return getattr(self, "_last_equity_dd_pct", 0.0)

    def update_equity(self, equity: float) -> dict[str, Any]:
        """
        Update portfolio equity and check drawdown.

        Args:
            equity: Current portfolio equity value.

        Returns:
            Dict with status info: {triggered, drawdown_pct, hwm, threshold_pct}
        """
        if equity <= 0:
            logger.warning("auto_stop.update_equity: equity <= 0 (%.2f), ignoring", equity)
            return self._get_status()

        # Update HWM if equity is higher
        if equity > self._hwm:
            self._hwm = equity
            logger.debug("auto_stop: HWM updated to %.2f", self._hwm)

        # Calculate drawdown
        if self._hwm > 0:
            drawdown_pct = ((self._hwm - equity) / self._hwm) * 100.0
        else:
            drawdown_pct = 0.0

        self._last_equity_dd_pct = -drawdown_pct  # Negative convention

        # Check threshold
        if not self._triggered and drawdown_pct >= self._threshold_pct:
            self._activate(equity, drawdown_pct)

        return self._get_status()

    def _activate(self, equity: float, drawdown_pct: float) -> None:
        """Activate auto-stop and trigger kill switch."""
        self._triggered = True
        self._triggered_at = datetime.now(UTC).isoformat()
        self._trigger_drawdown_pct = -drawdown_pct

        reason = (
            f"Auto-stop triggered: drawdown {drawdown_pct:.2f}% "
            f"exceeded threshold {self._threshold_pct:.2f}% "
            f"(equity={equity:.2f}, HWM={self._hwm:.2f})"
        )

        # Record in history
        self._history.append(
            {
                "action": "triggered",
                "timestamp": self._triggered_at,
                "drawdown_pct": round(drawdown_pct, 4),
                "threshold_pct": self._threshold_pct,
                "equity": equity,
                "hwm": self._hwm,
            }
        )
        self._save()

        # Activate kill switch
        if self._kill_switch is not None:
            try:
                self._kill_switch.activate(
                    reason=reason,
                    source="auto_stop",
                )
                logger.critical("AUTO-STOP: %s", reason)
            except Exception as exc:
                logger.error("auto_stop: failed to activate kill_switch: %s", exc)
        else:
            logger.warning("auto_stop: no kill_switch wired — trigger recorded but not enforced")

    def reset(
        self,
        authorized_by: str,
        reason: str,
        reset_hwm: bool = True,
        new_equity: float | None = None,
    ) -> dict[str, Any]:
        """
        Reset auto-stop. Requires authorization and reason for audit.

        IMPORTANT: This is the ONLY way to recover from auto-stop.
        No automatic recovery exists — reset must be intentional.

        Args:
            authorized_by: Who authorized the reset (e.g., "telegram:12345", "admin_api").
            reason: Why the reset is being performed.
            reset_hwm: Whether to reset HWM to current equity (default True).
            new_equity: If provided, set HWM to this value.

        Returns:
            Dict with reset status.
        """
        if not authorized_by or not reason:
            raise ValueError("reset() requires both authorized_by and reason")

        now = datetime.now(UTC).isoformat()

        # Record in history
        self._history.append(
            {
                "action": "reset",
                "timestamp": now,
                "authorized_by": authorized_by,
                "reason": reason,
                "previous_drawdown_pct": round(self._trigger_drawdown_pct, 4),
                "reset_hwm": reset_hwm,
            }
        )

        # Reset state
        self._triggered = False
        self._triggered_at = None
        self._trigger_drawdown_pct = 0.0
        self._reset_at = now
        self._reset_by = authorized_by

        # Optionally reset HWM
        if reset_hwm:
            self._hwm = new_equity if new_equity else 0.0
            self._last_equity_dd_pct = 0.0

        # Deactivate kill switch if it was activated by auto-stop
        if self._kill_switch is not None:
            try:
                self._kill_switch.deactivate(
                    reason=f"Auto-stop reset by {authorized_by}: {reason}",
                    authorized_by=authorized_by,
                )
                logger.info("auto_stop.reset: kill switch deactivated")
            except Exception as exc:
                logger.error("auto_stop.reset: failed to deactivate kill switch: %s", exc)

        self._save()

        logger.info(
            "auto_stop.reset: authorized_by=%s reason=%s reset_hwm=%s new_hwm=%.2f",
            authorized_by,
            reason,
            reset_hwm,
            self._hwm,
        )

        return {
            "status": "reset",
            "authorized_by": authorized_by,
            "reason": reason,
            "new_hwm": self._hwm,
            "timestamp": now,
        }

    def get_status(self) -> dict[str, Any]:
        """Get current auto-stop status."""
        return self._get_status()

    def get_history(self) -> list[dict[str, Any]]:
        """Get history of triggers and resets."""
        return list(self._history)

    def _get_status(self) -> dict[str, Any]:
        """Internal status dict."""
        return {
            "triggered": self._triggered,
            "threshold_pct": self._threshold_pct,
            "high_water_mark": self._hwm,
            "current_drawdown_pct": self._trigger_drawdown_pct if self._triggered else self._current_dd_pct,
            "triggered_at": self._triggered_at,
            "reset_at": self._reset_at,
            "reset_by": self._reset_by,
        }

    def _save(self) -> None:
        """Save state atomically using temp file + rename."""
        import contextlib
        import os
        import tempfile

        if not self._state_file:
            return

        state = {
            "threshold_pct": self._threshold_pct,
            "hwm": self._hwm,
            "triggered": self._triggered,
            "triggered_at": self._triggered_at,
            "trigger_drawdown_pct": self._trigger_drawdown_pct,
            "reset_at": self._reset_at,
            "reset_by": self._reset_by,
            "history": self._history[-100:],  # Keep last 100 events
        }

        path = self._state_file
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".auto_stop_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _load(self) -> None:
        """Load state from JSON."""
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._threshold_pct = data.get("threshold_pct", self._threshold_pct)
            self._hwm = data.get("hwm", 0.0)
            self._triggered = data.get("triggered", False)
            self._triggered_at = data.get("triggered_at")
            self._trigger_drawdown_pct = data.get("trigger_drawdown_pct", 0.0)
            self._reset_at = data.get("reset_at")
            self._reset_by = data.get("reset_by")
            self._history = data.get("history", [])
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("auto_stop._load: failed to load state: %s", exc)
