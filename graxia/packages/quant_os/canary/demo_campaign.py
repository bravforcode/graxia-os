"""Phase BE-P10 — Demo campaign manager."""
from dataclasses import dataclass


@dataclass
class CampaignState:
    status: str = "idle"  # idle, running, paused, completed, failed
    days_run: int = 0
    total_signals: int = 0
    total_orders: int = 0
    total_fills: int = 0
    incidents: int = 0
    critical_incidents: int = 0


class DemoCampaign:
    """Manage demo campaign lifecycle."""
    
    def __init__(self):
        self._state = CampaignState()
        self._daily_reports: list = []
        self._weekly_reports: list = []
    
    def start(self) -> None:
        self._state.status = "running"
    
    def pause(self) -> None:
        self._state.status = "paused"
    
    def resume(self) -> None:
        self._state.status = "running"
    
    def complete(self) -> None:
        self._state.status = "completed"
    
    def fail(self) -> None:
        self._state.status = "failed"
    
    def record_day(self, signals: int, orders: int, fills: int, incidents: int) -> None:
        self._state.days_run += 1
        self._state.total_signals += signals
        self._state.total_orders += orders
        self._state.total_fills += fills
        self._state.incidents += incidents
    
    def get_state(self) -> CampaignState:
        return self._state
    
    def is_running(self) -> bool:
        return self._state.status == "running"
    
    def get_summary(self) -> dict:
        return {
            "status": self._state.status,
            "days_run": self._state.days_run,
            "total_signals": self._state.total_signals,
            "total_orders": self._state.total_orders,
            "total_fills": self._state.total_fills,
            "incidents": self._state.incidents,
        }
