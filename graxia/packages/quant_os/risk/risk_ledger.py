"""Simple JSON-file-based daily risk tracking."""

import json
from pathlib import Path
from datetime import datetime, date, UTC


class RiskLedger:
    """
    Tracks daily/weekly risk metrics in a JSON file.
    Reset daily counters at start of each trading day.
    """

    def __init__(self, state_file: str = "data/risk_ledger.json"):
        self._state_file = Path(state_file)
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
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self._state, indent=2))

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

        total_drawdown tracks peak-to-trough equity drawdown (correct definition),
        not the max single-trade loss. Call ``update_equity()`` after each trade
        to keep the drawdown accurate.
        """
        self._maybe_reset()
        if pnl < 0:
            self._state["daily_realized_loss"] += abs(pnl)
            self._state["weekly_realized_loss"] += abs(pnl)
        # NOTE: total_drawdown is updated by update_equity(), not here.
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

    def set_kill_switch_state(self, state: str) -> None:
        self._state["kill_switch_state"] = state
        self._save()

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
