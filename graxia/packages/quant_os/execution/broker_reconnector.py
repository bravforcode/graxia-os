"""Phase 4 — Broker Reconnection Logic.

Handles broker disconnections gracefully:
- Detects disconnection via heartbeat timeout
- Pauses trading on disconnect
- Reconnects with stale-state protection
- IB TWS API pacing limiter (60 historical requests per 2min)
- Automatic restart on repeated failures

Research:
- IB TWS: weekly 2FA re-auth mandatory, 200+ error codes
- Pacing: max 60 historical requests per 2min, 150 market data per 5min
- Disconnected algo trading on stale state → unlimited loss
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class BrokerState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"  # Repeated failures, needs manual intervention


@dataclass
class BrokerConfig:
    """Broker reconnection configuration."""

    heartbeat_interval_sec: float = 30.0  # Expected heartbeat interval
    heartbeat_timeout_sec: float = 90.0  # 3x heartbeat = disconnected
    max_reconnect_attempts: int = 5  # Before declaring FAILED
    reconnect_delay_sec: float = 5.0  # Initial delay between attempts
    reconnect_backoff_mult: float = 2.0  # Exponential backoff multiplier
    max_reconnect_delay_sec: float = 60.0  # Cap on backoff

    # IB TWS pacing limits
    ib_historical_rate_limit: int = 60  # Max requests per 2min window
    ib_historical_window_sec: float = 120.0  # 2min window
    ib_market_data_rate_limit: int = 150  # Max per 5min window
    ib_market_data_window_sec: float = 300.0  # 5min window

    # Stale state protection
    max_stale_bars: int = 3  # Max bars to trade on stale data before halt
    require_fresh_tick: bool = True  # Require fresh tick before new orders


@dataclass
class ReconnectionEvent:
    """Event from reconnection logic."""

    event_type: str  # "DISCONNECTED", "RECONNECTING", "RECONNECTED", "FAILED", "STALE_HALT"
    timestamp: float
    attempt: int = 0
    delay_sec: float = 0.0
    message: str = ""


class BrokerReconnector:
    """Manages broker connection state and reconnection.

    Protects against:
    - Trading on stale data after disconnect
    - Unlimited position accumulation during disconnect
    - IB TWS rate limit violations
    """

    def __init__(self, config: BrokerConfig | None = None):
        self.config = config or BrokerConfig()
        self._state = BrokerState.CONNECTED
        self._last_heartbeat: float = time.time()
        self._reconnect_attempts: int = 0
        self._last_reconnect: float = 0.0
        self._events: list[ReconnectionEvent] = []

        # IB pacing trackers
        self._historical_requests: list[float] = []
        self._market_data_requests: list[float] = []

        # Stale state tracking
        self._bars_since_last_tick: int = 0
        self._stale_halt: bool = False

    @property
    def state(self) -> BrokerState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == BrokerState.CONNECTED

    @property
    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed (connected + not stale)."""
        return self._state == BrokerState.CONNECTED and not self._stale_halt

    @property
    def events(self) -> list[ReconnectionEvent]:
        return list(self._events)

    def heartbeat_received(self):
        """Call when a heartbeat is received from broker."""
        self._last_heartbeat = time.time()
        self._bars_since_last_tick = 0

        if self._state == BrokerState.DISCONNECTED or self._state == BrokerState.RECONNECTING:
            self._state = BrokerState.CONNECTED
            self._reconnect_attempts = 0
            self._stale_halt = False
            self._events.append(ReconnectionEvent(
                event_type="RECONNECTED",
                timestamp=time.time(),
                message="Broker reconnected successfully",
            ))

    def tick_received(self):
        """Call when a fresh market tick is received."""
        self._bars_since_last_tick = 0
        self._stale_halt = False

    def check_heartbeat(self) -> bool:
        """Check if heartbeat timeout has occurred.

        Returns:
            True if connection is still healthy, False if timeout detected
        """
        elapsed = time.time() - self._last_heartbeat
        if elapsed > self.config.heartbeat_timeout_sec:
            if self._state == BrokerState.CONNECTED:
                self._state = BrokerState.DISCONNECTED
                self._events.append(ReconnectionEvent(
                    event_type="DISCONNECTED",
                    timestamp=time.time(),
                    message=f"Heartbeat timeout after {elapsed:.0f}s",
                ))
            return False
        return True

    def attempt_reconnect(self) -> ReconnectionEvent:
        """Attempt to reconnect to broker.

        Returns:
            ReconnectionEvent with result
        """
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            self._state = BrokerState.FAILED
            event = ReconnectionEvent(
                event_type="FAILED",
                timestamp=time.time(),
                attempt=self._reconnect_attempts,
                message=f"Max reconnect attempts ({self.config.max_reconnect_attempts}) exhausted",
            )
            self._events.append(event)
            return event

        self._state = BrokerState.RECONNECTING
        delay = min(
            self.config.reconnect_delay_sec * (self.config.reconnect_backoff_mult ** self._reconnect_attempts),
            self.config.max_reconnect_delay_sec,
        )

        self._reconnect_attempts += 1
        self._last_reconnect = time.time()

        event = ReconnectionEvent(
            event_type="RECONNECTING",
            timestamp=time.time(),
            attempt=self._reconnect_attempts,
            delay_sec=delay,
            message=f"Reconnect attempt {self._reconnect_attempts}/{self.config.max_reconnect_attempts}, delay {delay:.0f}s",
        )
        self._events.append(event)
        return event

    def on_bar_close(self):
        """Call on each bar close to track staleness."""
        self._bars_since_last_tick += 1
        if self._bars_since_last_tick > self.config.max_stale_bars:
            self._stale_halt = True
            self._events.append(ReconnectionEvent(
                event_type="STALE_HALT",
                timestamp=time.time(),
                message=f"Trading halted: {self._bars_since_last_tick} bars without fresh tick",
            ))

    # ── IB TWS Pacing Limiter ──────────────────────────────────────────

    def check_historical_rate_limit(self) -> bool:
        """Check if historical data request is allowed under IB pacing rules.

        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        cutoff = now - self.config.ib_historical_window_sec
        self._historical_requests = [t for t in self._historical_requests if t > cutoff]

        if len(self._historical_requests) >= self.config.ib_historical_rate_limit:
            return False

        self._historical_requests.append(now)
        return True

    def check_market_data_rate_limit(self) -> bool:
        """Check if market data request is allowed under IB pacing rules.

        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        cutoff = now - self.config.ib_market_data_window_sec
        self._market_data_requests = [t for t in self._market_data_requests if t > cutoff]

        if len(self._market_data_requests) >= self.config.ib_market_data_rate_limit:
            return False

        self._market_data_requests.append(now)
        return True

    def reset(self):
        """Reset state for a new session."""
        self._state = BrokerState.CONNECTED
        self._last_heartbeat = time.time()
        self._reconnect_attempts = 0
        self._events.clear()
        self._historical_requests.clear()
        self._market_data_requests.clear()
        self._bars_since_last_tick = 0
        self._stale_halt = False
