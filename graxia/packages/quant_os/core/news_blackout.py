"""
News Blackout — Block trades during high-impact news windows.

When a HIGH/CRISIS news event is detected, block new trades for
`blackout_minutes` to avoid slippage and fakeouts.

Usage:
  from core.news_blackout import NewsBlackout
  nb = NewsBlackout(blackout_minutes=60)
  nb.trigger("CRISIS", "Fed emergency cut")
  if nb.is_blocked():
      print(f"Blocked for {nb.remaining_seconds()}s")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BlackoutEvent:
    """Record of a blackout trigger."""

    severity: str
    headline: str
    triggered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class NewsBlackout:
    """
    Block trading during news events.

    Rules:
      - CRISIS: blackout 120 minutes
      - HIGH_UNCERTAINTY: blackout 60 minutes
      - NORMAL: no blackout
    """

    SEVERITY_MINUTES = {
        "CRISIS": 120,
        "HIGH_UNCERTAINTY": 60,
        "HIGH": 60,
        "NORMAL": 0,
        "LOW": 0,
    }

    def __init__(self, blackout_minutes: int = 60):
        self._default_minutes = blackout_minutes
        self._active: list[BlackoutEvent] = []

    def trigger(self, severity: str, headline: str = "") -> BlackoutEvent:
        """Trigger a news blackout."""
        minutes = self.SEVERITY_MINUTES.get(severity, self._default_minutes)
        if minutes <= 0:
            return BlackoutEvent(severity=severity, headline=headline)

        now = datetime.now(UTC)
        event = BlackoutEvent(
            severity=severity,
            headline=headline,
            triggered_at=now,
            expires_at=now + timedelta(minutes=minutes),
        )
        self._active.append(event)
        logger.info("news_blackout.triggered", severity=severity, minutes=minutes, headline=headline[:80])
        return event

    def is_blocked(self) -> bool:
        """Check if trading is currently blocked."""
        now = datetime.now(UTC)
        self._cleanup_expired()
        return len(self._active) > 0

    def remaining_seconds(self) -> float:
        """Seconds until blackout expires."""
        if not self._active:
            return 0.0
        now = datetime.now(UTC)
        latest_expiry = max(e.expires_at for e in self._active)
        remaining = (latest_expiry - now).total_seconds()
        return max(0.0, remaining)

    def get_active(self) -> list[BlackoutEvent]:
        self._cleanup_expired()
        return list(self._active)

    def _cleanup_expired(self):
        now = datetime.now(UTC)
        self._active = [e for e in self._active if e.expires_at > now]

    def clear(self):
        """Manually clear all blackouts."""
        self._active.clear()

    def get_status(self) -> dict:
        self._cleanup_expired()
        if not self._active:
            return {"blocked": False, "remaining_seconds": 0}

        latest = max(self._active, key=lambda e: e.expires_at)
        return {
            "blocked": True,
            "remaining_seconds": round(self.remaining_seconds()),
            "active_count": len(self._active),
            "latest_severity": latest.severity,
            "latest_headline": latest.headline[:80],
        }
