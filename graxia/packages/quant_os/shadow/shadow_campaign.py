"""Phase BE-P8 — Shadow campaign manager."""
from dataclasses import dataclass
from datetime import datetime, UTC


@dataclass
class CampaignConfig:
    symbol: str = "XAUUSD"
    strategy_id: str = ""
    broker: str = ""
    server: str = ""
    max_duration_hours: int = 24
    max_signals_per_day: int = 100


class ShadowCampaign:
    """Manage shadow campaign lifecycle."""

    def __init__(self, config: CampaignConfig):
        self._config = config
        self._active: bool = False
        self._start_time: str = ""
        self._end_time: str = ""
        self._signal_count: int = 0
        self._status: str = "idle"  # idle, running, completed, failed

    def start(self) -> None:
        self._active = True
        self._start_time = datetime.now(UTC).isoformat()
        self._status = "running"
        self._signal_count = 0

    def stop(self, reason: str = "completed") -> None:
        self._active = False
        self._end_time = datetime.now(UTC).isoformat()
        self._status = "completed" if reason == "completed" else "failed"

    def record_signal(self) -> None:
        if self._active:
            self._signal_count += 1

    def is_active(self) -> bool:
        return self._active

    def get_status(self) -> str:
        return self._status

    def get_config(self) -> CampaignConfig:
        return self._config

    def get_summary(self) -> dict:
        return {
            "symbol": self._config.symbol,
            "strategy_id": self._config.strategy_id,
            "status": self._status,
            "start_time": self._start_time,
            "end_time": self._end_time,
            "signal_count": self._signal_count,
        }
