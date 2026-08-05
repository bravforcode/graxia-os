"""Regression test: AutonomousOrchestrator reloads the shared circuit breaker
from disk before every snapshot check.

A trip raised through API entry points (webhook / signal_service build a
fresh per-call breaker) must be visible to the long-running orchestrator,
which constructs its breaker once at startup.  The orchestrator therefore
calls ``reload()`` before reading ``is_blocked`` on each snapshot.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.autonomous import orchestrator as orch_mod


class _SpyBreaker:
    """Records the order of reload() / is_blocked access."""

    def __init__(self, *args, **kwargs):
        self.events: list[str] = []
        self._blocked = True

    def reload(self) -> None:
        self.events.append("reload")

    @property
    def is_blocked(self) -> bool:
        self.events.append("is_blocked")
        return self._blocked

    @property
    def reason(self) -> str:
        return "test"


@pytest.mark.asyncio
async def test_orchestrator_reloads_breaker_before_blocked_check(monkeypatch):
    """_on_snapshot reloads shared state BEFORE reading is_blocked."""
    monkeypatch.setattr(orch_mod, "CircuitBreaker", _SpyBreaker)
    monkeypatch.setattr(orch_mod, "TradeStore", lambda: MagicMock())

    orch = orch_mod.AutonomousOrchestrator(
        kill_switch=MagicMock(),
        risk_engine=MagicMock(),
        decision_engine=MagicMock(),
        order_executor=MagicMock(),
        chart_monitor=MagicMock(),
        notifier=MagicMock(),
    )
    orch._running = True  # _on_snapshot returns early unless running

    snap = SimpleNamespace(symbol="XAUUSD")
    await orch._on_snapshot(snap)

    assert orch._circuit_breaker.events == ["reload", "is_blocked"]
