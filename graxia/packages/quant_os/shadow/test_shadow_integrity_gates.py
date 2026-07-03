"""BE-P8.1 — Shadow integrity gate tests.

These tests prove the pipeline REJECTS signals that should never be accepted.
Evidence: SIG-000005 (entry=SL=TP) and SIG-000045 (spread 2.4x baseline)
were accepted in the original shadow session. These tests ensure that
can NEVER happen again.
"""

from datetime import datetime

from graxia.packages.quant_os.shadow.pipeline import (
    PositionStatus,
    ShadowPipeline,
    ShadowSignal,
    ShadowSignalOutcome,
    SignalDeduplicator,
    SpreadShockGate,
    validate_signal_geometry,
)

# ── Geometry validation tests ────────────────────────────────────────


class TestGeometryValidation:
    """Every case from the user's audit must be rejected."""

    def test_sl_equals_entry_buy(self):
        """SIG-000005: entry=SL=TP must be rejected as SL_ZERO_DISTANCE."""
        ok, reason = validate_signal_geometry("BUY", 4203.53, 4203.53, 4203.53)
        assert ok is False
        assert "SL_ZERO_DISTANCE" in reason

    def test_sl_equals_entry_sell(self):
        ok, reason = validate_signal_geometry("SELL", 4203.53, 4203.53, 4201.0)
        assert ok is False
        assert "SL_ZERO_DISTANCE" in reason

    def test_tp_equals_entry_buy(self):
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4199.0, 4200.0)
        assert ok is False
        assert "TP_ZERO_DISTANCE" in reason

    def test_tp_equals_entry_sell(self):
        ok, reason = validate_signal_geometry("SELL", 4200.0, 4201.0, 4200.0)
        assert ok is False
        assert "TP_ZERO_DISTANCE" in reason

    def test_sl_wrong_side_buy(self):
        """BUY SL above entry."""
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4210.0, 4220.0)
        assert ok is False
        assert "SL_WRONG_SIDE" in reason

    def test_sl_wrong_side_sell(self):
        """SELL SL below entry."""
        ok, reason = validate_signal_geometry("SELL", 4200.0, 4190.0, 4180.0)
        assert ok is False
        assert "SL_WRONG_SIDE" in reason

    def test_tp_wrong_side_buy(self):
        """BUY TP below entry."""
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4190.0, 4195.0)
        assert ok is False
        assert "TP_WRONG_SIDE" in reason

    def test_tp_wrong_side_sell(self):
        """SELL TP above entry."""
        ok, reason = validate_signal_geometry("SELL", 4200.0, 4210.0, 4205.0)
        assert ok is False
        assert "TP_WRONG_SIDE" in reason

    def test_zero_stop_distance(self):
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4200.0, 4220.0)
        assert ok is False

    def test_below_min_stop(self):
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4199.5, 4220.0, min_stop_distance=2.0)
        assert ok is False
        assert "BELOW_MIN_STOP" in reason

    def test_valid_buy(self):
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4190.0, 4220.0)
        assert ok is True
        assert reason == "OK"

    def test_valid_sell(self):
        ok, reason = validate_signal_geometry("SELL", 4200.0, 4210.0, 4180.0)
        assert ok is True
        assert reason == "OK"

    def test_valid_no_tp(self):
        ok, reason = validate_signal_geometry("BUY", 4200.0, 4190.0, None)
        assert ok is True

    def test_invalid_direction(self):
        ok, reason = validate_signal_geometry("LONG", 4200.0, 4190.0, 4220.0)
        assert ok is False
        assert "INVALID_DIRECTION" in reason


# ── Spread shock gate tests ──────────────────────────────────────────


class TestSpreadShockGate:
    """SIG-000045: spread 0.31 from baseline ~0.13 must be blocked."""

    def test_no_shock_with_few_samples(self):
        gate = SpreadShockGate(min_samples=10)
        for _ in range(5):
            gate.record(0.13)
        is_shock, _, _ = gate.is_shock(0.31)
        assert is_shock is False  # not enough samples

    def test_shock_detected(self):
        gate = SpreadShockGate(min_samples=10, shock_multiplier=2.0)
        for _ in range(20):
            gate.record(0.13)
        is_shock, current, baseline = gate.is_shock(0.31)
        assert is_shock is True
        assert current == 0.31
        assert baseline == 0.13

    def test_no_shock_within_threshold(self):
        gate = SpreadShockGate(min_samples=10, shock_multiplier=2.0)
        for _ in range(20):
            gate.record(0.13)
        is_shock, _, baseline = gate.is_shock(0.20)
        assert is_shock is False
        assert baseline == 0.13

    def test_baseline_rolling_window(self):
        gate = SpreadShockGate(window_size=5, min_samples=3)
        for s in [0.10, 0.11, 0.12, 0.13, 0.14]:
            gate.record(s)
        # Window is [0.10, 0.11, 0.12, 0.13, 0.14], p50 = 0.12
        assert gate.baseline() == 0.12


