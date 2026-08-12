"""Phase BE-P7 — EURUSD session calendar."""
from dataclasses import dataclass


@dataclass
class TradingSession:
    name: str
    open_hour_utc: int
    close_hour_utc: int
    typical_spread_pips: float
    typical_volume: str  # high, medium, low


class EURUSDSessionCalendar:
    """EURUSD trading sessions."""

    def __init__(self):
        self._sessions = [
            TradingSession("asian", 0, 7, 1.5, "low"),
            TradingSession("london", 7, 16, 0.8, "high"),
            TradingSession("new_york", 13, 21, 1.0, "high"),
            TradingSession("overlap_london_ny", 13, 16, 0.6, "very_high"),
        ]

    def get_sessions(self) -> list[TradingSession]:
        return self._sessions.copy()

    def get_session(self, name: str) -> TradingSession | None:
        for s in self._sessions:
            if s.name == name:
                return s
        return None

    def is_session_open(self, hour_utc: int) -> bool:
        for s in self._sessions:
            if s.open_hour_utc <= hour_utc < s.close_hour_utc:
                return True
        return False

    def get_active_sessions(self, hour_utc: int) -> list[TradingSession]:
        return [s for s in self._sessions
                if s.open_hour_utc <= hour_utc < s.close_hour_utc]
