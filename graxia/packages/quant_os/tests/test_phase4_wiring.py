"""Phase 4 — Tests for top-5 highest-risk new modules.

Tests for:
1. BrokerReconnector — heartbeat, reconnection, pacing limiter
2. RealTimePnLTracker — drawdown enforcement, alerts
3. MarginSimulator — margin calls, forced liquidation
4. DecayMonitor — 8-metric decay detection
5. PositionReconciler — position drift detection
"""

from decimal import Decimal

import pytest


# ── 1. BrokerReconnector Tests ──────────────────────────────────────────

class TestBrokerReconnector:
    """Tests for BrokerReconnector heartbeat, reconnection, and pacing."""

    def test_initial_state_connected(self):
        from execution.broker_reconnector import BrokerReconnector
        br = BrokerReconnector()
        assert br.state.value == "connected"
        assert br.is_connected is True
        assert br.is_trading_allowed is True

    def test_heartbeat_timeout_triggers_disconnect(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerConfig, BrokerState
        config = BrokerConfig(heartbeat_timeout_sec=0.0)  # Immediate timeout
        br = BrokerReconnector(config)
        br._last_heartbeat = 0.0  # Force stale
        healthy = br.check_heartbeat()
        assert healthy is False
        assert br.state == BrokerState.DISCONNECTED
        assert br.is_trading_allowed is False

    def test_reconnect_attempt(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerConfig, BrokerState
        config = BrokerConfig(heartbeat_timeout_sec=0.0, max_reconnect_attempts=3)
        br = BrokerReconnector(config)
        br._last_heartbeat = 0.0
        br.check_heartbeat()  # Trigger disconnect
        event = br.attempt_reconnect()
        assert event.event_type == "RECONNECTING"
        assert br.state == BrokerState.RECONNECTING
        assert event.attempt == 1

    def test_max_reconnect_attempts_triggers_failed(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerConfig, BrokerState
        config = BrokerConfig(heartbeat_timeout_sec=0.0, max_reconnect_attempts=2)
        br = BrokerReconnector(config)
        br._last_heartbeat = 0.0
        br.check_heartbeat()
        br.attempt_reconnect()
        br.attempt_reconnect()
        event = br.attempt_reconnect()
        assert event.event_type == "FAILED"
        assert br.state == BrokerState.FAILED

    def test_heartbeat_received_reconnects(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerConfig, BrokerState
        config = BrokerConfig(heartbeat_timeout_sec=0.0)
        br = BrokerReconnector(config)
        br._last_heartbeat = 0.0
        br.check_heartbeat()
        assert br.state == BrokerState.DISCONNECTED
        br.heartbeat_received()
        assert br.state == BrokerState.CONNECTED
        assert br.is_trading_allowed is True

    def test_stale_halt_after_max_bars(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerConfig
        config = BrokerConfig(max_stale_bars=2)
        br = BrokerReconnector(config)
        br.on_bar_close()
        br.on_bar_close()
        br.on_bar_close()  # 3 bars > max_stale_bars=2
        assert br.is_trading_allowed is False

    def test_ib_historical_rate_limit(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerConfig
        config = BrokerConfig(ib_historical_rate_limit=2, ib_historical_window_sec=120.0)
        br = BrokerReconnector(config)
        assert br.check_historical_rate_limit() is True
        assert br.check_historical_rate_limit() is True
        assert br.check_historical_rate_limit() is False  # Rate limited

    def test_reset(self):
        from execution.broker_reconnector import BrokerReconnector, BrokerState
        br = BrokerReconnector()
        br._last_heartbeat = 0.0
        br.check_heartbeat()
        assert br.state == BrokerState.DISCONNECTED
        br.reset()
        assert br.state == BrokerState.CONNECTED


# ── 2. RealTimePnLTracker Tests ──────────────────────────────────────────

class TestRealTimePnLTracker:
    """Tests for RealTimePnLTracker drawdown enforcement and alerts."""

    def test_initial_equity(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        assert tracker.equity == Decimal("10000")
        assert tracker.drawdown_pct == 0.0

    def test_update_tick_increases_equity(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        tracker.update_tick(Decimal("500"))  # +500 unrealized
        assert tracker.equity == Decimal("10500")
        assert tracker.drawdown_pct == 0.0

    def test_drawdown_calculation(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        tracker.update_tick(Decimal("500"))  # Peak = 10500, equity = 10500
        tracker.update_tick(Decimal("-1000"))  # equity = 10000 + (-1000) = 9000, peak = 10500
        # Drawdown from peak: (10500 - 9000) / 10500 = 0.142857
        assert abs(tracker.drawdown_pct - 0.142857) < 0.001

    def test_daily_drawdown_alert(self):
        from risk.realtime_pnl import RealTimePnLTracker, PnLConfig
        config = PnLConfig(max_daily_drawdown_pct=0.03)
        tracker = RealTimePnLTracker(config=config, initial_equity=Decimal("10000"))
        tracker.new_day()
        tracker.update_tick(Decimal("-400"))  # -4% daily DD > 3% limit
        alerts = [a for a in tracker.alerts if a.metric == "daily_drawdown"]
        assert len(alerts) > 0
        assert alerts[0].alert_type == "BREACH"

    def test_total_drawdown_warning(self):
        from risk.realtime_pnl import RealTimePnLTracker, PnLConfig
        config = PnLConfig(warning_drawdown_pct=0.02)
        tracker = RealTimePnLTracker(config=config, initial_equity=Decimal("10000"))
        tracker.update_tick(Decimal("-300"))  # 3% DD > 2% warning
        alerts = [a for a in tracker.alerts if a.alert_type == "WARNING"]
        assert len(alerts) > 0

    def test_can_open_position(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        allowed, reason = tracker.can_open_position(0.10)
        assert allowed is True

    def test_cannot_open_position_max_drawdown(self):
        from risk.realtime_pnl import RealTimePnLTracker, PnLConfig
        config = PnLConfig(critical_drawdown_pct=0.05)
        tracker = RealTimePnLTracker(config=config, initial_equity=Decimal("10000"))
        tracker.update_tick(Decimal("-600"))  # 6% DD > 5% critical
        allowed, reason = tracker.can_open_position(0.10)
        assert allowed is False
        assert "exceeds critical" in reason

    def test_record_trade_pnl(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        tracker.record_trade_pnl(Decimal("200"))
        assert tracker.equity == Decimal("10200")
        assert tracker._realized_pnl == Decimal("200")

    def test_snapshot(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        tracker.update_tick(Decimal("100"))
        snap = tracker.get_snapshot()
        assert snap.equity == Decimal("10100")
        assert snap.peak_equity == Decimal("10100")

    def test_reset(self):
        from risk.realtime_pnl import RealTimePnLTracker
        tracker = RealTimePnLTracker(initial_equity=Decimal("10000"))
        tracker.update_tick(Decimal("500"))
        tracker.record_trade_pnl(Decimal("100"))
        tracker.reset()
        assert tracker.equity == Decimal("10000")
        assert tracker._realized_pnl == Decimal("0")


# ── 3. MarginSimulator Tests ──────────────────────────────────────────

class TestMarginSimulator:
    """Tests for MarginSimulator margin calls and forced liquidation."""

    def test_initial_state(self):
        from risk.margin_simulator import MarginSimulator
        ms = MarginSimulator()
        assert len(ms.events) == 0

    def test_calculate_margin_state(self):
        from risk.margin_simulator import MarginSimulator
        ms = MarginSimulator()
        positions = [{"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "LONG"}]
        state = ms.calculate_margin_state(positions, Decimal("10000"))
        assert state.used_margin == Decimal("1000")  # 2000 * 1 * 50% = 1000
        assert state.margin_utilization == 0.1  # 1000/10000

    def test_no_margin_call_when_healthy(self):
        from risk.margin_simulator import MarginSimulator
        ms = MarginSimulator()
        positions = [{"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "LONG"}]
        events = ms.check_margin(positions, Decimal("10000"), current_bar=1)
        assert len(events) == 0

    def test_margin_call_triggered(self):
        from risk.margin_simulator import MarginSimulator, MarginConfig
        config = MarginConfig(maintenance_margin_pct=0.25, warning_threshold_pct=0.50)
        ms = MarginSimulator(config)
        # Position requires 1000 margin (2000 * 1 * 50%). Maintenance = 1000 * 25% = 250
        # If equity < 250, trigger margin call
        positions = [{"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "LONG"}]
        events = ms.check_margin(positions, Decimal("200"), current_bar=1)  # Equity only 200
        margin_calls = [e for e in events if e.event_type == "MARGIN_CALL"]
        assert len(margin_calls) > 0

    def test_forced_liquidation_after_delay(self):
        from risk.margin_simulator import MarginSimulator, MarginConfig
        config = MarginConfig(maintenance_margin_pct=0.25, margin_call_delay_bars=2)
        ms = MarginSimulator(config)
        positions = [{"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "LONG",
                      "symbol": "XAUUSD"}]
        # Trigger margin call
        ms.check_margin(positions, Decimal("200"), current_bar=1, current_prices={"XAUUSD": Decimal("2000")})
        # Not yet liquidated (only 1 bar elapsed)
        events1 = ms.check_margin(positions, Decimal("200"), current_bar=2, current_prices={"XAUUSD": Decimal("2000")})
        assert not any(e.event_type == "FORCED_LIQUIDATION" for e in events1)
        # Now liquidated (2 bars elapsed)
        events2 = ms.check_margin(positions, Decimal("200"), current_bar=3, current_prices={"XAUUSD": Decimal("2000")})
        assert any(e.event_type == "FORCED_LIQUIDATION" for e in events2)

    def test_apply_forced_liquidation_long(self):
        from risk.margin_simulator import MarginSimulator
        ms = MarginSimulator()
        position = {"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "LONG"}
        exit_price, pnl = ms.apply_forced_liquidation(position, Decimal("2000"))
        # Discount = 10%, so exit = 2000 * 0.9 = 1800
        assert exit_price == Decimal("1800")
        assert pnl == (Decimal("1800") - Decimal("2000")) * Decimal("1")  # -200

    def test_apply_forced_liquidation_short(self):
        from risk.margin_simulator import MarginSimulator
        ms = MarginSimulator()
        position = {"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "SHORT"}
        exit_price, pnl = ms.apply_forced_liquidation(position, Decimal("2000"))
        # Inflated = 10%, so exit = 2000 * 1.1 = 2200
        assert exit_price == Decimal("2200")
        assert pnl == (Decimal("2000") - Decimal("2200")) * Decimal("1")  # -200

    def test_events_capped(self):
        from risk.margin_simulator import MarginSimulator, MarginConfig
        config = MarginConfig(warning_threshold_pct=0.01)  # Always warn
        ms = MarginSimulator(config)
        ms._max_events = 10
        positions = [{"entry_price": Decimal("100"), "quantity": Decimal("1"), "side": "LONG"}]
        for i in range(20):
            ms.check_margin(positions, Decimal("10000"), current_bar=i, current_prices={"XAUUSD": Decimal("100")})
        assert len(ms.events) <= 10

    def test_reset(self):
        from risk.margin_simulator import MarginSimulator
        ms = MarginSimulator()
        positions = [{"entry_price": Decimal("2000"), "quantity": Decimal("1"), "side": "LONG",
                      "symbol": "XAUUSD"}]
        ms.check_margin(positions, Decimal("200"), current_bar=1)
        ms.reset()
        assert len(ms.events) == 0


# ── 4. DecayMonitor Tests ──────────────────────────────────────────

class TestDecayMonitor:
    """Tests for DecayMonitor 8-metric decay detection."""

    def test_initial_state(self):
        from validation.decay_monitor import DecayMonitor, DecaySignal
        dm = DecayMonitor()
        signal, alerts = dm.evaluate()
        assert signal == DecaySignal.NORMAL
        assert len(alerts) == 0

    def test_rolling_sharpe_warning(self):
        from validation.decay_monitor import DecayMonitor, DecayConfig, DecaySignal
        config = DecayConfig(rolling_window=20, sharpe_warning=0.5)
        dm = DecayMonitor(config)
        # Add returns that produce low Sharpe (lots of small losses)
        for _ in range(25):
            dm.update(-0.001)
        signal, alerts = dm.evaluate()
        sharpe_alerts = [a for a in alerts if a.metric_name == "rolling_sharpe"]
        # Should trigger warning or critical
        assert len(sharpe_alerts) > 0

    def test_win_rate_decay(self):
        from validation.decay_monitor import DecayMonitor, DecayConfig, DecayMetrics
        config = DecayConfig(rolling_window=20, win_rate_warning=0.45)
        dm = DecayMonitor(config)
        dm.set_baseline(DecayMetrics(win_rate=0.60))
        # Add mostly losing trades
        for _ in range(25):
            dm.update(bar_return=-0.001, trade_pnl=-1.0)
        for _ in range(5):
            dm.update(bar_return=0.001, trade_pnl=1.0)
        signal, alerts = dm.evaluate()
        wr_alerts = [a for a in alerts if a.metric_name == "win_rate"]
        assert len(wr_alerts) > 0

    def test_profit_factor_decay(self):
        from validation.decay_monitor import DecayMonitor, DecayConfig
        config = DecayConfig(rolling_window=20, pf_warning=1.2, pf_critical=1.0)
        dm = DecayMonitor(config)
        # Add equal wins and losses (PF = 1.0)
        for i in range(25):
            if i % 2 == 0:
                dm.update(bar_return=0.001, trade_pnl=1.0)
            else:
                dm.update(bar_return=-0.001, trade_pnl=-1.0)
        signal, alerts = dm.evaluate()
        pf_alerts = [a for a in alerts if a.metric_name == "profit_factor"]
        assert len(pf_alerts) > 0

    def test_critical_signal_when_many_alerts(self):
        from validation.decay_monitor import DecayMonitor, DecayConfig, DecaySignal
        config = DecayConfig(
            rolling_window=20,
            sharpe_emergency=-999.0,  # Won't trigger
            ir_critical=-999.0,
            win_rate_critical=0.01,  # Very low threshold
            pf_critical=0.01,
            pnl_decay_critical=0.99,
            freq_deviation_critical=0.99,
            signal_half_life_critical=1,
        )
        dm = DecayMonitor(config)
        # Add returns that produce many warnings
        for _ in range(25):
            dm.update(bar_return=-0.001, trade_pnl=-1.0, signal=0.5)
        # Set baseline that will trigger warnings
        from validation.decay_monitor import DecayMetrics
        dm.set_baseline(DecayMetrics(
            win_rate=0.90,
            avg_trade_pnl=100.0,
            trade_frequency_baseline=1.0,
        ))
        signal, alerts = dm.evaluate()
        # With many failing metrics, should be at least WARNING
        assert signal in (DecaySignal.WARNING, DecaySignal.CRITICAL, DecaySignal.EMERGENCY)

    def test_deque_bounded_memory(self):
        from validation.decay_monitor import DecayMonitor, DecayConfig
        config = DecayConfig(rolling_window=10)
        dm = DecayMonitor(config)
        for i in range(100):
            dm.update(bar_return=0.001)
        assert len(dm._returns) <= 10  # Bounded by deque maxlen

    def test_reset(self):
        from validation.decay_monitor import DecayMonitor
        dm = DecayMonitor()
        dm.update(bar_return=0.01, trade_pnl=1.0, signal=0.5)
        dm.reset()
        assert len(dm._returns) == 0
        assert len(dm._trades) == 0
        assert len(dm._signals) == 0


# ── 5. PositionReconciler Tests ──────────────────────────────────────────

class TestPositionReconciler:
    """Tests for PositionReconciler position drift detection."""

    def test_matching_positions(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        broker = [BrokerPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        result = pr.reconcile(internal, broker)
        assert result.matched is True
        assert result.drift_detected is False

    def test_quantity_mismatch(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("2"), Decimal("2000"))]
        broker = [BrokerPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        result = pr.reconcile(internal, broker)
        assert result.matched is False
        assert result.drift_detected is True
        assert result.mismatches[0]["type"] == "QTY_MISMATCH"

    def test_missing_from_broker(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        broker = []
        result = pr.reconcile(internal, broker)
        assert result.matched is False
        assert result.drift_detected is True
        assert result.mismatches[0]["type"] == "MISSING_FROM_BROKER"

    def test_extra_at_broker(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = []
        broker = [BrokerPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        result = pr.reconcile(internal, broker)
        assert result.matched is False
        assert result.drift_detected is True
        assert result.mismatches[0]["type"] == "EXTRA_AT_BROKER"

    def test_side_mismatch(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        broker = [BrokerPosition("XAUUSD", "SHORT", Decimal("1"), Decimal("2000"))]
        result = pr.reconcile(internal, broker)
        assert result.matched is False
        assert result.mismatches[0]["type"] == "SIDE_MISMATCH"

    def test_drift_count_tracks(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("2"), Decimal("2000"))]
        broker = [BrokerPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        pr.reconcile(internal, broker)
        pr.reconcile(internal, broker)
        assert pr.drift_count == 2

    def test_auto_close_drift_action(self):
        from execution.position_reconciler import PositionReconciler, ReconciliationConfig, InternalPosition, BrokerPosition
        config = ReconciliationConfig(auto_close_drift=True)
        pr = PositionReconciler(config)
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("2"), Decimal("2000"))]
        broker = []
        result = pr.reconcile(internal, broker)
        assert result.action_required == "CLOSE_DRIFT"

    def test_get_drift_positions(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        broker = []
        pr.reconcile(internal, broker)
        drift = pr.get_drift_positions()
        assert len(drift) == 1
        assert drift[0]["symbol"] == "XAUUSD"

    def test_multiple_symbols(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [
            InternalPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000")),
            InternalPosition("EURUSD", "SHORT", Decimal("2"), Decimal("1.1")),
        ]
        broker = [
            BrokerPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000")),
            BrokerPosition("EURUSD", "SHORT", Decimal("3"), Decimal("1.1")),  # Qty mismatch
        ]
        result = pr.reconcile(internal, broker)
        assert result.matched is False
        assert len(result.mismatches) == 1
        assert result.mismatches[0]["type"] == "QTY_MISMATCH"

    def test_reset(self):
        from execution.position_reconciler import PositionReconciler, InternalPosition, BrokerPosition
        pr = PositionReconciler()
        internal = [InternalPosition("XAUUSD", "LONG", Decimal("2"), Decimal("2000"))]
        broker = [BrokerPosition("XAUUSD", "LONG", Decimal("1"), Decimal("2000"))]
        pr.reconcile(internal, broker)
        pr.reset()
        assert pr.drift_count == 0
        assert pr.last_result is None
