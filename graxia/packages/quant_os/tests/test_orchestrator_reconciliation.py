"""Regression tests for Phase 0 item 5: reconciliation-driven kill-switch trips.

core/orchestrator.py::_sync_live_market_state runs PositionReconciler every
sync cycle. A CRITICAL discrepancy (e.g. a side mismatch, or a qty mismatch too
large to auto-fix) must trip the kill switch immediately. Repeated
reconciliation-cycle exceptions (broker/API failures) must trip the kill switch
after RECONCILIATION_FAIL_THRESHOLD (3) consecutive failures, and a single
successful cycle must reset that counter so failures don't accumulate across
healthy cycles.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from graxia.packages.quant_os.core.config import QuantConfig
from graxia.packages.quant_os.core.events import KillSwitchEvent
from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator

MT5_GATEWAY = "graxia.packages.quant_os.broker.mt5_gateway"
ACCOUNT_INFO = {"equity": 1000.0, "balance": 1000.0, "margin_level": 100.0}


def _make_orchestrator() -> TradingOrchestrator:
    orch = TradingOrchestrator(config=QuantConfig())
    orch.bus.subscribe(KillSwitchEvent, orch.trading_loop.on_kill_switch)
    return orch


def _run_sync_cycle(orch: TradingOrchestrator) -> None:
    asyncio.run(orch._sync_live_market_state())


def _stub_position_manager(orch: TradingOrchestrator, positions: dict) -> None:
    orch._position_manager.get_positions = lambda: positions
    orch._position_manager.sync_account_state = lambda **_: None
    orch._position_manager.update_prices = lambda *_: None


class TestReconciliationCriticalDiscrepancy:
    def test_side_mismatch_trips_kill_switch(self):
        """A CRITICAL (side-mismatch) discrepancy must trip the kill switch."""
        orch = _make_orchestrator()
        _stub_position_manager(
            orch,
            {"EURUSD:BUY": SimpleNamespace(symbol="EURUSD", side="BUY", quantity=1.0, entry_price=1.1000)},
        )

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_current_tick", return_value={"bid": 1.1000}),
            patch(
                f"{MT5_GATEWAY}.get_positions",
                # type=1 -> broker side SELL, vs internal BUY -> SIDE_MISMATCH -> CRITICAL
                return_value=[{"symbol": "EURUSD", "type": 1, "volume": 1.0, "price_open": 1.1000}],
            ),
        ):
            _run_sync_cycle(orch)

        assert orch.trading_loop.get_stats()["kill_switch_active"] is True

    def test_warning_discrepancy_does_not_trip_kill_switch(self):
        """An auto-fixable qty mismatch (WARNING) must NOT trip the kill switch."""
        orch = _make_orchestrator()
        _stub_position_manager(
            orch,
            {"EURUSD:BUY": SimpleNamespace(symbol="EURUSD", side="BUY", quantity=1.0, entry_price=1.1000)},
        )

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_current_tick", return_value={"bid": 1.1000}),
            patch(
                f"{MT5_GATEWAY}.get_positions",
                # qty diff 0.005: > qty_tolerance (0.0001) but <= auto_fix_threshold
                # (0.01) -> auto_fixable -> WARNING, not CRITICAL
                return_value=[{"symbol": "EURUSD", "type": 0, "volume": 1.005, "price_open": 1.1000}],
            ),
        ):
            _run_sync_cycle(orch)

        assert orch.trading_loop.get_stats()["kill_switch_active"] is False

    def test_unfixable_qty_mismatch_trips_kill_switch(self):
        """A qty mismatch too large to auto-fix is CRITICAL and must trip the
        kill switch."""
        orch = _make_orchestrator()
        _stub_position_manager(
            orch,
            {"EURUSD:BUY": SimpleNamespace(symbol="EURUSD", side="BUY", quantity=1.0, entry_price=1.1000)},
        )

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_current_tick", return_value={"bid": 1.1000}),
            patch(
                f"{MT5_GATEWAY}.get_positions",
                # qty diff 5.0: far beyond auto_fix_threshold (0.01) -> CRITICAL
                return_value=[{"symbol": "EURUSD", "type": 0, "volume": 6.0, "price_open": 1.1000}],
            ),
        ):
            _run_sync_cycle(orch)

        assert orch.trading_loop.get_stats()["kill_switch_active"] is True


class TestReconciliationFailureEscalation:
    def test_repeated_exceptions_trip_kill_switch_at_threshold(self):
        """3 consecutive reconciliation-cycle exceptions must trip the kill
        switch; fewer than 3 must not."""
        orch = _make_orchestrator()
        _stub_position_manager(orch, {})

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_positions", side_effect=RuntimeError("broker unreachable")),
        ):
            _run_sync_cycle(orch)
            assert orch._reconciliation_fail_count == 1
            assert orch.trading_loop.get_stats()["kill_switch_active"] is False

            _run_sync_cycle(orch)
            assert orch._reconciliation_fail_count == 2
            assert orch.trading_loop.get_stats()["kill_switch_active"] is False

            _run_sync_cycle(orch)
            assert orch._reconciliation_fail_count == 3
            assert orch.trading_loop.get_stats()["kill_switch_active"] is True

    def test_successful_cycle_resets_failure_count(self):
        """A clean reconciliation cycle must reset the consecutive-failure
        counter, so prior failures don't accumulate toward the trip
        threshold."""
        orch = _make_orchestrator()
        _stub_position_manager(orch, {})

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_positions", side_effect=RuntimeError("broker unreachable")),
        ):
            _run_sync_cycle(orch)
        assert orch._reconciliation_fail_count == 1

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_positions", return_value=[]),
        ):
            _run_sync_cycle(orch)
        assert orch._reconciliation_fail_count == 0
        assert orch.trading_loop.get_stats()["kill_switch_active"] is False

        with (
            patch(f"{MT5_GATEWAY}.get_account_info", return_value=ACCOUNT_INFO),
            patch(f"{MT5_GATEWAY}.get_positions", side_effect=RuntimeError("broker unreachable")),
        ):
            _run_sync_cycle(orch)
            _run_sync_cycle(orch)

        # Only 2 consecutive failures since the reset -- below the threshold of 3.
        assert orch._reconciliation_fail_count == 2
        assert orch.trading_loop.get_stats()["kill_switch_active"] is False
