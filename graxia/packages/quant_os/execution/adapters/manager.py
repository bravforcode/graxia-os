"""Broker manager for the unified adapter hierarchy.

Provides failover and lifecycle management over canonical ``BrokerAdapter``
implementations. The legacy ``BrokerManager`` in ``execution/broker_adapter.py``
is deprecated.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import BrokerAdapter
from .mt5 import MT5Adapter
from .paper import PaperAdapter
from ...core.config import QuantConfig, get_config
from ...core.exceptions import BrokerError

logger = logging.getLogger(__name__)


class BrokerManager:
    """Manages broker connections with primary/fallback failover.

    The manager is async at the boundary (initialize, health_check) because
    callers such as the FastAPI layer and ``OrderManager`` are async, but it
    delegates to the synchronous unified adapter interface internally.
    """

    def __init__(
        self,
        primary: Optional[BrokerAdapter] = None,
        fallbacks: Optional[list[BrokerAdapter]] = None,
    ) -> None:
        self.primary = primary
        self.fallbacks = list(fallbacks or [])
        self._active: Optional[BrokerAdapter] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: Optional[QuantConfig] = None) -> "BrokerManager":
        """Build a BrokerManager from QuantConfig defaults."""
        config = config or get_config()

        if config.live_trading_enabled:
            primary: BrokerAdapter = MT5Adapter(
                login=config.mt5_login,
                password=config.mt5_password,
                server=config.mt5_server,
                timeout=config.mt5_timeout_ms,
            )
            fallbacks = [PaperAdapter()]
        else:
            primary = PaperAdapter()
            fallbacks = []

        return cls(primary=primary, fallbacks=fallbacks)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """Connect to the primary broker or fall back to alternatives."""
        for adapter in [self.primary] + self.fallbacks:
            if adapter is None:
                continue
            try:
                if adapter.connect():
                    self._active = adapter
                    logger.info("BrokerManager active: %s", adapter.name)
                    return True
            except Exception as exc:
                logger.warning("BrokerManager failed to connect %s: %s", adapter.name, exc)

        return False

    @property
    def active(self) -> BrokerAdapter:
        """Return the currently active broker adapter."""
        if self._active is None:
            raise BrokerError("No active broker connection")
        return self._active

    async def health_check(self) -> bool:
        """Check whether the active broker is healthy, failing over if needed."""
        try:
            self.active.get_account_info()
            return True
        except Exception as exc:
            logger.warning("BrokerManager health_check failed: %s", exc)
            return await self._failover()

    async def _failover(self) -> bool:
        """Attempt to promote a fallback adapter."""
        for fallback in self.fallbacks:
            try:
                if fallback.connect():
                    previous = self._active
                    self._active = fallback
                    if previous is not None:
                        try:
                            previous.disconnect()
                        except Exception:
                            pass
                    logger.info("BrokerManager failover to %s", fallback.name)
                    return True
            except Exception as exc:
                logger.warning("BrokerManager failover to %s failed: %s", fallback.name, exc)
        return False
