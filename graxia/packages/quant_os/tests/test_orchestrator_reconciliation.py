"""Regression tests for core/orchestrator.py::_sync_live_market_state.

Covers the implemented sync contract:
1. No-op when the broker adapter is None or disconnected.
2. Equity sync: adapter.get_account_info() -> trading_loop.update_account_equity()
   + position_manager.sync_account_state().
3. Price sync: adapter.get_tick() -> position_manager.update_prices().
4. Graceful degradation: missing get_tick, missing positions, zero/missing
   bids and per-call failures are all tolerated without raising.

NOTE: The originally-planned Phase 0 item 5 (reconciliation-driven kill-switch
trips with a fail counter) was never implemented in _sync_live_market_state;
this suite is aligned to the implemented behavior instead.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from graxia.packages.quant_os.core.config import QuantConfig
from graxia.packages.quant_os.core.orchestrator import TradingOrchestrator


def _make_orchestrator() -> TradingOrchestrator:
    return TradingOrchestrator(config=QuantConfig())


def _make_adapter(**overrides: object) -> SimpleNamespace:
    """Fake broker adapter with a healthy account-info response."""
    base: dict[str, object] = {
        "is_connected": True,
        "get_account_info": lambda: SimpleNamespace(equity=1000.0, balance=900.0, margin_level=200.0),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _run_sync_cycle(orch: TradingOrchestrator) -> None:
    orch._sync_live_market_state()


class TestSyncLiveMarketState:
    def test_noop_when_broker_adapter_is_none(self):
        orch = _make_orchestrator()
        orch._broker_adapter = None
        orch._position_manager = MagicMock()

        _run_sync_cycle(orch)

        orch._position_manager.sync_account_state.assert_not_called()
        orch._position_manager.update_prices.assert_not_called()

    def test_noop_when_broker_disconnected(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(is_connected=False)
        orch._position_manager = MagicMock()

        _run_sync_cycle(orch)

        orch._position_manager.sync_account_state.assert_not_called()
        orch._position_manager.update_prices.assert_not_called()

    def test_equity_sync_propagates_to_loop_and_position_manager(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter()
        orch._trading_loop = MagicMock()
        orch._position_manager = MagicMock(get_positions=MagicMock(return_value={}))

        _run_sync_cycle(orch)

        orch._trading_loop.update_account_equity.assert_called_once_with(1000.0, margin_level_pct=200.0)
        orch._position_manager.sync_account_state.assert_called_once_with(
            equity=1000.0, balance=900.0, margin_level=200.0
        )

    def test_zero_equity_skips_account_sync(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(
            get_account_info=lambda: SimpleNamespace(equity=0.0, balance=0.0, margin_level=0.0)
        )
        orch._trading_loop = MagicMock()
        orch._position_manager = MagicMock(get_positions=MagicMock(return_value={}))

        _run_sync_cycle(orch)

        orch._trading_loop.update_account_equity.assert_not_called()
        orch._position_manager.sync_account_state.assert_not_called()

    def test_equity_failure_swallowed_then_price_sync_continues(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(
            get_account_info=MagicMock(side_effect=RuntimeError("equity boom")),
            get_tick=lambda _sym: {"bid": 1.1000},
        )
        orch._position_manager = MagicMock(
            get_positions=MagicMock(return_value={"EURUSD:BUY": SimpleNamespace(symbol="EURUSD")}),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)  # must not raise; price sync still runs

        orch._position_manager.update_prices.assert_called_once_with({"EURUSD": 1.1000})

    def test_price_sync_updates_prices_from_ticks(self):
        def _tick(symbol: str) -> dict[str, float]:
            return {"bid": 1.1000} if symbol == "EURUSD" else {"bid": 0.0}

        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(get_tick=_tick)
        orch._position_manager = MagicMock(
            get_positions=MagicMock(
                return_value={
                    "EURUSD:BUY": SimpleNamespace(symbol="EURUSD"),
                    "GBPUSD:SELL": SimpleNamespace(symbol="GBPUSD"),  # bid 0.0 -> skipped
                }
            ),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)

        orch._position_manager.update_prices.assert_called_once_with({"EURUSD": 1.1000})

    def test_no_price_sync_without_get_tick(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter()  # no get_tick -> graceful degradation
        orch._position_manager = MagicMock(
            get_positions=MagicMock(return_value={"EURUSD:BUY": SimpleNamespace(symbol="EURUSD")}),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)

        orch._position_manager.sync_account_state.assert_called_once()
        orch._position_manager.update_prices.assert_not_called()

    def test_no_price_sync_without_open_positions(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(get_tick=lambda _sym: {"bid": 1.1000})
        orch._position_manager = MagicMock(
            get_positions=MagicMock(return_value={}),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)

        orch._position_manager.sync_account_state.assert_called_once()
        orch._position_manager.update_prices.assert_not_called()

    def test_tick_failure_swallowed(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(get_tick=MagicMock(side_effect=RuntimeError("tick boom")))
        orch._position_manager = MagicMock(
            get_positions=MagicMock(return_value={"EURUSD:BUY": SimpleNamespace(symbol="EURUSD")}),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)  # must not raise

        orch._position_manager.update_prices.assert_not_called()

    def test_object_tick_with_bid_attribute_supported(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(get_tick=lambda _sym: SimpleNamespace(bid=1.1000))
        orch._position_manager = MagicMock(
            get_positions=MagicMock(return_value={"EURUSD:BUY": SimpleNamespace(symbol="EURUSD")}),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)

        orch._position_manager.update_prices.assert_called_once_with({"EURUSD": 1.1000})

    def test_missing_bid_ignored(self):
        orch = _make_orchestrator()
        orch._broker_adapter = _make_adapter(get_tick=lambda _sym: {"ask": 1.1000})  # no 'bid'
        orch._position_manager = MagicMock(
            get_positions=MagicMock(return_value={"EURUSD:BUY": SimpleNamespace(symbol="EURUSD")}),
            sync_account_state=MagicMock(),
            update_prices=MagicMock(),
        )

        _run_sync_cycle(orch)

        orch._position_manager.update_prices.assert_not_called()
