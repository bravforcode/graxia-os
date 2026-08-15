"""Risk Budget — limits total risk per day/week."""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class RiskBudget:
    max_daily_loss_pct: float = 2.0  # Max 2% loss per day
    max_weekly_loss_pct: float = 5.0  # Max 5% loss per week
    max_position_pct: float = 1.0  # Max 1% risk per trade
    max_open_positions: int = 3
    current_daily_pnl: float = 0.0
    current_weekly_pnl: float = 0.0
    open_positions: int = 0
    daily_reset_date: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d"))
    weekly_reset_date: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-W%W"))

    def can_trade(self) -> tuple[bool, str]:
        self._check_resets()
        if self.current_daily_pnl <= -self.max_daily_loss_pct:
            return False, f"Daily loss limit reached: {self.current_daily_pnl:.2f}%"
        if self.current_weekly_pnl <= -self.max_weekly_loss_pct:
            return False, f"Weekly loss limit reached: {self.current_weekly_pnl:.2f}%"
        if self.open_positions >= self.max_open_positions:
            return False, f"Max open positions: {self.open_positions}"
        return True, "OK"

    def record_trade(self, pnl_pct: float) -> None:
        self.current_daily_pnl += pnl_pct
        self.current_weekly_pnl += pnl_pct

    def record_position_open(self) -> None:
        self.open_positions += 1

    def record_position_close(self) -> None:
        self.open_positions = max(0, self.open_positions - 1)

    def _check_resets(self) -> None:
        now = datetime.now(UTC)
        today = now.strftime("%Y-%m-%d")
        week = now.strftime("%Y-W%W")
        if today != self.daily_reset_date:
            self.current_daily_pnl = 0.0
            self.daily_reset_date = today
        if week != self.weekly_reset_date:
            self.current_weekly_pnl = 0.0
            self.weekly_reset_date = week


def save_state(budget: RiskBudget, path: str | Path) -> None:
    """Persist a RiskBudget to disk as JSON."""
    Path(path).write_text(json.dumps(asdict(budget)))


def load_state(path: str | Path) -> RiskBudget:
    """Load a RiskBudget previously written by save_state()."""
    data = json.loads(Path(path).read_text())
    return RiskBudget(**data)
