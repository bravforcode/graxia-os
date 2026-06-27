"""
Session Filter — Trade only during high-edge sessions for XAUUSD.

Sessions (UTC):
  - Asian:   00:00 - 08:00 (low volume, tight range)
  - London:  08:00 - 16:00 (high volume, breakouts)
  - NY:      13:00 - 21:00 (highest volume, trends)
  - Overlap: 13:00 - 16:00 (London+NY = best edge)

XAUUSD edge by session:
  - London open: Strongest directional moves
  - NY open: Continuation or reversal
  - Asian: Mean-reversion only (avoid breakouts)

Usage:
  from core.session_filter import SessionFilter
  sf = SessionFilter()
  if sf.is_active():
      multiplier = sf.get_edge_multiplier("XAUUSD")
"""
from __future__ import annotations

from datetime import UTC, datetime, time
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class Session(str, Enum):
    ASIAN = "asian"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"  # London + NY
    CLOSED = "closed"


# Session boundaries (UTC)
SESSION_TIMES = {
    Session.ASIAN: (time(0, 0), time(8, 0)),
    Session.LONDON: (time(8, 0), time(16, 0)),
    Session.NEW_YORK: (time(13, 0), time(21, 0)),
    Session.OVERLAP: (time(13, 0), time(16, 0)),
}

# Edge multipliers per session for XAUUSD
# Higher = more confident in edge
EDGE_MULTIPLIERS = {
    Session.ASIAN: 0.3,       # Low edge — avoid or reduce size
    Session.LONDON: 1.0,      # Full edge — London open breakout
    Session.NEW_YORK: 0.9,    # Good edge — NY continuation
    Session.OVERLAP: 1.2,     # Best edge — double volume
    Session.CLOSED: 0.0,      # No edge — market closed
}

# Symbol-specific adjustments
SYMBOL_SESSION_BIAS = {
    "XAUUSD": {
        Session.ASIAN: 0.2,   # Gold is quiet in Asian session
        Session.LONDON: 1.0,
        Session.NEW_YORK: 0.9,
        Session.OVERLAP: 1.3, # Gold moves most during overlap
    },
    "EURUSD": {
        Session.ASIAN: 0.3,
        Session.LONDON: 1.0,
        Session.NEW_YORK: 0.8,
        Session.OVERLAP: 1.1,
    },
    "GBPUSD": {
        Session.ASIAN: 0.2,
        Session.LONDON: 1.0,
        Session.NEW_YORK: 0.7,
        Session.OVERLAP: 1.0,
    },
    "USDJPY": {
        Session.ASIAN: 0.8,   # JPY active in Asian session
        Session.LONDON: 0.7,
        Session.NEW_YORK: 0.9,
        Session.OVERLAP: 0.8,
    },
}


class SessionFilter:
    """
    Determines current trading session and edge multiplier.

    Usage:
        sf = SessionFilter()
        if sf.is_active():
            mult = sf.get_edge_multiplier("XAUUSD")
    """

    def __init__(self, now: datetime | None = None):
        self._now = now or datetime.now(UTC)

    @property
    def current_session(self) -> Session:
        """Get current session based on UTC time."""
        t = self._now.time()

        # Check overlap first (highest priority)
        overlap_start, overlap_end = SESSION_TIMES[Session.OVERLAP]
        if overlap_start <= t < overlap_end:
            return Session.OVERLAP

        # Check each session
        for session in [Session.ASIAN, Session.LONDON, Session.NEW_YORK]:
            start, end = SESSION_TIMES[session]
            if start <= t < end:
                return session

        return Session.CLOSED

    def is_active(self) -> bool:
        """Check if market is currently open."""
        return self.current_session != Session.CLOSED

    def get_edge_multiplier(self, symbol: str = "XAUUSD") -> float:
        """
        Get edge multiplier for current session and symbol.

        Returns:
            0.0 - 1.2+ (higher = stronger edge)
        """
        session = self.current_session

        # Check symbol-specific bias first
        if symbol in SYMBOL_SESSION_BIAS:
            return SYMBOL_SESSION_BIAS[symbol].get(session, EDGE_MULTIPLIERS[session])

        return EDGE_MULTIPLIERS[session]

    def get_session_info(self) -> dict:
        """Get detailed session information."""
        session = self.current_session
        return {
            "session": session.value,
            "is_active": self.is_active(),
            "edge_multiplier": self.get_edge_multiplier(),
            "time_utc": self._now.strftime("%H:%M UTC"),
        }

    def should_trade(self, symbol: str = "XAUUSD", min_edge: float = 0.5) -> bool:
        """Check if we should trade this symbol right now."""
        if not self.is_active():
            return False
        return self.get_edge_multiplier(symbol) >= min_edge

    def get_next_session(self) -> dict:
        """Get information about the next session."""
        t = self._now.time()
        now_minutes = t.hour * 60 + t.minute

        sessions = [
            (Session.ASIAN, 0),
            (Session.LONDON, 480),    # 8:00
            (Session.OVERLAP, 780),   # 13:00
            (Session.NEW_YORK, 780),  # 13:00
            (Session.CLOSED, 1260),   # 21:00
        ]

        for session, start_min in sessions:
            if now_minutes < start_min:
                hours = (start_min - now_minutes) // 60
                mins = (start_min - now_minutes) % 60
                return {
                    "next_session": session.value,
                    "starts_in": f"{hours}h {mins}m",
                    "edge_multiplier": EDGE_MULTIPLIERS[session],
                }

        # Next is tomorrow's Asian session
        return {
            "next_session": Session.ASIAN.value,
            "starts_in": f"{24 - t.hour}h {60 - t.minute}m",
            "edge_multiplier": EDGE_MULTIPLIERS[Session.ASIAN],
        }
