"""Broker manager for the unified adapter hierarchy.

Provides failover and lifecycle management over canonical ``BrokerAdapter``
implementations. The legacy ``BrokerManager`` in ``execution/broker_adapter.py``
is deprecated.
"""

from __future__ import annotations

import logging

from ...core.config import QuantConfig, get_config
from ...core.exceptions import BrokerError
from .base import BrokerAdapter
from .mt5 import MT5Adapter
from .myfxbook import MyfxbookAdapter
from .paper import PaperAdapter

logger = logging.getLogger(__name__)


class BrokerManager:
    """Manages broker connections with primary/fallback failover.

    The manager is async at the boundary (initialize, health_check) because
    callers such as the FastAPI layer and ``OrderManager`` are async, but it
    delegates to the synchronous unified adapter interface internally.
    """

    def __init__(
        self,
        primary: BrokerAdapter | None = None,
        fallbacks: list[BrokerAdapter] | None = None,
    ) -> None:
        self.primary = primary
        self.fallbacks = list(fallbacks or [])
        self._active: BrokerAdapter | None = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: QuantConfig | None = None) -> BrokerManager:
        """Build a BrokerManager from QuantConfig defaults.

        The ``account_data_source`` field selects which adapter feeds account
        state. Myfxbook is read-only and refuses trading operations, so it is
        safe to use as a data source but will fail closed if live trading is
        attempted through it.
        """
        config = config or get_config()

        source = (config.account_data_source or "mt5").lower()  # type: ignore[attr-defined]

        if source == "myfxbook":
            primary: BrokerAdapter = MyfxbookAdapter(
                email=config.myfxbook_email,  # type: ignore[attr-defined]
                password=config.myfxbook_password,  # type: ignore[attr-defined]
            )
            fallbacks = []
            if config.live_trading_enabled:
                logger.warning(
                    "account_data_source=myfxbook is READ-ONLY; live trading via "
                    "MyfxbookAdapter will be refused (fail-closed). Keep source=mt5 "
                    "for live execution."
                )
        elif config.live_trading_enabled:
            primary = MT5Adapter(
                login=config.mt5_login,
                password=config.mt5_password,
                server=config.mt5_server,
                timeout=config.mt5_timeout_ms,
            )
            fallbacks = [PaperAdapter()]
        else:
            primary = PaperAdapter()
            fallbacks = []

        return cls(primary=primary, fallbacks=fallbacks)  # type: ignore[arg-type]

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
                        try:  # noqa: SIM105
                            previous.disconnect()
                        except Exception:
                            pass
                    logger.info("BrokerManager failover to %s", fallback.name)
                    return True
            except Exception as exc:
                logger.warning("BrokerManager failover to %s failed: %s", fallback.name, exc)
        return False
