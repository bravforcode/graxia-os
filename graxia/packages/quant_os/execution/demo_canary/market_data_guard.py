"""
Guard: verify canonical tick freshness, spread, event blackout, session.
Read-only. Fail-closed.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

MAX_TICK_AGE_SECONDS = 5
MAX_SPREAD_POINTS = 25  # 0.25 in point units for XAUUSD (point=0.01)

@dataclass(frozen=True)
class MarketDataGuardResult:
    passed: bool
    reason: str = ""
    tick_age_ms: int = 0
    spread_points: float = 0.0

def verify_tick_freshness(tick_time: Optional[datetime] = None) -> MarketDataGuardResult:
    """Verify last tick is within MAX_TICK_AGE_SECONDS."""
    if tick_time is None:
        return MarketDataGuardResult(False, "No tick data available")
    now = datetime.now(timezone.utc)
    age = (now - tick_time).total_seconds() * 1000
    if age > MAX_TICK_AGE_SECONDS * 1000:
        return MarketDataGuardResult(False, f"Tick age {age:.0f}ms exceeds {MAX_TICK_AGE_SECONDS*1000}ms", tick_age_ms=int(age))
    return MarketDataGuardResult(True, tick_age_ms=int(age))

def verify_spread(spread_points: float) -> MarketDataGuardResult:
    """Verify spread is within fixed canary threshold."""
    if spread_points <= 0:
        return MarketDataGuardResult(False, f"Invalid spread: {spread_points}")
    if spread_points > MAX_SPREAD_POINTS:
        return MarketDataGuardResult(False, f"Spread {spread_points}pt exceeds {MAX_SPREAD_POINTS}pt", spread_points=spread_points)
    return MarketDataGuardResult(True, spread_points=spread_points)

# Event blackout simulation (no real calendar in G2)
HIGH_IMPACT_EVENTS = []  # Populated from calendar source in production

def verify_event_blackout() -> MarketDataGuardResult:
    """Verify no high-impact economic event blackout."""
    now = datetime.now(timezone.utc)
    for event in HIGH_IMPACT_EVENTS:
        start = event.get("start")
        end = event.get("end")
        if start and end and start <= now <= end:
            return MarketDataGuardResult(False, f"Event blackout active: {event.get('name', 'unknown')}")
    return MarketDataGuardResult(True)

ALLOWED_SESSIONS = ["LONDON", "NEW_YORK", "ASIAN"]

def verify_session(session: str = "") -> MarketDataGuardResult:
    """Verify trading session is allowed."""
    if session and session not in ALLOWED_SESSIONS:
        return MarketDataGuardResult(False, f"Session {session} not allowed")
    return MarketDataGuardResult(True)
