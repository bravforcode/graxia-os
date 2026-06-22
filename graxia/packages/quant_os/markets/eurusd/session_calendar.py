from dataclasses import dataclass
from datetime import time
from enum import Enum

class SessionType(Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    LONDON_NY_OVERLAP = "london_ny_overlap"
    OFF_HOURS = "off_hours"

@dataclass(frozen=True)
class TradingSession:
    name: str
    open_time: time
    close_time: time
    session_type: SessionType

# EURUSD active sessions (UTC)
SESSIONS = [
    TradingSession("Asian", time(0, 0), time(8, 0), SessionType.ASIAN),
    TradingSession("London", time(8, 0), time(16, 0), SessionType.LONDON),
    TradingSession("NewYork", time(13, 0), time(21, 0), SessionType.NEW_YORK),
    TradingSession("London-NY Overlap", time(13, 0), time(16, 0), SessionType.LONDON_NY_OVERLAP),
]

def get_active_session(utc_hour: int) -> SessionType:
    # ponytail: overlap checked first since it's the highest-priority subset
    if 13 <= utc_hour < 16:
        return SessionType.LONDON_NY_OVERLAP
    if 8 <= utc_hour < 16:
        return SessionType.LONDON
    if 13 <= utc_hour < 21:
        return SessionType.NEW_YORK
    if 0 <= utc_hour < 8:
        return SessionType.ASIAN
    return SessionType.OFF_HOURS

def is_liquidity_session(utc_hour: int) -> bool:
    session = get_active_session(utc_hour)
    return session in (SessionType.LONDON, SessionType.NEW_YORK, SessionType.LONDON_NY_OVERLAP)
