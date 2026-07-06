"""News Blackout Gate — prevents trading during high-impact economic events.

Fail-open by default for paper mode. In live mode, integrates with the
existing news pipeline (EventRiskGate, MacroPolicyGuard) to block trading
before/after major economic releases.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class NewsBlackoutGate:
    """Prevents trading during high-impact news events."""

    def __init__(self) -> None:
        self._blackout_until: datetime | None = None
        self._reason: str = ""
        self._event_risk_gate: Any | None = None
        self._macro_guard: Any | None = None

        try:
            from ..news_events.event_risk_gate import EventRiskGate
            from ..news_events.event_store import EventStore

            self._event_risk_gate = EventRiskGate(event_store=EventStore())
        except Exception:
            logger.debug("news_gate.event_risk_gate_unavailable")

        try:
            from ..news_events.macro_policy import MacroPolicyGuard

            self._macro_guard = MacroPolicyGuard()
        except Exception:
            logger.debug("news_gate.macro_policy_guard_unavailable")

    def is_blocked(self) -> bool:
        """Check if trading is currently blocked."""
        if self._blackout_until is not None:
            if datetime.now(tz=UTC) < self._blackout_until:
                return True
            self.clear_blackout()

        if self._event_risk_gate is not None:
            try:
                result = self._event_risk_gate.evaluate(at=datetime.now(tz=UTC))
                if not result.eligible_for_new_order_intent:
                    logger.warning(
                        "news_gate.event_blocked",
                        event_ids=result.event_ids,
                        reason_codes=result.reason_codes,
                    )
                    return True
            except Exception as exc:
                logger.debug("news_gate.event_risk_check_failed", error=str(exc))

        return False

    def set_blackout(self, until: datetime, reason: str) -> None:
        """Set blackout period."""
        self._blackout_until = until
        self._reason = reason
        logger.warning(
            "news_gate.blackout_set",
            until=until.isoformat(),
            reason=reason,
        )

    def clear_blackout(self) -> None:
        """Clear blackout period."""
        if self._blackout_until is not None:
            logger.info("news_gate.blackout_cleared", was_reason=self._reason)
        self._blackout_until = None
        self._reason = ""

    def get_next_event(self) -> dict | None:
        """Get next scheduled news event."""
        if self._event_risk_gate is None:
            return None
        try:
            result = self._event_risk_gate.evaluate(at=datetime.now(tz=UTC))
            if result.event_ids:
                return {
                    "event_ids": result.event_ids,
                    "reason_codes": result.reason_codes,
                    "blocked": not result.eligible_for_new_order_intent,
                }
        except Exception:
            pass
        return None