# ── Deduplication tests ──────────────────────────────────────────────


class TestDeduplication:
    """Same strategy + symbol + candle + direction + features must produce at most 1 intent."""

    def test_duplicate_within_window(self):
        dedup = SignalDeduplicator(candle_seconds=60)
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)  # 30s later
        assert dedup.is_duplicate("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1) is False
        dedup.record("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1)
        assert dedup.is_duplicate("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t2) is True

    def test_no_duplicate_after_window(self):
        dedup = SignalDeduplicator(candle_seconds=60)
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 1, 0)  # 61s later
        assert dedup.is_duplicate("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1) is False
        dedup.record("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1)
        assert dedup.is_duplicate("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t2) is False

    def test_different_direction_not_duplicate(self):
        dedup = SignalDeduplicator(candle_seconds=60)
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)
        dedup.record("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1)
        assert dedup.is_duplicate("v1", "XAUUSD", "SELL", "2026-01-01T12:00:00", "hash_a", t2) is False

    def test_different_feature_hash_not_duplicate(self):
        dedup = SignalDeduplicator(candle_seconds=60)
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)
        dedup.record("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1)
        assert dedup.is_duplicate("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_b", t2) is False

    def test_different_strategy_not_duplicate(self):
        dedup = SignalDeduplicator(candle_seconds=60)
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)
        dedup.record("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1)
        assert dedup.is_duplicate("v2", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t2) is False

    def test_different_candle_not_duplicate(self):
        dedup = SignalDeduplicator(candle_seconds=60)
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)
        dedup.record("v1", "XAUUSD", "BUY", "2026-01-01T12:00:00", "hash_a", t1)
        assert dedup.is_duplicate("v1", "XAUUSD", "BUY", "2026-01-01T12:01:00", "hash_a", t2) is False


# ── Pipeline integration tests ───────────────────────────────────────


class TestShadowPipelineGates:
    """Prove the full pipeline rejects bad signals."""

    def _make_signal(self, **overrides) -> ShadowSignal:
        defaults = dict(
            signal_id="TEST-001",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            symbol="XAUUSD",
            direction="BUY",
            entry_price=4200.0,
            stop_loss=4190.0,
            take_profit=4220.0,
            outcome=ShadowSignalOutcome.ACCEPTED,
            event_risk_state="CLEAR",
            market_health_state="HEALTHY",
            sized_volume=0.01,
            hypothetical_fill_price=4200.0,
            hypothetical_spread_cost=0.13,
            hypothetical_slippage_cost=0.065,
            strategy_version="locked_v1",
            feature_hash="abc123",
            closed_candle_time="2026-01-01T11:59:00",
        )
        defaults.update(overrides)
        return ShadowSignal(**defaults)

    def test_geometry_rejects_sl_equals_entry(self):
        """The exact SIG-000005 scenario must be rejected."""
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = self._make_signal(stop_loss=4200.0, take_profit=4200.0)
        result = pipeline.process_signal(sig)
        assert result.outcome == ShadowSignalOutcome.REJECTED_GEOMETRY
        assert "GEOMETRY" in result.rejection_reason

    def test_geometry_rejects_wrong_side(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = self._make_signal(direction="BUY", stop_loss=4210.0)
        result = pipeline.process_signal(sig)
        assert result.outcome == ShadowSignalOutcome.REJECTED_GEOMETRY

    def test_spread_shock_rejects(self):
        """SIG-000045 scenario: spread 0.31 from baseline ~0.13."""
        pipeline = ShadowPipeline(spread_min_samples=5)
        pipeline.start_session("test")
        # Build baseline — each signal needs unique dedup key
        for i in range(10):
            sig = self._make_signal(
                signal_id=f"BASE-{i}",
                hypothetical_spread_cost=0.13,
                timestamp=datetime(2026, 1, 1, 12, i, 0),
                closed_candle_time=f"2026-01-01T11:{59-i:02d}:00",
            )
            pipeline.process_signal(sig)
        # Now send shock
        shock_sig = self._make_signal(
            signal_id="SHOCK-001",
            hypothetical_spread_cost=0.31,
            timestamp=datetime(2026, 1, 1, 12, 10, 0),
            closed_candle_time="2026-01-01T11:49:00",
        )
        result = pipeline.process_signal(shock_sig)
        assert result.outcome == ShadowSignalOutcome.REJECTED_SPREAD_SHOCK
        assert "SPREAD_SHOCK" in result.rejection_reason

    def test_dedup_rejects_same_candle(self):
        pipeline = ShadowPipeline(dedup_candle_seconds=60)
        pipeline.start_session("test")
        t1 = datetime(2026, 1, 1, 12, 0, 0)
        t2 = datetime(2026, 1, 1, 12, 0, 30)
        sig1 = self._make_signal(signal_id="SIG-1", timestamp=t1)
        sig2 = self._make_signal(signal_id="SIG-2", timestamp=t2)
        pipeline.process_signal(sig1)
        result = pipeline.process_signal(sig2)
        assert result.outcome == ShadowSignalOutcome.REJECTED_DUPLICATE

    def test_event_block_rejects(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = self._make_signal(event_risk_state="NFP_BLACKOUT")
        result = pipeline.process_signal(sig)
        assert result.outcome == ShadowSignalOutcome.REJECTED_EVENT_BLOCK

    def test_market_health_rejects(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = self._make_signal(market_health_state="DISCONNECTED")
        result = pipeline.process_signal(sig)
        assert result.outcome == ShadowSignalOutcome.REJECTED_MARKET_HEALTH

    def test_valid_signal_accepted(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = self._make_signal()
        result = pipeline.process_signal(sig)
        assert result.outcome == ShadowSignalOutcome.ACCEPTED


# ── Position lifecycle tests ─────────────────────────────────────────


class TestPositionLifecycle:
    """Full lifecycle: signal → gate → open → SL/TP/time → P&L → ledger."""

    def _make_pipeline_with_accepted(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = ShadowSignal(
            signal_id="SIG-001",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            symbol="XAUUSD",
            direction="BUY",
            entry_price=4200.0,
            stop_loss=4190.0,
            take_profit=4220.0,
            outcome=ShadowSignalOutcome.ACCEPTED,
            sized_volume=0.01,
            hypothetical_fill_price=4200.0,
            hypothetical_spread_cost=0.13,
            hypothetical_slippage_cost=0.065,
        )
        pipeline.process_signal(sig)
        return pipeline, sig

    def test_open_position(self):
        pipeline, sig = self._make_pipeline_with_accepted()
        pos = pipeline.open_position(sig)
        assert pos is not None
        assert pos.status == PositionStatus.OPEN
        assert pos.fill_price == 4200.0

    def test_cannot_open_rejected(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = ShadowSignal(
            signal_id="SIG-001",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            symbol="XAUUSD",
            direction="BUY",
            entry_price=4200.0,
            stop_loss=4190.0,
            take_profit=4220.0,
            outcome=ShadowSignalOutcome.REJECTED_GEOMETRY,
        )
        pos = pipeline.open_position(sig)
        assert pos is None

    def test_sl_close(self):
        pipeline, sig = self._make_pipeline_with_accepted()
        pos = pipeline.open_position(sig)
        # Price drops to SL
        closed = pipeline.check_position_exit(
            pos,
            current_bid=4189.0,
            current_ask=4189.5,
            timestamp=datetime(2026, 1, 1, 12, 5, 0),
        )
        assert closed is True
        assert pos.status == PositionStatus.CLOSED_SL
        assert pos.exit_price == 4190.0
        assert pos.pnl_gross < 0  # loss on BUY when price drops

    def test_tp_close(self):
        pipeline, sig = self._make_pipeline_with_accepted()
        pos = pipeline.open_position(sig)
        # Price rises to TP
        closed = pipeline.check_position_exit(
            pos,
            current_bid=4221.0,
            current_ask=4221.5,
            timestamp=datetime(2026, 1, 1, 12, 5, 0),
        )
        assert closed is True
        assert pos.status == PositionStatus.CLOSED_TP
        assert pos.exit_price == 4220.0
        assert pos.pnl_gross > 0  # profit on BUY when price rises

    def test_pnl_calculation(self):
        pipeline, sig = self._make_pipeline_with_accepted()
        pos = pipeline.open_position(sig)
        pipeline.check_position_exit(
            pos,
            current_bid=4220.0,
            current_ask=4220.5,
            timestamp=datetime(2026, 1, 1, 12, 5, 0),
        )
        # BUY 0.01 at 4200, exit at 4220: gross = (4220-4200)*0.01 = 0.20
        assert abs(pos.pnl_gross - 0.20) < 0.01
        # Net = gross - costs
        assert pos.pnl_net < pos.pnl_gross

    def test_sell_direction_pnl(self):
        pipeline = ShadowPipeline()
        pipeline.start_session("test")
        sig = ShadowSignal(
            signal_id="SIG-SELL",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            symbol="XAUUSD",
            direction="SELL",
            entry_price=4200.0,
            stop_loss=4210.0,
            take_profit=4180.0,
            outcome=ShadowSignalOutcome.ACCEPTED,
            sized_volume=0.01,
            hypothetical_fill_price=4200.0,
            hypothetical_spread_cost=0.13,
            hypothetical_slippage_cost=0.065,
        )
        pipeline.process_signal(sig)
        pos = pipeline.open_position(sig)
        # Price drops (good for SELL)
        pipeline.check_position_exit(
            pos,
            current_bid=4179.0,
            current_ask=4179.5,
            timestamp=datetime(2026, 1, 1, 12, 5, 0),
        )
        assert pos.status == PositionStatus.CLOSED_TP
        assert pos.pnl_gross > 0  # profit on SELL when price drops

    def test_session_summary_includes_pnl(self):
        pipeline, sig = self._make_pipeline_with_accepted()
        pos = pipeline.open_position(sig)
        pipeline.check_position_exit(
            pos,
            current_bid=4220.0,
            current_ask=4220.5,
            timestamp=datetime(2026, 1, 1, 12, 5, 0),
        )
        session = pipeline.get_session("test")
        summary = session.summary()
        assert summary["positions_opened"] == 1
        assert summary["positions_closed"] == 1
        assert summary["total_pnl_net"] != 0


# ── Reproduce the actual SIG-000005 failure ─────────────────────────


class TestReproduceOriginalFailure:
    """Reproduce the exact failure from the shadow session data."""

    def test_sig_000005_rejected(self):
        """entry=4203.53, SL=4203.53, TP=4203.53 → MUST be rejected."""
        pipeline = ShadowPipeline()
        pipeline.start_session("reproduce")
        sig = ShadowSignal(
            signal_id="SIG-000005",
            timestamp=datetime(2026, 6, 22, 9, 30, 0),
            symbol="XAUUSD",
            direction="SELL",
            entry_price=4203.53,
            stop_loss=4203.53,
            take_profit=4203.53,
            outcome=ShadowSignalOutcome.ACCEPTED,
            event_risk_state="CLEAR",
            market_health_state="HEALTHY",
            sized_volume=0.01,
            hypothetical_fill_price=4203.53,
            hypothetical_spread_cost=0.0,
            hypothetical_slippage_cost=0.0,
            strategy_version="locked_v1",
            feature_hash="abc123",
            closed_candle_time="2026-06-22T09:29:00",
        )
        result = pipeline.process_signal(sig)
        assert result.outcome == ShadowSignalOutcome.REJECTED_GEOMETRY
        assert result.rejection_reason != ""

    def test_sig_000045_rejected(self):
        """spread=0.31 from baseline ~0.13 → MUST be rejected after warmup."""
        pipeline = ShadowPipeline(spread_min_samples=5)
        pipeline.start_session("reproduce")
        # Build baseline with 10 normal spreads
        for i in range(10):
            sig = ShadowSignal(
                signal_id=f"SIG-{i:06d}",
                timestamp=datetime(2026, 6, 22, 9, 26 + i, 0),
                symbol="XAUUSD",
                direction="SELL",
                entry_price=4200.0 + i,
                stop_loss=4201.0 + i,
                take_profit=4198.0 + i,
                outcome=ShadowSignalOutcome.ACCEPTED,
                event_risk_state="CLEAR",
                market_health_state="HEALTHY",
                sized_volume=0.01,
                hypothetical_fill_price=4200.0 + i,
                hypothetical_spread_cost=0.13,
                hypothetical_slippage_cost=0.065,
                strategy_version="locked_v1",
                feature_hash="abc123",
                closed_candle_time=f"2026-06-22T09:{25+i:02d}:00",
            )
            pipeline.process_signal(sig)
        # Now send the shock spread
        shock = ShadowSignal(
            signal_id="SIG-000045",
            timestamp=datetime(2026, 6, 22, 10, 10, 0),
            symbol="XAUUSD",
            direction="BUY",
            entry_price=4211.34,
            stop_loss=4208.24,
            take_profit=4217.54,
            outcome=ShadowSignalOutcome.ACCEPTED,
            event_risk_state="CLEAR",
            market_health_state="HEALTHY",
            sized_volume=0.01,
            hypothetical_fill_price=4211.34,
            hypothetical_spread_cost=0.31,
            hypothetical_slippage_cost=0.155,
            strategy_version="locked_v1",
            feature_hash="abc123",
            closed_candle_time="2026-06-22T10:09:00",
        )
        result = pipeline.process_signal(shock)
        assert result.outcome == ShadowSignalOutcome.REJECTED_SPREAD_SHOCK
