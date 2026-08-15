"""Tests for RealtimeReconciler — wires PositionReconciler to live trading loop."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from graxia.packages.quant_os.core.events import BarEvent
from graxia.packages.quant_os.core.position_manager import Position
from graxia.packages.quant_os.execution.adapters.base import BrokerAdapter
from graxia.packages.quant_os.execution.position_reconciler import (
    PositionReconciler,
    ReconciliationConfig,
)
from graxia.packages.quant_os.execution.realtime_reconciler import RealtimeReconciler
from graxia.packages.quant_os.monitoring.alerts import AlertManager

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def reconciler():
    """Standard PositionReconciler with auto-close enabled."""
    config = ReconciliationConfig(
        tolerance_pct=0.01,
        max_position_drift=0,
        reconciliation_interval_bars=1,
        auto_close_drift=True,
    )
    return PositionReconciler(config)


@pytest.fixture
def broker_adapter():
    """Mock BrokerAdapter returning no positions by default."""
    adapter = MagicMock(spec=BrokerAdapter)
    adapter.get_positions.return_value = []
    adapter.close_position.return_value = MagicMock(status="FILLED")
    return adapter


@pytest.fixture
def alert_manager():
    """Mock AlertManager with async send_alert."""
    manager = MagicMock(spec=AlertManager)
    manager.send_alert = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_engine():
    """Mock engine (PositionManager) returning empty positions."""
    engine = MagicMock()
    engine.get_positions.return_value = {}
    return engine


@pytest.fixture
def bar():
    """Standard BarEvent."""
    return BarEvent(
        symbol="XAUUSD",
        timeframe="M15",
        open=2650.0,
        high=2655.0,
        low=2648.0,
        close=2652.0,
        volume=100.0,
        bar_index=1,
    )


# ── Tests ─────────────────────────────────────────────────────────────


def test_realtime_reconciler_runs_every_n_bars(reconciler, broker_adapter, alert_manager, mock_engine, bar):
    """Reconciliation runs exactly every interval_bars bars."""
    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        engine=mock_engine,
        interval_bars=3,
    )
    rt.start()

    # Bars 1, 2: no reconciliation
    for i in range(1, 3):
        b = BarEvent(
            symbol="XAUUSD",
            timeframe="M15",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=100.0,
            bar_index=i,
        )
        result = rt.on_bar(b)
        assert result is None, f"Bar {i} should not trigger reconciliation"

    # Bar 3: reconciliation triggers
    b3 = BarEvent(
        symbol="XAUUSD", timeframe="M15", open=2650.0, high=2655.0, low=2648.0, close=2652.0, volume=100.0, bar_index=3
    )
    result = rt.on_bar(b3)
    assert result is not None, "Bar 3 should trigger reconciliation"
    assert result.matched is True  # Both empty → matched

    # Bar 4, 5: no reconciliation
    for i in range(4, 6):
        b = BarEvent(
            symbol="XAUUSD",
            timeframe="M15",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=100.0,
            bar_index=i,
        )
        result = rt.on_bar(b)
        assert result is None

    # Bar 6: reconciliation triggers again
    b6 = BarEvent(
        symbol="XAUUSD", timeframe="M15", open=2650.0, high=2655.0, low=2648.0, close=2652.0, volume=100.0, bar_index=6
    )
    result = rt.on_bar(b6)
    assert result is not None

    rt.stop()


def test_realtime_reconciler_skips_when_interval_not_reached(reconciler, broker_adapter, alert_manager, bar):
    """Reconciliation skipped when bar count < interval_bars."""
    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        interval_bars=5,
    )
    rt.start()

    # First 4 bars should not trigger
    for i in range(1, 5):
        b = BarEvent(
            symbol="XAUUSD",
            timeframe="M15",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=100.0,
            bar_index=i,
        )
        assert rt.on_bar(b) is None

    # 5th bar triggers
    b5 = BarEvent(
        symbol="XAUUSD", timeframe="M15", open=2650.0, high=2655.0, low=2648.0, close=2652.0, volume=100.0, bar_index=5
    )
    assert rt.on_bar(b5) is not None

    rt.stop()


def test_realtime_reconciler_drift_sends_alert(reconciler, broker_adapter, alert_manager, bar):
    """Drift detection sends alert via AlertManager."""
    # Internal has a position, broker has none → drift
    mock_engine = MagicMock()
    mock_engine.get_positions.return_value = {
        "XAUUSD:BUY": Position(
            symbol="XAUUSD",
            side="BUY",
            quantity=1.0,
            entry_price=2650.0,
        ),
    }

    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        engine=mock_engine,
        interval_bars=1,
    )
    rt.start()

    # Need a running event loop for async alert
    async def _run():
        result = rt.on_bar(bar)
        assert result is not None
        assert result.drift_detected is True
        assert result.action_required == "CLOSE_DRIFT"
        # Alert should have been sent
        alert_manager.send_alert.assert_called_once()
        call_args = alert_manager.send_alert.call_args
        alert = call_args[0][0] if call_args[0] else call_args[1].get("alert") or call_args[1].get("args", [None])[0]
        # Just verify it was called — the Alert object is positional
        assert alert_manager.send_alert.called

    asyncio.run(_run())
    rt.stop()


def test_realtime_reconciler_broker_error_handled(reconciler, alert_manager, bar):
    """Broker connection failure is handled gracefully (returns empty list)."""
    broker_adapter = MagicMock(spec=BrokerAdapter)
    broker_adapter.get_positions.side_effect = ConnectionError("MT5 disconnected")

    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        interval_bars=1,
    )
    rt.start()

    # Should not raise — error handled internally
    result = rt.on_bar(bar)
    assert result is not None
    # With empty broker positions, internal (also empty) matches
    assert result.matched is True
    assert result.position_count_broker == 0

    rt.stop()


def test_realtime_reconciler_start_stop(reconciler, broker_adapter, alert_manager):
    """Start/stop lifecycle works correctly."""
    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        interval_bars=1,
    )

    assert rt.is_running is False

    rt.start()
    assert rt.is_running is True

    rt.stop()
    assert rt.is_running is False


def test_realtime_reconciler_noop_when_stopped(reconciler, broker_adapter, alert_manager, bar):
    """on_bar returns None when reconciler is stopped."""
    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        interval_bars=1,
    )
    # Not started → should be no-op
    assert rt.on_bar(bar) is None


def test_realtime_reconciler_thread_safety(reconciler, broker_adapter, alert_manager):
    """Multiple threads calling on_bar concurrently is safe."""
    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        interval_bars=1,
    )
    rt.start()

    errors = []

    def _worker(n: int):
        try:
            for i in range(50):
                bar = BarEvent(
                    symbol="XAUUSD",
                    timeframe="M15",
                    open=2650.0,
                    high=2655.0,
                    low=2648.0,
                    close=2652.0,
                    volume=100.0,
                    bar_index=n * 100 + i,
                )
                rt.on_bar(bar)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=_worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread safety errors: {errors}"
    rt.stop()


def test_realtime_reconciler_reconciliation_log(reconciler, broker_adapter, alert_manager, bar):
    """Reconciliation results are logged for audit trail."""
    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        interval_bars=1,
    )
    rt.start()

    rt.on_bar(bar)
    assert len(rt._reconciliation_log) == 1
    assert rt._reconciliation_log[0].matched is True

    rt.stop()


def test_realtime_reconciler_drift_with_qty_mismatch(reconciler, broker_adapter, alert_manager):
    """Quantity mismatch between internal and broker triggers drift."""
    # Internal: 1.0 lot, Broker: 0.5 lot → mismatch
    mock_engine = MagicMock()
    mock_engine.get_positions.return_value = {
        "XAUUSD:BUY": Position(symbol="XAUUSD", side="BUY", quantity=1.0, entry_price=2650.0),
    }
    broker_adapter.get_positions.return_value = [
        {"symbol": "XAUUSD", "side": "BUY", "volume": 0.5, "avg_price": 2650.0},
    ]

    rt = RealtimeReconciler(
        reconciler=reconciler,
        broker_adapter=broker_adapter,
        alert_manager=alert_manager,
        engine=mock_engine,
        interval_bars=1,
    )
    rt.start()

    bar = BarEvent(
        symbol="XAUUSD", timeframe="M15", open=2650.0, high=2655.0, low=2648.0, close=2652.0, volume=100.0, bar_index=1
    )

    async def _run():
        result = rt.on_bar(bar)
        assert result is not None
        assert result.drift_detected is True
        assert result.matched is False
        assert len(result.mismatches) > 0
        assert result.mismatches[0]["type"] == "QTY_MISMATCH"

    asyncio.run(_run())
    rt.stop()
