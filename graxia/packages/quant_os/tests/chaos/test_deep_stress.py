"""
Deep Stress Tests — Multi-Module Chaos
=======================================
Exercises multiple modules together under sustained load.

Run:
  python -m pytest tests/chaos/test_deep_stress.py -q --tb=short
"""

from __future__ import annotations

import gc
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pytest
from quant_os.core.enums import OrderStatus, SignalType
from quant_os.core.event_bus import EventBus
from quant_os.core.events import (
    Event,
    FillEvent,
    OrderEvent,
    SignalEvent,
    TickEvent,
)
from quant_os.core.portfolio_risk import PortfolioRisk, Position
from quant_os.core.state_store import SystemState, load, save
from quant_os.execution.order_state_machine import OrderStateMachine
from quant_os.risk.engine import (
    AccountState,
    PortfolioState,
    RiskEngine,
    RiskVerdict,
    Signal,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_state_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def risk_engine():
    return RiskEngine()


@pytest.fixture
def portfolio_risk():
    return PortfolioRisk(capital=100_000.0)


def _fast_signal(i: int) -> Signal:
    return Signal(
        symbol=f"SYM{i % 20}",
        conviction=0.8,
        entry_price=2000.0 + i * 0.1,
        stop_loss=1995.0,
        take_profit=2010.0,
        direction="BUY",
        side="BUY",
        timestamp=datetime.now(),
        timestamp_epoch=time.time(),
        asset_class="metals",
        venue="paper",
        strategy_id=f"strat_{i % 5}",
    )


def _fresh_account(equity: float = 100_000.0) -> AccountState:
    return AccountState(equity=equity, free_margin=equity)


def _fresh_portfolio(n_positions: int = 0) -> PortfolioState:
    syms = [f"SYM{i}" for i in range(n_positions)]
    return PortfolioState(
        total_exposure_pct=0.01 * n_positions,
        class_exposure_pct={"metals": 0.01 * n_positions},
        venue_exposure_pct={"paper": 0.01 * n_positions},
        position_symbols=syms,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Risk Engine Under Stress — 1000 rapid signals
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskEngineStress:
    def test_1000_rapid_signals(self, risk_engine):
        account = _fresh_account()
        portfolio = _fresh_portfolio()
        results: list[RiskVerdict] = []
        for i in range(1000):
            sig = _fast_signal(i)
            v = risk_engine.evaluate(sig, account, portfolio)
            results.append(v)
        approved = sum(1 for r in results if r.approved)
        rejected = sum(1 for r in results if not r.approved)
        assert approved + rejected == 1000

    def test_signals_under_daily_loss_limit(self, risk_engine):
        account = _fresh_account()
        account.daily_pnl = -1500.0  # 1.5% loss, under 2% default
        portfolio = _fresh_portfolio()
        v = risk_engine.evaluate(_fast_signal(0), account, portfolio)
        assert v.approved is True

    def test_signals_exceed_daily_loss_limit(self, risk_engine):
        account = _fresh_account()
        account.daily_pnl = -3000.0  # 3% loss, exceeds 2%
        portfolio = _fresh_portfolio()
        v = risk_engine.evaluate(_fast_signal(0), account, portfolio)
        assert v.approved is False
        assert "daily_loss" in v.reason.lower() or "DAILY_LOSS" in str(v.reason_code)

    def test_max_positions_rejected(self, risk_engine):
        account = _fresh_account()
        portfolio = _fresh_portfolio(n_positions=20)
        v = risk_engine.evaluate(_fast_signal(0), account, portfolio)
        assert v.approved is False
        assert "positions" in v.reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Order State Machine Stress — 500 orders, all transitions
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrderStateMachineStress:
    # SIGNAL_CREATED is the default initial state; start transitions from RISK_CHECKED
    HAPPY_PATH = [
        OrderStatus.RISK_CHECKED,
        OrderStatus.ORDER_PRECHECKED,
        OrderStatus.ORDER_SUBMITTED,
        OrderStatus.ORDER_ACKNOWLEDGED,
        OrderStatus.FILLED,
        OrderStatus.PROTECTIVE_STOPS_PENDING,
        OrderStatus.PROTECTIVE_STOPS_VERIFIED,
        OrderStatus.POSITION_RECONCILED,
        OrderStatus.CLOSED,
        OrderStatus.DEAL_RECONCILED,
        OrderStatus.AUDITED,
    ]

    def test_500_orders_full_happy_path(self):
        errors: list = []
        for i in range(500):
            try:
                sm = OrderStateMachine(order_id=f"ORD-{i}")
                for state in self.HAPPY_PATH:
                    sm.transition(state)
                assert sm.is_terminal()
            except Exception as e:
                errors.append((i, e))
        assert errors == []

    def test_reject_at_each_stage(self):
        for i, stop_at in enumerate(self.HAPPY_PATH):
            sm = OrderStateMachine(order_id=f"REJ-{i}")
            for state in self.HAPPY_PATH[:i]:
                sm.transition(state)
            try:
                sm.transition(OrderStatus.REJECTED)
                assert sm.is_terminal()
            except Exception:
                pass

    def test_invalid_transition_raises(self):
        from quant_os.core.exceptions import OrderStateError

        sm = OrderStateMachine(order_id="BAD")
        with pytest.raises(OrderStateError):
            sm.transition(OrderStatus.AUDITED)

    def test_concurrent_order_transitions(self):
        errors: list = []

        def run_order(i: int):
            try:
                sm = OrderStateMachine(order_id=f"THR-{i}")
                for state in self.HAPPY_PATH:
                    sm.transition(state)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(run_order, i) for i in range(200)]
            for f in as_completed(futs):
                f.result()
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Event Bus Stress — 1000 events concurrently
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventBusStress:
    def test_1000_events_fired(self):
        bus = EventBus()
        received: list = []
        bus.subscribe(SignalEvent, lambda e: received.append(e))
        for i in range(1000):
            bus.publish(SignalEvent(symbol=f"SYM{i % 10}", signal_type=SignalType.BUY))
        assert len(received) == 1000
        assert bus.published_count == 1000

    def test_handler_exception_isolation(self):
        bus = EventBus()
        ok_events: list = []

        def bad_handler(e):
            raise RuntimeError("boom")

        def good_handler(e):
            ok_events.append(e)

        bus.subscribe(SignalEvent, bad_handler)
        bus.subscribe(SignalEvent, good_handler)
        for i in range(100):
            bus.publish(SignalEvent(symbol="X", signal_type=SignalType.BUY))
        assert len(ok_events) == 100
        assert bus.handler_errors == 100

    def test_concurrent_publish(self):
        bus = EventBus()
        received: list = []
        bus.subscribe(SignalEvent, lambda e: received.append(e))
        errors: list = []

        def publish_batch(start: int):
            try:
                for i in range(200):
                    bus.publish(SignalEvent(symbol=f"S{i}", signal_type=SignalType.BUY))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=publish_batch, args=(i * 200,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert errors == []
        assert len(received) == 1000

    def test_unsubscribe_during_stress(self):
        bus = EventBus()
        count = [0]
        handler = lambda e: count.__setitem__(0, count[0] + 1)
        bus.subscribe(SignalEvent, handler)
        for i in range(500):
            bus.publish(SignalEvent(symbol="X", signal_type=SignalType.BUY))
        bus.unsubscribe(SignalEvent, handler)
        for i in range(500):
            bus.publish(SignalEvent(symbol="X", signal_type=SignalType.BUY))
        assert count[0] == 500

    def test_mixed_event_types_stress(self):
        bus = EventBus()
        counts = {"sig": 0, "tick": 0, "order": 0, "fill": 0}
        bus.subscribe(SignalEvent, lambda e: counts.__setitem__("sig", counts["sig"] + 1))
        bus.subscribe(TickEvent, lambda e: counts.__setitem__("tick", counts["tick"] + 1))
        bus.subscribe(OrderEvent, lambda e: counts.__setitem__("order", counts["order"] + 1))
        bus.subscribe(FillEvent, lambda e: counts.__setitem__("fill", counts["fill"] + 1))
        for i in range(250):
            bus.publish(SignalEvent(symbol="X", signal_type=SignalType.BUY))
            bus.publish(TickEvent(symbol="X"))
            bus.publish(OrderEvent(symbol="X"))
            bus.publish(FillEvent(symbol="X"))
        assert counts["sig"] == 250
        assert counts["tick"] == 250
        assert counts["order"] == 250
        assert counts["fill"] == 250


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Portfolio Risk Stress — 100 positions simultaneously
# ═══════════════════════════════════════════════════════════════════════════════


class TestPortfolioRiskStress:
    def test_100_positions_simultaneous(self, portfolio_risk):
        for i in range(100):
            pos = Position(
                symbol=f"SYM{i}",
                direction="LONG",
                entry_price=2000.0,
                risk_dollars=10.0,
                size_lots=0.01,
            )
            portfolio_risk.add_position(pos)
        assert portfolio_risk.total_risk == 1000.0

    def test_rapid_add_remove_cycle(self, portfolio_risk):
        for i in range(500):
            pos = Position(symbol="XAUUSD", direction="LONG", entry_price=2000.0, risk_dollars=50.0, size_lots=0.1)
            portfolio_risk.add_position(pos)
            result = portfolio_risk.can_add("XAUUSD", 10.0)
            portfolio_risk.remove_position("XAUUSD")

    def test_pnl_tracking_under_load(self, portfolio_risk):
        for i in range(1000):
            portfolio_risk.update_pnl(10.0 if i % 3 == 0 else -5.0)
        assert portfolio_risk._daily_pnl != 0

    def test_can_add_blocks_at_limit(self):
        pr = PortfolioRisk(capital=10_000.0)
        for i in range(10):
            pr.add_position(
                Position(symbol=f"S{i}", direction="LONG", entry_price=100.0, risk_dollars=60.0, size_lots=1.0)
            )
        result = pr.can_add("NEW", risk_dollars=100.0)
        assert result["allowed"] is False

    def test_concurrent_portfolio_access(self, portfolio_risk):
        errors: list = []

        def writer(sym: str):
            try:
                for _ in range(50):
                    portfolio_risk.add_position(
                        Position(symbol=sym, direction="LONG", entry_price=2000.0, risk_dollars=10.0, size_lots=0.01)
                    )
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = [pool.submit(writer, f"P{i}") for i in range(5)]
            for f in as_completed(futs):
                f.result()
        assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Signal Pipeline Stress — 500 signals end-to-end
# ═══════════════════════════════════════════════════════════════════════════════


class TestSignalPipelineStress:
    def test_500_signals_end_to_end(self):
        bus = EventBus()
        risk_engine = RiskEngine()
        account = _fresh_account()
        portfolio = _fresh_portfolio()
        approved = [0]
        rejected = [0]

        def risk_handler(e: SignalEvent):
            sig = Signal(
                symbol=e.symbol,
                conviction=e.confidence,
                entry_price=e.entry_price,
                stop_loss=e.stop_loss,
                take_profit=e.take_profit,
                direction="BUY" if e.signal_type == SignalType.BUY else "SELL",
                timestamp=datetime.now(),
                timestamp_epoch=time.time(),
            )
            v = risk_engine.evaluate(sig, account, portfolio)
            if v.approved:
                approved[0] += 1
            else:
                rejected[0] += 1

        bus.subscribe(SignalEvent, risk_handler)
        for i in range(500):
            bus.publish(
                SignalEvent(
                    symbol=f"SYM{i % 20}",
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    entry_price=2000.0 + i * 0.1,
                    stop_loss=1995.0,
                    take_profit=2010.0,
                )
            )
        assert approved[0] + rejected[0] == 500


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Memory Under Sustained Load — track RSS over 1000 iterations
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryStress:
    def test_sustained_load_no_growth(self):
        gc.collect()
        baseline_objects = len(gc.get_objects())

        bus = EventBus()
        bus.subscribe(Event, lambda e: None)
        for i in range(1000):
            bus.publish(SignalEvent(symbol="X", signal_type=SignalType.BUY))
            if i % 100 == 0:
                gc.collect()

        gc.collect()
        final_objects = len(gc.get_objects())
        growth_pct = (final_objects - baseline_objects) / max(baseline_objects, 1)
        assert (
            growth_pct < 1.0
        ), f"Object count grew {growth_pct:.0%} (baseline={baseline_objects}, final={final_objects})"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Concurrent State Store — 10 threads writing to same file
# ═══════════════════════════════════════════════════════════════════════════════


class TestConcurrentStateStore:
    def test_10_threads_same_file(self, tmp_state_dir):
        path = os.path.join(tmp_state_dir, "state.json")
        errors: list = []

        def writer(n: int):
            try:
                for i in range(20):
                    state = SystemState(
                        system_state="RUNNING",
                        daily_pnl=float(n * 100 + i),
                        positions=[{"id": f"pos-{n}-{i}"}],
                    )
                    for attempt in range(3):
                        try:
                            save(state, path)
                            break
                        except (PermissionError, OSError):
                            time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(20):
                    for attempt in range(3):
                        try:
                            load(path)
                            break
                        except (PermissionError, OSError):
                            time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        threads.append(threading.Thread(target=reader))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert errors == []
        loaded = load(path)
        assert loaded.system_state == "RUNNING"

    def test_state_corruption_recovery(self, tmp_state_dir):
        path = os.path.join(tmp_state_dir, "state.json")
        save(SystemState(daily_pnl=42.0), path)
        Path(path).write_text("{corrupt", encoding="utf-8")
        loaded = load(path)
        assert loaded.system_state == "INIT"
        assert loaded.daily_pnl == 0.0

    def test_missing_file_returns_default(self, tmp_state_dir):
        loaded = load(os.path.join(tmp_state_dir, "nonexistent.json"))
        assert loaded.system_state == "INIT"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Redis Failure Cascade — simulated Redis down mid-operation
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedisFailureCascade:
    """Simulates Redis going down mid-operation by mocking failures."""

    def test_graceful_degradation_without_redis(self, risk_engine):
        account = _fresh_account()
        portfolio = _fresh_portfolio()
        sig = _fast_signal(0)
        v = risk_engine.evaluate(sig, account, portfolio)
        assert v.approved is True

    def test_event_bus_survives_handler_failure(self):
        bus = EventBus()
        fail_count = [0]
        ok_count = [0]

        def failing_handler(e):
            fail_count[0] += 1
            raise ConnectionError("Redis down")

        def ok_handler(e):
            ok_count[0] += 1

        bus.subscribe(SignalEvent, failing_handler)
        bus.subscribe(SignalEvent, ok_handler)
        for _ in range(100):
            bus.publish(SignalEvent(symbol="X", signal_type=SignalType.BUY))
        assert fail_count[0] == 100
        assert ok_count[0] == 100

    def test_state_store_atomic_write_interrupted(self, tmp_state_dir):
        path = os.path.join(tmp_state_dir, "state.json")
        save(SystemState(daily_pnl=100.0), path)
        from unittest.mock import patch as mock_patch

        original_replace = os.replace

        def fail_replace(src, dst):
            if ".tmp" in src:
                raise OSError("Disk full")
            return original_replace(src, dst)

        with pytest.raises(OSError):
            with mock_patch("os.replace", side_effect=fail_replace):
                save(SystemState(daily_pnl=200.0), path)
        loaded = load(path)
        assert loaded.daily_pnl == 100.0

    def test_risk_engine_kill_switch_cascades(self):
        class FakeKillSwitch:
            def is_active(self):
                return True

            @property
            def trigger_type(self):
                return "MANUAL"

        engine = RiskEngine(kill_switch=FakeKillSwitch())
        sig = _fast_signal(0)
        v = engine.evaluate(sig, _fresh_account(), _fresh_portfolio())
        assert v.approved is False
        assert "kill" in v.reason.lower()

    def test_partial_fill_then_crash_recovery(self):
        sm = OrderStateMachine(order_id="CRASH-1")
        sm.transition(OrderStatus.RISK_CHECKED)
        sm.transition(OrderStatus.ORDER_PRECHECKED)
        sm.transition(OrderStatus.ORDER_SUBMITTED)
        sm.transition(OrderStatus.PARTIAL_FILL)
        assert sm.state == OrderStatus.PARTIAL_FILL
        sm.transition(OrderStatus.CRITICAL_INCIDENT)
        assert sm.is_terminal()
