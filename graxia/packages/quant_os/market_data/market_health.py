"""
Market Health State Machine for Quant OS

Determines overall market health by evaluating multiple subsystem inputs.
Only HEALTHY state permits new order intents.

Priority order (highest first):
1. DISCONNECTED (feed health)
2. MARKET_CLOSED (session guard)
3. STALE_FEED (tick age)
4. WIDE_SPREAD (spread monitor)
5. CLOCK_DRIFT (clock guard)
6. MISSING_TICK_GAP (tick recorder)
7. OUT_OF_ORDER_DATA (tick recorder)
8. CONTRACT_CHANGED (contract spec)
9. If none → HEALTHY

CRITICAL CONSTRAINT: This module is READ-ONLY. No order submission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class MarketHealthState(str, Enum):
    """Market health states. Only HEALTHY allows new orders."""
    HEALTHY = "HEALTHY"
    STALE_FEED = "STALE_FEED"
    WIDE_SPREAD = "WIDE_SPREAD"
    CLOCK_DRIFT = "CLOCK_DRIFT"
    OUT_OF_ORDER_DATA = "OUT_OF_ORDER_DATA"
    MISSING_TICK_GAP = "MISSING_TICK_GAP"
    MARKET_CLOSED = "MARKET_CLOSED"
    DISCONNECTED = "DISCONNECTED"
    CONTRACT_CHANGED = "CONTRACT_CHANGED"
    UNKNOWN = "UNKNOWN"


@dataclass
class MarketHealthResult:
    """
    Result of a market health evaluation.

    Attributes:
        state: The determined health state.
        eligible_for_new_order: True only when state == HEALTHY.
        reason_codes: List of specific reason codes contributing to the state.
        details: Additional context about the evaluation.
        timestamp_utc: When the evaluation was performed.
    """
    state: MarketHealthState
    eligible_for_new_order: bool
    reason_codes: list[str]
    details: dict[str, Any]
    timestamp_utc: datetime

    def summary(self) -> str:
        eligibility = "ELIGIBLE" if self.eligible_for_new_order else "BLOCKED"
        reasons = ", ".join(self.reason_codes) if self.reason_codes else "none"
        return f"Market {self.state.value} [{eligibility}]: {reasons}"


@dataclass
class MarketHealthConfig:
    """Configuration thresholds for health evaluation."""
    max_tick_age_seconds: float = 3.0
    max_clock_drift_ms: float = 500.0
    spread_baseline_window: int = 500
    reject_spread_multiplier_above: float = 2.0
    min_valid_bid_ask_distance_points: int = 1
    max_missing_tick_gap_seconds: float = 30.0


class MarketHealthMachine:
    """
    Central market health evaluation state machine.

    Aggregates signals from all market data subsystems and produces
    a single health verdict. Only HEALTHY permits new order intents.

    Usage:
        machine = MarketHealthMachine("XAUUSD")
        result = machine.evaluate(
            feed_health=feed_state,
            spread_state=spread_state,
            clock_state=clock_state,
            session_state=session_result,
        )
        if result.eligible_for_new_order:
            # proceed with order intent (READ-ONLY phase: log only)
    """

    def __init__(self, symbol: str, config: Optional[dict] = None):
        self._symbol = symbol
        self._config_dict = config or self._default_config()
        self._last_state = MarketHealthState.UNKNOWN
        self._last_result: Optional[MarketHealthResult] = None

    def _default_config(self) -> dict:
        return {
            "max_tick_age_seconds": 3.0,
            "max_clock_drift_ms": 500.0,
            "spread_baseline_window": 500,
            "reject_spread_multiplier_above": 2.0,
            "min_valid_bid_ask_distance_points": 1,
            "max_missing_tick_gap_seconds": 30.0,
        }

    def evaluate(
        self,
        feed_health: Any = None,
        spread_state: Any = None,
        clock_state: Any = Any,
        session_state: Any = None,
        tick_gap_info: Any = None,
        contract_changed: bool = False,
    ) -> MarketHealthResult:
        """
        Evaluate all health inputs and determine overall market health.

        New order intents are eligible only in HEALTHY state.

        Args:
            feed_health: FeedHealthState from FeedHealthMonitor
            spread_state: SpreadState from SpreadMonitor
            clock_state: ClockState from ClockGuard
            session_state: SessionResult from MarketSessionGuard
            tick_gap_info: TickRecorderState or list of gaps
            contract_changed: Whether contract spec has changed

        Returns:
            MarketHealthResult with state, eligibility, and diagnostics.
        """
        reason_codes: list[str] = []
        details: dict[str, Any] = {}

        # Priority 1: DISCONNECTED
        if self._check_disconnected(feed_health):
            reason_codes.append("FEED_DISCONNECTED")
            details["feed_health"] = self._extract_detail(feed_health, "level")

        # Priority 2: MARKET_CLOSED
        if self._check_market_closed(session_state):
            reason_codes.append("MARKET_CLOSED")
            details["session_state"] = self._extract_detail(session_state, "state")

        # Priority 3: STALE_FEED
        if self._check_stale_feed(feed_health):
            reason_codes.append("STALE_FEED")
            details["tick_age_seconds"] = self._extract_detail(
                feed_health, "last_tick_age_seconds"
            )

        # Priority 4: WIDE_SPREAD
        if self._check_wide_spread(spread_state):
            reason_codes.append("WIDE_SPREAD")
            details["spread"] = self._extract_detail(spread_state, "current_spread")

        # Priority 5: CLOCK_DRIFT
        if self._check_clock_drift(clock_state):
            reason_codes.append("CLOCK_DRIFT")
            details["drift_ms"] = self._extract_detail(clock_state, "drift_ms")

        # Priority 6: MISSING_TICK_GAP
        if self._check_tick_gap(tick_gap_info):
            reason_codes.append("MISSING_TICK_GAP")
            details["gaps"] = self._extract_detail(tick_gap_info, "gaps_detected")

        # Priority 7: OUT_OF_ORDER_DATA
        if self._check_out_of_order(tick_gap_info):
            reason_codes.append("OUT_OF_ORDER_DATA")
            details["out_of_order"] = self._extract_detail(
                tick_gap_info, "out_of_order_count"
            )

        # Priority 8: CONTRACT_CHANGED
        if contract_changed:
            reason_codes.append("CONTRACT_CHANGED")

        # Determine state
        if reason_codes:
            state = self._reason_to_state(reason_codes[0])
        else:
            state = MarketHealthState.HEALTHY

        eligible = state == MarketHealthState.HEALTHY

        result = MarketHealthResult(
            state=state,
            eligible_for_new_order=eligible,
            reason_codes=reason_codes,
            details=details,
            timestamp_utc=datetime.now(timezone.utc),
        )

        self._last_state = state
        self._last_result = result
        return result

    def is_eligible_for_order(self) -> bool:
        """Check if the last evaluation permits new orders."""
        return self._last_state == MarketHealthState.HEALTHY

    def get_state(self) -> MarketHealthState:
        """Return the last evaluated state."""
        return self._last_state

    def get_last_result(self) -> Optional[MarketHealthResult]:
        """Return the full last evaluation result."""
        return self._last_result

    # --- Check methods ---

    def _check_disconnected(self, feed_health: Any) -> bool:
        if feed_health is None:
            return True  # No feed = disconnected
        level = getattr(feed_health, "level", None)
        if hasattr(level, "value"):
            level = level.value
        return level == "DISCONNECTED"

    def _check_market_closed(self, session_state: Any) -> bool:
        if session_state is None:
            return False  # No session check = assume open (fail-open for session)
        is_open = getattr(session_state, "is_open", True)
        return is_open is False

    def _check_stale_feed(self, feed_health: Any) -> bool:
        if feed_health is None:
            return False
        age = getattr(feed_health, "last_tick_age_seconds", None)
        if age is None:
            return False
        max_age = getattr(feed_health, "max_tick_age_seconds", 3.0)
        return age > max_age

    def _check_wide_spread(self, spread_state: Any) -> bool:
        if spread_state is None:
            return False
        return getattr(spread_state, "is_wide", False) is True

    def _check_clock_drift(self, clock_state: Any) -> bool:
        if clock_state is None:
            return False
        is_drifted = getattr(clock_state, "is_drifted", False)
        return is_drifted is True

    def _check_tick_gap(self, tick_gap_info: Any) -> bool:
        if tick_gap_info is None:
            return False
        gaps = getattr(tick_gap_info, "gaps_detected", 0)
        return gaps > 0

    def _check_out_of_order(self, tick_gap_info: Any) -> bool:
        if tick_gap_info is None:
            return False
        ooo = getattr(tick_gap_info, "out_of_order_count", 0)
        return ooo > 0

    def _reason_to_state(self, reason: str) -> MarketHealthState:
        """Map a reason code to the corresponding health state."""
        mapping = {
            "FEED_DISCONNECTED": MarketHealthState.DISCONNECTED,
            "MARKET_CLOSED": MarketHealthState.MARKET_CLOSED,
            "STALE_FEED": MarketHealthState.STALE_FEED,
            "WIDE_SPREAD": MarketHealthState.WIDE_SPREAD,
            "CLOCK_DRIFT": MarketHealthState.CLOCK_DRIFT,
            "MISSING_TICK_GAP": MarketHealthState.MISSING_TICK_GAP,
            "OUT_OF_ORDER_DATA": MarketHealthState.OUT_OF_ORDER_DATA,
            "CONTRACT_CHANGED": MarketHealthState.CONTRACT_CHANGED,
        }
        return mapping.get(reason, MarketHealthState.UNKNOWN)

    def _extract_detail(self, obj: Any, attr: str) -> Any:
        """Safely extract an attribute from an object."""
        if obj is None:
            return None
        val = getattr(obj, attr, None)
        if hasattr(val, "value"):
            return val.value
        return val
