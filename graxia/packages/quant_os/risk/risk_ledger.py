"""Simple JSON-file-based daily risk tracking."""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


class RiskLedger:
    """
    Tracks daily/weekly risk metrics in a JSON file.
    Reset daily counters at start of each trading day.
    """

    def __init__(self, state_file: str = "data/risk_ledger.json", coordinator: Any | None = None):
        self._state_file = Path(state_file)
        self._coordinator = coordinator
        self._state = self._load()

    def _load(self) -> dict:
        if self._state_file.exists():
            return json.loads(self._state_file.read_text())
        return self._default_state()

    def _default_state(self) -> dict:
        return {
            "daily_realized_loss": 0.0,
            "weekly_realized_loss": 0.0,
            "total_drawdown": 0.0,
            "peak_equity": 0.0,
            "cumulative_equity": 0.0,
            "orders_today": 0,
            "open_positions": 0,
            "gross_exposure": 0.0,
            "symbol_exposure": {},
            "rejection_reasons": [],
            "kill_switch_state": "inactive",
            "last_reset_date": date.today().isoformat(),
            "last_reset_week": datetime.now(UTC).isocalendar()[1],
        }

    def _save(self):
        """Persist state atomically using temp file + rename."""
        import tempfile

        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_file.parent),
            prefix=".risk_ledger_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._state_file))
        except Exception:
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def _maybe_reset(self):
        """Reset daily/weekly counters if date/week changed."""
        today = date.today().isoformat()
        if self._state.get("last_reset_date") != today:
            self._state["daily_realized_loss"] = 0.0
            self._state["orders_today"] = 0
            self._state["rejection_reasons"] = []
            self._state["last_reset_date"] = today

        current_week = datetime.now(UTC).isocalendar()[1]
        if self._state.get("last_reset_week") != current_week:
            self._state["weekly_realized_loss"] = 0.0
            self._state["last_reset_week"] = current_week

    def record_trade(self, pnl: float, symbol: str, volume: float) -> None:
        """Record a completed trade outcome.

        Tracks daily/weekly loss, cumulative equity, and peak-to-trough drawdown.
        Drawdown is updated automatically via cumulative equity tracking.
        """
        self._maybe_reset()
        if pnl < 0:
            self._state["daily_realized_loss"] += abs(pnl)
            self._state["weekly_realized_loss"] += abs(pnl)
        # Update cumulative equity and drawdown
        self._state["cumulative_equity"] = self._state.get("cumulative_equity", 0.0) + pnl
        self.update_equity(self._state["cumulative_equity"])
        self._save()

    def update_equity(self, equity: float) -> None:
        """Update peak equity and recompute drawdown.

        Call this after every trade with the current account equity.
        Drawdown = (peak - current) / peak, expressed as a positive fraction.
        """
        if equity > self._state.get("peak_equity", 0.0):
            self._state["peak_equity"] = equity
        peak = self._state.get("peak_equity", 0.0)
        if peak > 0:
            self._state["total_drawdown"] = max(0.0, (peak - equity) / peak)
        self._save()

    def record_order(self) -> None:
        """Record a new order attempt."""
        self._maybe_reset()
        self._state["orders_today"] += 1
        self._save()

    def set_open_positions(self, count: int, gross_exposure: float = 0.0, symbol_exposure: dict = None) -> None:
        """Update open position metrics."""
        self._state["open_positions"] = count
        self._state["gross_exposure"] = gross_exposure
        if symbol_exposure is not None:
            self._state["symbol_exposure"] = symbol_exposure
        self._save()

    def add_rejection(self, reason: str) -> None:
        """Record a rejection reason (capped at 1000 entries to bound memory)."""
        self._maybe_reset()
        reasons = self._state["rejection_reasons"]
        reasons.append(reason)
        # P5 FIX: cap at 1000 to prevent unbounded memory growth
        if len(reasons) > 1000:
            self._state["rejection_reasons"] = reasons[-1000:]
        self._save()

    def set_coordinator(self, coordinator: Any) -> None:
        """Wire in the StateCoordinator for cross-store sync."""
        self._coordinator = coordinator

    def set_kill_switch_state(self, state: str) -> None:
        self._state["kill_switch_state"] = state
        self._save()
        if self._coordinator is not None:
            active = state.lower() in ("active", "triggered")
            self._coordinator.sync_kill_switch(
                active, f"ledger:{state}", source="risk_ledger", triggering_store="risk_ledger"
            )

    @property
    def daily_realized_loss(self) -> float:
        self._maybe_reset()
        return self._state["daily_realized_loss"]

    @property
    def weekly_realized_loss(self) -> float:
        self._maybe_reset()
        return self._state["weekly_realized_loss"]

    @property
    def total_drawdown(self) -> float:
        return self._state["total_drawdown"]

    @property
    def orders_today(self) -> int:
        self._maybe_reset()
        return self._state["orders_today"]

    @property
    def open_positions(self) -> int:
        return self._state["open_positions"]

    @property
    def kill_switch_state(self) -> str:
        return self._state["kill_switch_state"]
